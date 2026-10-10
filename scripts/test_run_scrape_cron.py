"""Tests for run_scrape_cron's pause switch — offline: scrape.py is never started."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_scrape_cron as cron  # noqa: E402


class FakeProc:
    pid = 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def run(monkeypatch, tmp_path):
    """A run with its files in tmp_path; records alerts and the sweeps it starts."""
    seen = {"alerts": [], "started": [], "mirrored": 0}
    monkeypatch.setattr(cron, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cron, "LOCK_FILE", tmp_path / "_cron.lock")
    monkeypatch.setattr(cron, "STATUS_FILE", tmp_path / "_cron_status.json")
    monkeypatch.setattr(cron, "SUMMARY_FILE", tmp_path / "_last_run.json")
    monkeypatch.setattr(cron, "_alert", seen["alerts"].append)

    def popen(cmd, **kwargs):
        seen["started"].append(cmd)
        return FakeProc()
    monkeypatch.setattr(cron.subprocess, "Popen", popen)
    monkeypatch.setattr(cron, "_mirror_photos", lambda: seen.__setitem__("mirrored", seen["mirrored"] + 1))
    return seen


@pytest.mark.parametrize("value", ["1", "true", "YES", "until the matching test is done"])
def test_a_paused_pipeline_skips_the_run_and_says_so(run, monkeypatch, tmp_path, value):
    (tmp_path / "_cron_status.json").write_text('{"state": "ok"}')
    monkeypatch.setenv("PIPELINE_PAUSED", value)
    assert cron.run_pipeline() == 0
    assert run["started"] == []
    assert len(run["alerts"]) == 1 and "PIPELINE_PAUSED" in run["alerts"][0]
    # The last real run's heartbeat is left alone.
    assert (tmp_path / "_cron_status.json").read_text() == '{"state": "ok"}'


@pytest.mark.parametrize("value", [None, "", "0", "false", "No", " no "])
def test_the_switch_is_off_unless_set(run, monkeypatch, tmp_path, value):
    if value is None:
        monkeypatch.delenv("PIPELINE_PAUSED", raising=False)
    else:
        monkeypatch.setenv("PIPELINE_PAUSED", value)
    assert cron.run_pipeline() == 0
    assert len(run["started"]) == 1 and run["alerts"] == []
    assert json.loads((tmp_path / "_cron_status.json").read_text())["state"] == "ok"


def test_a_good_run_copies_new_photos_and_a_failed_one_does_not(run, monkeypatch):
    monkeypatch.delenv(cron.PAUSE_ENV, raising=False)
    assert cron.run_pipeline() == 0 and run["mirrored"] == 1

    class Failing(FakeProc):
        def wait(self, timeout=None):
            return 1
    monkeypatch.setattr(cron.subprocess, "Popen", lambda cmd, **kw: Failing())
    assert cron.run_pipeline() == 1 and run["mirrored"] == 1


def test_a_photo_mirror_failure_never_fails_the_run(monkeypatch, caplog):
    import photo_mirror

    def boom(**kw):
        raise RuntimeError("storage down")
    monkeypatch.setattr(photo_mirror, "run", boom)
    cron._mirror_photos()                     # logs, does not raise
    assert "photo mirror failed" in caplog.text
