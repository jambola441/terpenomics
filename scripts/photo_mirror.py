#!/usr/bin/env python3
"""photo_mirror.py — Copy store photos that cannot be resized on request into
Terpee's own storage, at the sizes the apps draw.

Most store photos sit behind an image service that resizes on request (Dutchie's,
imgix, Shopify), and the web and app ask those for the drawn size
(ui/my-app/src/utils/photoUrl.ts). The rest are plain files on Google Cloud Storage,
Azure and CloudFront, often print-size: those are downloaded once, written at 320px
and 640px as WebP to the `photos` bucket (photo_store.py), and recorded in
photo_mirrors. The API then serves the copy (services/listing_photos.py), and the
apps pick 320 or 640 by the size they draw.

A photo that cannot be copied (gone, not an image) is recorded with the reason and
tried again a week later; its listings keep the original.

  python scripts/photo_mirror.py                # copy what is new, over DATABASE_URL
  python scripts/photo_mirror.py --via-http     # the same over Supabase's REST API
  python scripts/photo_mirror.py --dry-run      # count what would be copied

The daily cron job runs it after the scrape (run_scrape_cron.py).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import photo_store  # noqa: E402

WIDTHS = (320, 640)
RETRY_AFTER = timedelta(days=7)
MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; terpee-photos/1.0)"


def resizes_on_request(url: str) -> bool:
    """Whether the apps already get this photo resized from its own host. Mirrors
    photoAt in ui/my-app/src/utils/photoUrl.ts: change one, change both."""
    m = re.match(r"^https://([^/?#]+)([^?#]*)(\?[^#]*)?$", url or "", re.I)
    if not m:
        return False
    host, path, query = m.group(1).lower(), m.group(2), m.group(3) or ""
    if host == "s3-us-west-2.amazonaws.com" and path.startswith("/dutchie-images/"):
        return True
    if host == "dutchie-images.s3.us-west-2.amazonaws.com":
        return True
    if host.endswith(".imgix.net") or host == "images.weedmaps.com":
        return not re.search(r"(^\?|&)s=", query)
    return host == "cdn.shopify.com" or "/cdn/shop/" in path or host.endswith(".supabase.co")


def pending(urls: Iterable[str], mirrors: dict[str, dict], now: datetime) -> list[str]:
    """The photos to copy: https, not resizable at their host, and not copied
    already nor failed within RETRY_AFTER."""
    out = []
    for url in sorted({u for u in urls if u}):
        if not url.lower().startswith("https://") or resizes_on_request(url):
            continue
        done = mirrors.get(url)
        if done and (done.get("url") or done["mirrored_at"] > now - RETRY_AFTER):
            continue
        out.append(url)
    return out


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"over {MAX_BYTES // 1024 // 1024} MB")
    return data


def copy(url: str, fetch: Callable[[str], bytes] = _fetch,
         upload: Callable[[str, bytes, str], str] = photo_store.upload) -> dict:
    """One photo copied: its photo_mirrors row, with `failed` set when it could not be."""
    folder = f"store/{hashlib.sha1(url.encode()).hexdigest()[:32]}"
    now = datetime.now(timezone.utc)
    try:
        data = fetch(url)
        sizes = photo_store.webp_sizes(data, WIDTHS)
        urls = {w: upload(f"{folder}/{w}.webp", body, "image/webp") for w, body in sizes.items()}
        return {"source_url": url, "url": urls[max(WIDTHS)], "bytes": len(data),
                "failed": None, "mirrored_at": now}
    except Exception as e:  # noqa: BLE001 — recorded per photo; the rest go on
        reason = f"HTTP {e.code}" if hasattr(e, "code") else f"{type(e).__name__}: {e}"
        return {"source_url": url, "url": None, "bytes": None, "failed": reason[:300],
                "mirrored_at": now}


# --------------------------------------------------------------------------- storage

def _load_postgres() -> tuple[list[str], dict[str, dict]]:
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT image_url FROM listings "
                "WHERE is_active AND image_url LIKE 'https://%%'")
    urls = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT source_url, url, mirrored_at FROM photo_mirrors")
    mirrors = {s: {"url": u, "mirrored_at": t} for s, u, t in cur.fetchall()}
    conn.close()
    return urls, mirrors


def _save_postgres(rows: list[dict]) -> None:
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    psycopg2.extras.execute_values(conn.cursor(), """
        INSERT INTO photo_mirrors (source_url, url, bytes, failed, mirrored_at) VALUES %s
        ON CONFLICT (source_url) DO UPDATE SET url = EXCLUDED.url, bytes = EXCLUDED.bytes,
            failed = EXCLUDED.failed, mirrored_at = EXCLUDED.mirrored_at
        """, [(r["source_url"], r["url"], r["bytes"], r["failed"], r["mirrored_at"]) for r in rows])
    conn.commit()
    conn.close()


def _load_http() -> tuple[list[str], dict[str, dict]]:
    import db_http
    urls = [r["image_url"] for r in db_http.select_all(
        "listings", "select=image_url&is_active=is.true&image_url=like.https*&order=id")]
    mirrors = {r["source_url"]: {"url": r["url"],
                                 "mirrored_at": datetime.fromisoformat(r["mirrored_at"])}
               for r in db_http.select_all("photo_mirrors",
                                           "select=source_url,url,mirrored_at&order=source_url")}
    return urls, mirrors


def _save_http(rows: list[dict]) -> None:
    import db_http
    db_http.upsert("photo_mirrors", [{**r, "mirrored_at": r["mirrored_at"].isoformat()} for r in rows],
                   on_conflict="source_url")


def run(via_http: bool = False, dry_run: bool = False, limit: Optional[int] = None,
        workers: int = 8) -> dict:
    """Copy what is pending. Returns counts; prints them."""
    if not photo_store.configured() and not dry_run:
        print("photo_mirror: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipped")
        return {"pending": 0, "copied": 0, "failed": 0, "skipped": True}
    urls, mirrors = _load_http() if via_http else _load_postgres()
    todo = pending(urls, mirrors, datetime.now(timezone.utc))[:limit]
    print(f"photo_mirror: {len(todo)} photos to copy "
          f"({len(mirrors)} already recorded, {len(set(urls))} in use)")
    if dry_run or not todo:
        return {"pending": len(todo), "copied": 0, "failed": 0}
    save = _save_http if via_http else _save_postgres
    copied = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        batch = []
        for row in pool.map(copy, todo):
            batch.append(row)
            copied += row["url"] is not None
            failed += row["url"] is None
            if len(batch) == 100:
                save(batch)
                batch = []
        if batch:
            save(batch)
    print(f"photo_mirror: {copied} copied, {failed} could not be (kept their original)")
    return {"pending": len(todo), "copied": copied, "failed": failed}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--via-http", action="store_true", default=os.environ.get("DB_VIA_HTTP") == "1",
                    help="read and write over Supabase's REST API (a sandbox; DB_ACCESS.md)")
    ap.add_argument("--dry-run", action="store_true", help="count what would be copied")
    ap.add_argument("--limit", type=int, help="copy at most this many")
    args = ap.parse_args()
    try:  # the .env, where a sandbox keeps the keys (DB_ACCESS.md); Render sets them itself
        import db_http
        db_http._load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    run(via_http=args.via_http, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
