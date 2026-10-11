"""apply_review_decisions.py: the one-off that applies recorded `entry` decisions."""
import apply_review_decisions as ard


class FakeDb:
    def __init__(self, decisions, listings):
        self._d, self._l, self.applied = decisions, listings, []

    def decisions(self):
        return self._d

    def listings(self, ids):
        return {i: self._l[i] for i in ids if i in self._l}

    def apply(self, c):
        self.applied.append(c)

    def commit(self):
        pass


DECISIONS = [
    {"id": "d1", "listing_id": "l1", "decision": "entry", "entry_id": "e1", "reason": "review_unsure"},
    {"id": "d2", "listing_id": "l2", "decision": "entry", "entry_id": "e2", "reason": "review_near"},  # matched since
    {"id": "d3", "listing_id": "l3", "decision": "none", "entry_id": None, "reason": "review_missing"},
]
LISTINGS = {
    "l1": {"id": "l1", "catalog_entry_id": "e9", "catalog_match_method": "review_unsure",
           "catalog_match_confidence": 0.6, "scraped_name": "A", "scraped_brand": "B"},
    "l2": {"id": "l2", "catalog_entry_id": "e2", "catalog_match_method": "exact",
           "catalog_match_confidence": 1.0, "scraped_name": "C", "scraped_brand": "B"},
    "l3": {"id": "l3", "catalog_entry_id": None, "catalog_match_method": "review_missing",
           "catalog_match_confidence": None, "scraped_name": "D", "scraped_brand": "B"},
}


def test_plan_takes_entry_decisions_still_in_review_and_keeps_the_prior_match():
    assert ard.plan(DECISIONS, LISTINGS) == [{
        "decision_id": "d1", "listing_id": "l1", "entry_id": "e1", "prev_method": "review_unsure",
        "prev_entry_id": "e9", "prev_confidence": 0.6, "name": "A", "brand": "B"}]


def test_dry_run_by_default_writes_nothing(monkeypatch, capsys):
    db = FakeDb(DECISIONS, LISTINGS)
    monkeypatch.setattr(ard, "PgDb", lambda: db)
    assert ard.main([]) == 0
    assert db.applied == []
    out = capsys.readouterr().out
    assert "listing still in review: 1" in out and "dry run" in out


def test_write_applies(monkeypatch):
    db = FakeDb(DECISIONS, LISTINGS)
    monkeypatch.setattr(ard, "HttpDb", lambda: db)
    assert ard.main(["--write", "--via-http"]) == 0
    assert [c["listing_id"] for c in db.applied] == ["l1"]
