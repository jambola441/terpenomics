"""Brand logos: read off a brand's own site, picked by a person, stored as ours.

A brand's tile used to show whichever of its product photos sorted first. The admin
(routes/admin/brand_logos.py) now lists the biggest brands; for each, `candidates`
reads the brand's home page for the images a site names as its logo, a person picks
one (or uploads a file), and `store_logo` writes it to the photos bucket at a
web size. Brand tiles and pages show it (logos_for); a brand without one keeps the
product photo or its initial.

Fetching a URL a person typed is done server-side, so every request, redirects
included, must go to a public address on https: never the API's own network.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from typing import Iterable, Optional

from sqlmodel import Session, select

from models import BrandLogo
from services import photo_store

MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 20
USER_AGENT = "Mozilla/5.0 (compatible; terpee-logos/1.0)"
# Drawn at most 64px wide, at up to 3x.
LOGO_PX = 384
MAX_CANDIDATES = 12


def brand_key(brand: Optional[str]) -> str:
    """The key logos (and catalogs) are filed under: lowercase, '&' folded to 'and',
    no punctuation. Mirrors scripts/catalog_store.brand_key; a test keeps them equal."""
    s = re.sub(r"\s*[&+]\s*", " and ", (brand or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s)).strip()


def logos_for(session: Session, brand_names: Iterable[Optional[str]]) -> dict[str, str]:
    """brand name -> logo URL, for the names that have one. One query."""
    by_key: dict[str, list[str]] = {}
    for name in brand_names:
        if name:
            by_key.setdefault(brand_key(name), []).append(name)
    if not by_key:
        return {}
    rows = session.exec(
        select(BrandLogo.brand_key, BrandLogo.logo_url)
        .where(BrandLogo.brand_key.in_(list(by_key)))
        .where(BrandLogo.logo_url.is_not(None))
    ).all()
    return {name: url for key, url in rows for name in by_key.get(key, [])}


# --------------------------------------------------------------------------- fetching

class UnsafeURL(ValueError):
    """A URL that is not https, or whose host is not a public address."""


def check_public(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise UnsafeURL(f"only https URLs: {url[:120]}")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURL(f"unknown host {parts.hostname}") from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise UnsafeURL(f"{parts.hostname} is not a public address")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirects)


def fetch(url: str, max_bytes: int, accept: str) -> tuple[bytes, str, str]:
    """(body, content type, final URL) of a public https URL, at most max_bytes."""
    check_public(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with _opener.open(req, timeout=TIMEOUT_SECONDS) as r:
        body = r.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"larger than {max_bytes // 1024 // 1024} MB")
        return body, r.headers.get("Content-Type", ""), r.geturl()


# --------------------------------------------------------------------------- candidates

def _ld_logos(node) -> Iterable[str]:
    """`logo` values anywhere in a JSON-LD blob (Organization, Brand, WebSite...)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "logo":
                if isinstance(v, str):
                    yield v
                elif isinstance(v, dict) and isinstance(v.get("url"), str):
                    yield v["url"]
            else:
                yield from _ld_logos(v)
    elif isinstance(node, list):
        for v in node:
            yield from _ld_logos(v)


def candidates_from_html(html: str, page_url: str) -> list[dict]:
    """The images a page names as its logo, most likely first: a structured-data logo,
    images marked "logo" (the header's), the home-screen icon, large icons, then the
    share image (often a banner, so last)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    seen: set[str] = set()

    def add(src: Optional[str], kind: str) -> None:
        if not src or src.strip().startswith("data:"):
            return
        url = urllib.parse.urljoin(page_url, src.strip().split()[0])
        if url.startswith("https://") and url not in seen:
            seen.add(url)
            found.append({"url": url, "kind": kind})

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            for url in _ld_logos(json.loads(script.string or "")):
                add(url, "site logo")
        except ValueError:
            continue
    for img in soup.find_all("img"):
        marks = " ".join([" ".join(img.get("class") or []), img.get("id") or "", img.get("alt") or "",
                          img.get("src") or ""]).lower()
        if "logo" in marks:
            srcset = (img.get("srcset") or img.get("data-srcset") or "").split(",")[0]
            add(img.get("src") or img.get("data-src") or srcset, "logo image")
    links = []
    for link in soup.find_all("link", href=True):
        sizes = [int(n) for n in re.findall(r"(\d+)x\d+", (link.get("sizes") or "") + " " + link["href"])]
        links.append(({r.lower() for r in (link.get("rel") or [])}, max(sizes, default=0), link))
    # Largest first; one under 96px would be blurry on the tile.
    links.sort(key=lambda x: -x[1])
    for rels, px, link in links:      # one is enough: the others are the same at other sizes
        if rels & {"apple-touch-icon", "apple-touch-icon-precomposed"} and (px == 0 or px >= 96):
            add(link["href"], "app icon")
            break
    for rels, px, link in links:
        if "icon" in rels and (px >= 96 or "svg" in (link.get("type") or "")):
            add(link["href"], "icon")
    for meta in soup.find_all("meta"):
        if (meta.get("property") or meta.get("name") or "").lower() in ("og:image", "twitter:image"):
            add(meta.get("content"), "share image")
    if not any(c["kind"] == "app icon" for c in found):
        add("/apple-touch-icon.png", "app icon (guessed)")
    return found[:MAX_CANDIDATES]


def candidates(site_url: str) -> list[dict]:
    """Logo candidates on a brand's home page."""
    body, _, final = fetch(site_url, MAX_PAGE_BYTES, "text/html,application/xhtml+xml")
    return candidates_from_html(body.decode("utf-8", "replace"), final)


# --------------------------------------------------------------------------- storing

_SVG_DANGER = re.compile(rb"<script|<foreignobject|\son\w+\s*=|javascript:", re.I)


def logo_file(data: bytes) -> tuple[bytes, str, str]:
    """(file, content type, extension) for a logo: an SVG kept as drawn when it carries
    no script, anything else at LOGO_PX as WebP with its transparency."""
    head = data[:1024].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:4096].lower()):
        if _SVG_DANGER.search(data):
            raise ValueError("an SVG with script in it")
        return data, "image/svg+xml", "svg"
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("not an image") from e
    im = ImageOps.exif_transpose(im).convert("RGBA")
    im.thumbnail((LOGO_PX, LOGO_PX), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=90, method=4)
    return buf.getvalue(), "image/webp", "webp"


def store_logo(key: str, data: bytes) -> str:
    """Write a logo to the bucket and return its URL. Named by its content, so a new
    pick is a new URL and no browser shows the old one from its cache."""
    body, content_type, ext = logo_file(data)
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "brand"
    path = f"logos/{slug}-{hashlib.sha1(body).hexdigest()[:10]}.{ext}"
    return photo_store.upload(path, body, content_type)
