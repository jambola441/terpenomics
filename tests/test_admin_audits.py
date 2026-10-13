"""The admin audits API (routes/admin/audits.py).

The API writes audit rows and queues jobs; the worker does the work (scripts/audits.py,
tested in scripts/test_audits.py). Here: a run is created with its build job, brand
health adds up, a run's summary gives error rates and per-flag precision, a person's
verdict counts, the two listing fixes write and log, and proposals move only from
measured to approved (which queues the apply) or to rejected.
"""
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser
from database import engine
from models import (
    AuditItem, AuditJob, AuditLog, AuditProposal, AuditRun, BrandCatalog, BrandCatalogEntry, Dispensary,
    Listing, ReviewDecision,
)
from routes.admin import router as admin_router
from routes.admin.auth import require_admin


@pytest.fixture
def world():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for model in (AuditLog, AuditJob, AuditProposal, AuditItem, AuditRun, ReviewDecision, Listing,
                      BrandCatalogEntry, BrandCatalog, Dispensary):
            for row in s.exec(select(model)).all():
                s.delete(row)
        s.commit()
        camino = BrandCatalog(brand_slug="camino", brand_name="Camino", source_method="listings_bootstrap")
        s.add(camino)
        s.commit()
        e20 = BrandCatalogEntry(catalog_id=camino.id, name="Yuzu Lemon", strain="Yuzu Lemon", category="edible",
                                variant="20pk 100mg")
        e10 = BrandCatalogEntry(catalog_id=camino.id, name="Yuzu Lemon", strain="Yuzu Lemon", category="edible",
                                variant="10pk 50mg")
        store = Dispensary(name="Court", slug="court")
        s.add_all([e20, e10, store])
        s.commit()

        def L(name, method, entry=None, **kw):
            return Listing(dispensary_id=store.id, scraped_name=name, scraped_brand="Camino",
                           scraped_category="edible", catalog_match_method=method,
                           catalog_entry_id=entry.id if entry else None, **kw)
        ls = {"a": L("Camino Yuzu 20pk", "attributes", e20, price_cents=2000),
              "b": L("Camino Yuzu 10pk", "attributes", e20, price_cents=1000),
              "c": L("Camino Yuzu ?", "review_unsure", e10),
              "d": L("Camino Yuzu 20", "manual", e20)}
        s.add_all(ls.values())
        s.commit()
        return {"catalog": camino.id, "e20": e20.id, "e10": e10.id,
                **{k: v.id for k, v in ls.items()}}


def _client(user_id="admin-1"):
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id=user_id, email=f"{user_id}@example.com", phone=None, role="admin", raw_claims={})
    return TestClient(app)


def _run_with_items(world, verdicts):
    """A ready run with one item per (listing key, source, flag kinds, verdict)."""
    with Session(engine) as s:
        run = AuditRun(brands=["Camino"], sample_size=2, created_by="t", status="ready")
        s.add(run)
        s.commit()
        for key, source, kinds, verdict in verdicts:
            s.add(AuditItem(run_id=run.id, listing_id=world[key], brand="Camino", source=source,
                            flags=[{"kind": k, "text": k} for k in kinds], verdict=verdict,
                            evidence={"listing": {"id": str(world[key])}}))
        s.commit()
        return run.id


def test_create_run_queues_its_build(world):
    c = _client()
    r = c.post("/admin/audits/runs", json={"brands": ["camino"], "sample_size": 5, "judge_model": "claude-haiku-5-5"})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["brands"] == ["Camino"] and run["status"] == "queued" and run["judge_label"] == "Haiku 5.5"
    with Session(engine) as s:
        (job,) = s.exec(select(AuditJob)).all()
        assert job.kind == "build_run" and job.payload == {"run_id": run["id"]}
    assert c.post("/admin/audits/runs", json={"brands": ["Nope"]}).status_code == 422
    assert c.post("/admin/audits/runs", json={"brands": ["Camino"], "judge_model": "gpt"}).status_code == 422


def test_models_estimate_costs_per_model(world):
    got = _client().get("/admin/audits/models?sample_size=20").json()
    by = {m["id"]: m for m in got["models"]}
    assert set(by) == {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}
    assert by["claude-haiku-5-5"]["est_run_usd"] < by["claude-sonnet-5-5"]["est_run_usd"] < by["claude-opus-5-5"]["est_run_usd"]


def test_run_summary_error_rates_and_flag_precision(world):
    run_id = _run_with_items(world, [
        ("a", "flag", ["price-outlier"], "wrong"),
        ("b", "flag", ["price-outlier", "odd-title"], "right"),
        ("c", "sample", [], "right"),
        ("d", "sample", [], "unsure"),
    ])
    got = _client().get(f"/admin/audits/runs/{run_id}").json()
    summary = got["summary"]
    assert summary["all"]["error_rate"] == round(1 / 3, 3)
    assert summary["sample"] == {"items": 2, "judged": 2, "right": 1, "wrong": 0, "unsure": 1, "error_rate": 0.0}
    assert summary["flags"]["price-outlier"]["precision"] == 0.5
    assert summary["flags"]["odd-title"]["precision"] == 0.0
    assert len(got["items"]) == 4


