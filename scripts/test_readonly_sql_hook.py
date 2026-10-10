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


# --- the same check reached through `scripts/db_http.py sql` in Bash ---------------

REPO = str(hook.REPO)


@pytest.mark.parametrize("command", [
    'python3 scripts/db_http.py sql "SELECT count(*) FROM listings"',
    "python scripts/db_http.py sql 'SELECT 1'",
    f'python3 {REPO}/scripts/db_http.py sql "SELECT 1"',
    f'cd {REPO} && python3 scripts/db_http.py sql "SELECT 1"',
    'python3 scripts/db_http.py sql "SELECT a FROM t WHERE b > 1 AND c <> 2" 2>&1 | head -50',
    'python3 scripts/db_http.py sql "SELECT 1" | tail -n 20',
    "python3 scripts/db_http.py sql \"SELECT product_line FROM listings WHERE x = 'a|b; c'\"",
    # the shape agents actually write: a time limit and SQL over several lines
    'timeout 120 python scripts/db_http.py sql "\nWITH l AS (\n  SELECT 1 AS n\n)\nSELECT n FROM l" 2>&1 | head -40',
    f'cd {REPO} && timeout 90s python3 scripts/db_http.py sql "SELECT 1"',
    # output piped through text filters
    'timeout 90 python scripts/db_http.py sql "SELECT 1" 2>&1 | grep -iE \'view|create\' | head',
    "python3 scripts/db_http.py sql \"SELECT 1\" 2>&1 | tr -d '\\n '; echo",
    "python3 scripts/db_http.py sql \"SELECT 1\" | jq -r '.[] | .n' | sort -rn | uniq -c | wc -l",
    'python3 scripts/db_http.py sql "SELECT 1" 2>/dev/null | cut -c1-200',
])
def test_bash_reads_are_approved(command):
    queries = hook.sqls_from_bash(command, REPO)
    assert queries and all(hook.is_read_only(q) for q in queries)


@pytest.mark.parametrize("command", [
    'python3 scripts/db_http.py sql "SELECT 1"; rm -rf data',
    'python3 scripts/db_http.py sql "SELECT 1" && curl example.com',
    'python3 scripts/db_http.py sql "SELECT 1" | sh',
    'python3 scripts/db_http.py sql "SELECT 1" | head -5 | sh',
    'python3 scripts/db_http.py sql "SELECT 1" > out.json',
    'python3 scripts/db_http.py sql "SELECT 1" &',
    'python3 scripts/db_http.py sql "SELECT $(rm -rf data)"',
    'python3 scripts/db_http.py sql "SELECT `id`"',
    "python3 scripts/db_http.py sql - <<'EOF'\nSELECT 1\nEOF",
    'python3 scripts/db_http.py update listings "id=eq.1" \'{"x":1}\'',
    'python3 scripts/other.py sql "SELECT 1"',
    'X=1 python3 scripts/db_http.py sql "SELECT 1"',
    'cd /tmp && python3 scripts/db_http.py sql "SELECT 1"',
    'python3 /tmp/scripts/db_http.py sql "SELECT 1"',
    'python3 -c "import os" scripts/db_http.py sql "SELECT 1"',
    'python3 scripts/db_http.py sql "SELECT 1',
    'python3 scripts/db_http.py sql "SELECT 1"\nrm -rf data',
    'timeout 5 python3 scripts/db_http.py sql "SELECT 1"\nDELETE FROM x',
    'timeout python3 scripts/db_http.py sql "SELECT 1"',
    'timeout -s KILL 5 python3 scripts/db_http.py sql "SELECT 1"',
    'python3 scripts/db_http.py sql "SELECT \\" ; rm x; \\""',
    # a pipe into a program, a second command, or a filter used to write a file
    'python3 scripts/db_http.py sql "SELECT 1" | python3 -c "import sys"',
    'python3 scripts/db_http.py sql "SELECT 1" 2>&1; sed -n 1,30p models.py',
    'python3 scripts/db_http.py sql "SELECT 1" | sort -o out.txt',
    'python3 scripts/db_http.py sql "SELECT 1" | sort -rn -o out.txt',
    'python3 scripts/db_http.py sql "SELECT 1" | sort --compress-program=sh',
    'python3 scripts/db_http.py sql "SELECT 1" | uniq - out.txt',
    "python3 scripts/db_http.py sql \"SELECT 1\" | tr -d '\\n'; echo; rm x",
    'python3 scripts/db_http.py sql "SELECT 1" || rm x',
    'python3 scripts/db_http.py sql "SELECT 1"; cd /tmp',
    f'python3 scripts/db_http.py sql "SELECT 1"; cd {REPO}',
    'echo',
    'python3 scripts/db_http.py sql "SELECT 1" | grep x > out.txt',
    'python3 scripts/db_http.py sql "SELECT 1" | grep -i "a\\|b"',
])
def test_other_bash_is_not_read_as_sql(command):
    assert hook.sqls_from_bash(command, REPO) is None


def test_bash_write_is_found_but_not_read_only():
    queries = hook.sqls_from_bash('python3 scripts/db_http.py sql "DELETE FROM listings"', REPO)
    assert queries == ["DELETE FROM listings"] and not hook.is_read_only(queries[0])


def test_bash_from_another_directory_is_not_this_repos_script():
    assert hook.sqls_from_bash('python3 scripts/db_http.py sql "SELECT 1"', "/tmp") is None


def test_chained_reads_are_all_checked():
    reads = 'python3 scripts/db_http.py sql "SELECT 1" 2>&1; timeout 9 python3 scripts/db_http.py sql "SELECT 2" | tr -d x'
    assert hook.sqls_from_bash(reads, REPO) == ["SELECT 1", "SELECT 2"]
    mixed = 'python3 scripts/db_http.py sql "SELECT 1" && python3 scripts/db_http.py sql "DROP TABLE x"'
    queries = hook.sqls_from_bash(mixed, REPO)
    assert queries and not all(hook.is_read_only(q) for q in queries)
