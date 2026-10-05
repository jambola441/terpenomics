from backfill_customer_phone_e164 import plan


def test_plan_respells_skips_and_reports():
    rows = [
        {"id": "a", "phone": "16462606799"},      # JWT spelling
        {"id": "b", "phone": "+15035554869"},     # already E.164
        {"id": "c", "phone": "(503) 555-0001"},   # hand-typed
        {"id": "d", "phone": "+15035550001"},     # same number as c
        {"id": "e", "phone": "12345"},            # junk
    ]
    changes, unparseable, collisions = plan(rows)
    assert changes == [("a", "16462606799", "+16462606799")]
    assert unparseable == ["e"]
    assert collisions == [["c", "d"]]
