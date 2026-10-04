"""The PreToolUse hook that auto-approves read-only SQL (.claude/hooks/readonly_sql.py).
A false 'read-only' skips a human's confirmation, so the cases that must prompt matter
more than the ones that may pass."""

import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "readonly_sql.py"
_spec = importlib.util.spec_from_file_location("readonly_sql", _path)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


@pytest.mark.parametrize("sql", [
    "SELECT count(*) FROM listings WHERE is_active",
    "WITH x AS (SELECT 1) SELECT * FROM x;",
    "SELECT pg_get_viewdef('products'::regclass, true)",
    "select 'drop table x' as s",
    "-- comment\nSELECT 1",
    "EXPLAIN SELECT 1",
    'SELECT "update" FROM t',
])
def test_reads_are_approved(sql):
    assert hook.is_read_only(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM listings",
    "WITH d AS (DELETE FROM listings RETURNING *) SELECT * FROM d",
    "SELECT * INTO t2 FROM listings",
    "SELECT 1; DROP TABLE x",
    "EXPLAIN ANALYZE DELETE FROM listings",
    "SELECT nextval('s')",
    "SELECT * FROM listings FOR UPDATE",
    "SELECT $$x$$",
    "SET ROLE postgres",
    # escape strings: a backslash escapes the quote, so the literal ends elsewhere
    "SELECT E'\\''; DELETE FROM listings; -- '\n",
    "SELECT e'a\\'b'",
    "SELECT U&'d\\0061t\\+000061'",
    "SELECT 'a\\'; DELETE FROM listings; --'",
])
def test_anything_else_prompts(sql):
    assert not hook.is_read_only(sql)
