"""photo_store.py — Terpee's own photo files, in Supabase Storage.

The `photos` bucket (migration 0013) is public to read and written only with the
service-role key. Two kinds of file go in it: store photos copied at web sizes from
hosts that cannot resize on request (photo_mirror.py), and brand logos.

    url = upload("store/ab12/640.webp", data, "image/webp")

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (DB_ACCESS.md).
"""

from __future__ import annotations

import io
import os
import urllib.parse
import urllib.request
from typing import Iterable

BUCKET = "photos"
TIMEOUT_SECONDS = 60
# Copies are named after their source and never change, so a browser may keep them.
CACHE_SECONDS = 30 * 24 * 3600


def configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def _base() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def public_url(path: str) -> str:
    return f"{_base()}/storage/v1/object/public/{BUCKET}/{urllib.parse.quote(path)}"


def upload(path: str, data: bytes, content_type: str) -> str:
    """Write one file (replacing any there) and return its public URL."""
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        f"{_base()}/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}",
        data=data, method="POST",
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": content_type,
                 "x-upsert": "true", "cache-control": f"max-age={CACHE_SECONDS}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):
        pass
    return public_url(path)


def webp_sizes(data: bytes, widths: Iterable[int], quality: int = 80) -> dict[int, bytes]:
    """The image at each width as WebP, never enlarged, transparency kept, turned the
    way its EXIF says. Raises ValueError for something that is not an image."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"not an image: {e}") from e
    im = ImageOps.exif_transpose(im)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if has_alpha else "RGB")
    out = {}
    for w in widths:
        copy = im.copy()
        if copy.width > w:
            copy = copy.resize((w, max(1, round(copy.height * w / copy.width))), Image.LANCZOS)
        buf = io.BytesIO()
        copy.save(buf, "WEBP", quality=quality, method=4)
        out[w] = buf.getvalue()
    return out