def test_brand_health(world):
    _run_with_items(world, [("a", "flag", ["price"], None), ("c", "sample", [], "wrong")])
    (b,) = _client().get("/admin/audits/brands").json()["brands"]
    assert b["brand"] == "Camino" and b["listings"] == 4 and b["trusted"] == 3 and b["trusted_pct"] == 75.0
    assert b["review_backlog"] == 1
    assert b["open_flags"] == 1
    assert b["last_audit"]["sample"]["error_rate"] == 1.0


def test_manual_verdict_counts_once(world):
    run_id = _run_with_items(world, [("a", "sample", [], None)])
    c = _client()
    item = c.get(f"/admin/audits/runs/{run_id}").json()["items"][0]
    r = c.post(f"/admin/audits/items/{item['id']}/verdict", json={"verdict": "wrong", "cause": "wrong_size"})
    assert r.json()["judged_by"] == "manual:admin-1@example.com" and r.json()["cause"] == "wrong_size"
    c.post(f"/admin/audits/items/{item['id']}/verdict", json={"verdict": "right", "cause": "x"})
    run = c.get(f"/admin/audits/runs/{run_id}").json()
    assert run["run"]["judged_items"] == 1 and run["items"][0]["cause"] is None


def test_manual_match_reuses_the_review_path_and_logs(world):
    run_id = _run_with_items(world, [("b", "flag", ["price-outlier"], "wrong")])
    c = _client()
    item = c.get(f"/admin/audits/runs/{run_id}").json()["items"][0]
    assert c.post(f"/admin/audits/items/{item['id']}/manual-match", json={"entry_id": str(UUID(int=7))}).status_code == 422
    r = c.post(f"/admin/audits/items/{item['id']}/manual-match", json={"entry_id": str(world["e10"])})
    assert r.status_code == 200 and r.json()["fix"]["action"] == "manual-match"
    with Session(engine) as s:
        listing = s.get(Listing, world["b"])
        assert (listing.catalog_entry_id, listing.catalog_match_method) == (world["e10"], "manual")
        (log,) = s.exec(select(AuditLog)).all()
        assert log.before["catalog_entry_id"] == str(world["e20"]) and log.after["catalog_match_method"] == "manual"
    cands = c.get(f"/admin/audits/items/{item['id']}/candidates").json()["candidates"]
    assert {x["id"] for x in cands} >= {str(world["e10"])}


def test_store_error_is_recorded_and_logged(world):
    run_id = _run_with_items(world, [("a", "flag", ["price-outlier"], "wrong")])
    c = _client()
    item = c.get(f"/admin/audits/runs/{run_id}").json()["items"][0]
    r = c.post(f"/admin/audits/items/{item['id']}/store-error", json={"what": "price", "note": "sale"})
    assert r.json()["fix"]["action"] == "store-error"
    with Session(engine) as s:
        assert s.exec(select(AuditLog)).one().action == "store-error"
        assert s.get(Listing, world["a"]).catalog_match_method == "attributes"     # match untouched


def test_proposal_lifecycle(world):
    c = _client()
    assert c.post("/admin/audits/proposals", json={"kind": "add-size", "brand": "Camino",
                                                     "params": {"entry": "x"}}).status_code == 422
    assert c.post("/admin/audits/proposals", json={"kind": "nope", "brand": "Camino", "params": {}}).status_code == 422
    p = c.post("/admin/audits/proposals", json={"kind": "add-size", "brand": "Camino", "why": "2 stores sell 5pk",
                                                 "params": {"entry": str(world["e20"]), "size": "5pk 25mg"}}).json()
    assert p["status"] == "measuring"
    assert c.post(f"/admin/audits/proposals/{p['id']}/approve").status_code == 409     # not measured yet
    with Session(engine) as s:
        row = s.get(AuditProposal, UUID(p["id"]))
        row.status, row.measure = "measured", {"trusted_before": 3, "trusted_after": 4}
        s.add(row)
        s.commit()
    assert c.get("/admin/audits/proposals").json()["proposals"][0]["measure"]["trusted_after"] == 4
    edited = c.patch(f"/admin/audits/proposals/{p['id']}", json={"params": {"entry": str(world["e20"]), "size": "5pk"}})
    assert edited.json()["status"] == "measuring" and edited.json()["measure"] is None
    with Session(engine) as s:
        row = s.get(AuditProposal, UUID(p["id"]))
        row.status = "measured"
        s.add(row)
        s.commit()
    approved = c.post(f"/admin/audits/proposals/{p['id']}/approve").json()
    assert approved["status"] == "approved" and approved["decided_by"] == "admin-1@example.com"
    with Session(engine) as s:
        kinds = [j.kind for j in s.exec(select(AuditJob)).all()]
        assert kinds.count("measure_proposal") == 2 and kinds.count("apply_proposal") == 1
    assert c.post(f"/admin/audits/proposals/{p['id']}/reject", json={}).status_code == 409
    assert c.get("/admin/audits/proposals?status=decided").json()["proposals"] == []
