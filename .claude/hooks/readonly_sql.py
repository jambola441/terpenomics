#!/usr/bin/env python3
"""
PreToolUse hook: auto-approve read-only SQL, from either path that runs it —
mcp__Supabase__execute_sql, or `python3 scripts/db_http.py sql "<query>"` in Bash.

Approves a query only when every check passes; anything else falls through to the
normal permission prompt (exit 0, no output). It never denies — a write is still
possible, it just has to be confirmed by a person.

A Bash command is read only in one exact shape (`sql_from_bash`): an optional
`cd <this repo> &&`, then python/python3 running this repo's scripts/db_http.py with
`sql` and one argument, optionally followed by `2>&1` and a pipe into head or tail.
Anything else — another script, env assignments, `$`/backticks, `;`, a heredoc —
prompts as before.

Conservative by construction:
  - exactly one statement (a trailing semicolon is fine)
  - it starts with SELECT / WITH / EXPLAIN / SHOW / TABLE / VALUES
  - no write or session keyword anywhere outside string literals and quoted
    identifiers — this catches data-modifying CTEs (WITH x AS (DELETE ...)),
    SELECT ... INTO (creates a table), FOR UPDATE row locks, EXPLAIN ANALYZE
    (which executes its statement), SET ROLE, COPY, CALL, DO, ...
  - no call to a built-in function with side effects (nextval, set_config,
    pg_terminate_backend, advisory locks, file/large-object access, dblink, ...)

Known limit: a user-defined function with side effects called from a SELECT is not
detectable from the text. This is a guard against accidental writes, not a sandbox.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

# .claude/hooks/readonly_sql.py -> the repo root
REPO = Path(__file__).resolve().parents[2]
DB_HTTP = REPO / "scripts" / "db_http.py"

STARTERS = {"select", "with", "explain", "show", "table", "values"}

WRITE_KEYWORDS = {
    "insert", "update", "delete", "merge", "upsert", "create", "alter", "drop",
    "truncate", "grant", "revoke", "copy", "vacuum", "analyze", "analyse", "reindex",
    "cluster", "refresh", "comment", "lock", "call", "do", "set", "reset", "into",
    "execute", "prepare", "deallocate", "listen", "notify", "unlisten", "import",
    "load", "discard", "begin", "commit", "rollback", "savepoint", "release",
    "checkpoint", "security", "owner",
}

SIDE_EFFECT_FUNCS = re.compile(
    r"\b(nextval|setval|set_config|pg_terminate_backend|pg_cancel_backend|"
    r"pg_advisory\w*|pg_try_advisory\w*|lo_\w+|pg_read\w*|pg_ls\w*|pg_stat_reset\w*|"
    r"pg_reload_conf|pg_rotate_logfile|pg_switch_wal|pg_create\w*|pg_drop\w*|"
    r"pg_logical\w*|pg_promote|pg_file\w*|pg_replication\w*|pg_sleep\w*|"
    r"dblink\w*|http\w*|net\.\w+)\s*\(",
    re.I,
)


def _strip(sql: str) -> str | None:
    """Remove comments and blank out literals/quoted identifiers.

    Returns None on anything we do not parse with confidence (dollar quoting,
    unterminated literals) so the caller falls back to a prompt.
    """
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j < 0:
                return None
            i = j + 2
            out.append(" ")
            continue
        if c == "$":
            return None  # dollar-quoted bodies can hide anything; let a human look
        if c == "'" and i > 0 and sql[i - 1] in "eEuU&":
            # E'...' (a backslash escapes the quote) and U&'...' change what ends a
            # literal; "E'\''; DELETE ...; -- '" would otherwise read as one string.
            return None
        if c in ("'", '"'):
            j = i + 1
            while True:
                j = sql.find(c, j)
                if j < 0:
                    return None
                if j + 1 < n and sql[j + 1] == c:  # doubled quote = escaped
                    j += 2
                    continue
                break
            if "\\" in sql[i:j]:
                return None  # a backslash in a literal: not worth reasoning about
            out.append(" ''" if c == "'" else ' "x" ')
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def is_read_only(sql: str) -> bool:
    text = _strip(sql or "")
    if text is None:
        return False
    statements = [s for s in text.split(";") if s.strip()]
    if len(statements) != 1:
        return False
    words = re.findall(r"[a-z_][a-z0-9_]*", statements[0].lower())
    if not words or words[0] not in STARTERS:
        return False
    if WRITE_KEYWORDS.intersection(words):
        return False
    if SIDE_EFFECT_FUNCS.search(statements[0]):
        return False
    return True


def _same_file(path: str, cwd: Path) -> bool:
    p = Path(path)
    try:
        return (p if p.is_absolute() else cwd / p).resolve() == DB_HTTP
    except OSError:
        return False


def _is_pager(tokens: list[str]) -> bool:
    """`head`/`tail` with only flags and counts, e.g. `head -50`, `tail -n 20`."""
    return (bool(tokens) and tokens[0] in ("head", "tail")
            and all(re.fullmatch(r"-?[A-Za-z0-9]+", t) for t in tokens[1:]))


def sql_from_bash(command: str, cwd: str | None) -> str | None:
    """The SQL of a `db_http.py sql "<query>"` command, or None for any other command."""
    # `$` and backticks expand inside double quotes; a newline could start a second
    # command or a heredoc. None of them is needed by the shape we accept.
    if any(ch in command for ch in "$`\n\r"):
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None

    here = Path(cwd or os.getcwd())
    if tokens[:1] == ["cd"]:
        if len(tokens) < 3 or tokens[2] != "&&":
            return None
        target = Path(tokens[1])
        target = target if target.is_absolute() else here / target
        try:
            if target.resolve() != REPO:
                return None
        except OSError:
            return None
        here, tokens = REPO, tokens[3:]

    if len(tokens) < 4 or tokens[0] not in ("python", "python3"):
        return None
    if not _same_file(tokens[1], here) or tokens[2] != "sql":
        return None
    query, rest = tokens[3], tokens[4:]
    if query == "-":
        return None  # reads the SQL from stdin, which we cannot see

    if rest[:3] == ["2", ">&", "1"]:
        rest = rest[3:]
    if rest:
        if rest[0] != "|" or not _is_pager(rest[1:]):
            return None
    return query


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "Bash":
        query = sql_from_bash(tool_input.get("command") or "", payload.get("cwd"))
        if query is None:
            return
    else:
        query = tool_input.get("query") or ""
    if is_read_only(query):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "read-only SQL (auto-approved by .claude/hooks/readonly_sql.py)",
        }}))


if __name__ == "__main__":
    main()
