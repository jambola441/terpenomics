"""Behaviour against a sandbox that fails most writes.

The NY sandbox spent weeks returning a server fault for most write calls, so
the runner has to retry the right things, stop retrying what is down, survive
being interrupted, and combine a partial fresh run with older evidence without
mixing the two inside a tab. None of this touches the network.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from .client import CallRecord, MetrcClient
from .config import MetrcConfig
from .steps import Context
from .validate import merge_by_tab

FAULT = (
    '{"Message":"Could not load file or assembly \'System.Data.SqlClient, '
    'Version=0.0.0.0\'. The system cannot find the file specified."}'
)


class _Resp:
    def __init__(self, code, text):
        self.status_code, self.text, self.headers = code, text, {}

    def json(self):
        return json.loads(self.text)


class TestRetries(unittest.TestCase):
    def _client(self, responses, retries=100):
        client = MetrcClient(MetrcConfig(
            vendor_key="v", user_key="u", server_fault_retries=retries,
        ))
        self.sent = 0

        def fake(*_args, **_kwargs):
            self.sent += 1
            return responses[min(self.sent - 1, len(responses) - 1)]

        patch_req = mock.patch.object(client.session, "request", side_effect=fake)
        patch_sleep = mock.patch("time.sleep")
        patch_req.start(); patch_sleep.start()
        self.addCleanup(patch_req.stop); self.addCleanup(patch_sleep.stop)
        return client

    def _post(self, client):
        return client.call("POST", "/strains/v2/", body=[{}],
                           license_number="L", raise_on_error=False)

    def test_a_fault_is_retried_until_it_clears(self):
        client = self._client([_Resp(400, FAULT)] * 5 + [_Resp(200, '{"Ids":[7]}')])
        record = self._post(client)
        self.assertEqual(record.status, 200)
        self.assertEqual(self.sent, 6)

    def test_a_real_rejection_is_not_retried(self):
        client = self._client([_Resp(400, '[{"row":0,"message":"Name was not specified."}]')])
        record = self._post(client)
        self.assertEqual(record.status, 400)
        self.assertEqual(self.sent, 1)
        self.assertFalse(record.server_fault)

    def test_an_endpoint_that_exhausts_the_budget_is_not_hammered_again(self):
        client = self._client([_Resp(400, FAULT)], retries=100)
        first = self._post(client)
        self.assertEqual(self.sent, 100)
        self.assertTrue(first.server_fault)
        self._post(client)
        self.assertEqual(self.sent, 101, "a dead endpoint should get one more attempt, not 100")


class TestCheckpoint(unittest.TestCase):
    def test_a_spent_tag_is_persisted_before_it_is_used(self):
        saved = []
        ctx = Context(plant_tags=["A", "B", "C"])
        ctx.persist = lambda: saved.append(list(ctx.plant_tags))
        self.assertEqual(ctx.take_plant_tag(), "A")
        self.assertEqual(saved[-1], ["B", "C"], "the taken tag must already be gone from the checkpoint")

    def test_state_round_trips(self):
        ctx = Context(license_number="L", plant_tags=["B"], package_tags=["P"],
                      created={"strain_name": "S"})
        restored = Context()
        restored.restore(json.loads(json.dumps(ctx.snapshot())))
        self.assertEqual(restored.snapshot(), ctx.snapshot())


def _rec(sheet, step, status, marker):
    return CallRecord(sheet=sheet, step=step, status=status, names=[marker])


class TestMergeByTab(unittest.TestCase):
    def test_a_complete_fresh_tab_replaces_the_old_one(self):
        base = [_rec("Plants", "Step 1", 200, "old"), _rec("Plants", "Step 2", 200, "old")]
        fresh = [_rec("Plants", "Step 1", 200, "new"), _rec("Plants", "Step 2", 200, "new")]
        merged, prov = merge_by_tab(base, fresh)
        self.assertEqual(prov["Plants"], "fresh")
        self.assertEqual({r.names[0] for r in merged if r.sheet == "Plants"}, {"new"})

    def test_a_partial_fresh_tab_never_mixes_with_the_old_one(self):
        base = [_rec("Plants", f"Step {i}", 200, "old") for i in (1, 2, 3)]
        fresh = [_rec("Plants", "Step 1", 200, "new"), _rec("Plants", "Step 2", 400, "new")]
        merged, prov = merge_by_tab(base, fresh)
        self.assertEqual(prov["Plants"], "base")
        self.assertEqual({r.names[0] for r in merged if r.sheet == "Plants"}, {"old"})

    def test_a_step_that_failed_before_does_not_block_a_fresh_tab(self):
        base = [_rec("Ext", "Step 1a", 401, "old"), _rec("Ext", "Step 2", 200, "old")]
        fresh = [_rec("Ext", "Step 1a", 401, "new"), _rec("Ext", "Step 2", 200, "new")]
        _, prov = merge_by_tab(base, fresh)
        self.assertEqual(prov["Ext"], "fresh")

    def test_a_tab_missing_from_the_fresh_run_is_kept(self):
        base = [_rec("Sales", "Step 1", 200, "old")]
        merged, prov = merge_by_tab(base, [_rec("Plants", "Step 1", 200, "new")])
        self.assertEqual(prov["Sales"], "base")
        self.assertEqual(prov["Plants"], "fresh")
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
