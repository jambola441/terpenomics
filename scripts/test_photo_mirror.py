"""photo_mirror.py: which store photos are copied, and what a copy is — offline."""

import io
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import photo_mirror as pm  # noqa: E402

PIL = pytest.importorskip("PIL.Image")
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def png(width, height, alpha=False):
    buf = io.BytesIO()
    PIL.new("RGBA" if alpha else "RGB", (width, height), (10, 120, 60, 128) if alpha else (10, 120, 60)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("url,resizable", [
    ("https://s3-us-west-2.amazonaws.com/dutchie-images/abc", True),
    ("https://dutchie-images.s3.us-west-2.amazonaws.com/abc", True),
    ("https://tymber-blaze-products.imgix.net/a.jpg", True),
    ("https://tymber-s3.imgix.net/a.jpg?s=sig", False),           # signed: copy it
    ("https://cdn.shopify.com/s/files/a.png?v=1", True),
    ("https://abc.supabase.co/storage/v1/object/public/photos/store/k/640.webp", True),
    ("https://storage.googleapis.com/maui/x.png", False),
    ("https://leaflogixmedia.blob.core.windows.net/product-image/x.jpg", False),
    ("https://d1qjybsjlbmhj3.cloudfront.net/x.png", False),
])
def test_only_photos_their_host_cannot_resize_are_copied(url, resizable):
    assert pm.resizes_on_request(url) is resizable


def test_pending_skips_copied_and_recent_failures_and_retries_old_ones():
    g = "https://storage.googleapis.com/m/"
    mirrors = {g + "done": {"url": "https://x/640.webp", "mirrored_at": NOW - timedelta(days=90)},
               g + "failed-yesterday": {"url": None, "mirrored_at": NOW - timedelta(days=1)},
               g + "failed-long-ago": {"url": None, "mirrored_at": NOW - timedelta(days=8)}}
    urls = [g + "new", g + "new", g + "done", g + "failed-yesterday", g + "failed-long-ago",
            "https://s3-us-west-2.amazonaws.com/dutchie-images/k", "http://plain/x.png", "data:image/png,x", None]
    assert pm.pending(urls, mirrors, NOW) == [g + "failed-long-ago", g + "new"]


def test_a_copy_is_two_webp_widths_never_enlarged_and_keeps_transparency():
    uploads = {}

    def upload(path, data, content_type):
        uploads[path] = (data, content_type)
        return f"https://abc.supabase.co/storage/v1/object/public/photos/{path}"

    row = pm.copy("https://storage.googleapis.com/m/a.png", fetch=lambda u: png(1600, 1200, alpha=True),
                  upload=upload)
    assert row["failed"] is None and row["bytes"] > 0 and row["url"].endswith("/640.webp")
    sizes = {p.rsplit("/", 1)[1]: PIL.open(io.BytesIO(d)) for p, (d, ct) in uploads.items()}
    assert {k: v.size for k, v in sizes.items()} == {"320.webp": (320, 240), "640.webp": (640, 480)}
    assert all(v.format == "WEBP" and v.mode == "RGBA" for v in sizes.values())
    assert {ct for _, ct in uploads.values()} == {"image/webp"}

    uploads.clear()
    pm.copy("https://storage.googleapis.com/m/small.png", fetch=lambda u: png(200, 100), upload=upload)
    assert {PIL.open(io.BytesIO(d)).size for d, _ in uploads.values()} == {(200, 100)}


def test_a_photo_that_cannot_be_copied_says_why():
    def gone(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    assert pm.copy("https://x/gone.png", fetch=gone, upload=None)["failed"] == "HTTP 404"
    row = pm.copy("https://x/page.png", fetch=lambda u: b"<html>", upload=None)
    assert row["url"] is None and row["failed"].startswith("ValueError: not an image")


@pytest.mark.parametrize("error", [
    urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer")),
    urllib.error.HTTPError("https://x", 503, "Unavailable", {}, None),
    TimeoutError("timed out"),
])
def test_a_network_hiccup_is_not_recorded_so_the_next_run_retries(error):
    def flaky(url):
        raise error
    assert pm.copy("https://x/a.png", fetch=flaky, upload=None) is None


def test_a_photo_too_big_to_decode_safely_is_refused(monkeypatch):
    from services import photo_store
    monkeypatch.setattr(photo_store, "MAX_PIXELS", 100 * 100)
    row = pm.copy("https://x/huge.png", fetch=lambda u: png(200, 200), upload=None)
    assert "too large to resize" in row["failed"]


def test_run_copies_pending_photos_and_records_every_attempt(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    g = "https://storage.googleapis.com/m/"
    monkeypatch.setattr(pm, "_load_postgres", lambda: ([g + "a", g + "b", g + "a"], {}))
    saved = []
    monkeypatch.setattr(pm, "_save_postgres", saved.extend)
    monkeypatch.setattr(pm, "_load_postgres", lambda: ([g + "a", g + "b", g + "a", g + "c"], {}))
    monkeypatch.setattr(pm, "copy", lambda url: None if url.endswith("c") else {
        "source_url": url, "url": None if url.endswith("b") else "u", "bytes": 1, "failed": None,
        "mirrored_at": NOW})
    assert pm.run() == {"pending": 3, "copied": 1, "failed": 1, "later": 1}
    assert sorted(r["source_url"] for r in saved) == [g + "a", g + "b"]       # c: not recorded


def test_run_without_storage_keys_skips(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert pm.run()["skipped"] is True
