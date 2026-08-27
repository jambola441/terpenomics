"""CLI for the Metrc proficiency evaluation.

    python -m scripts.metrc.run setup-user          # mint a sandbox user key
    python -m scripts.metrc.run facilities          # list facilities + permissions
    python -m scripts.metrc.run bootstrap           # mint tags + opening packages
    python -m scripts.metrc.run get-only            # run the read-only evaluation
    python -m scripts.metrc.run fill --run <id>     # write a run into the workbook
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .bootstrap import (
    facility_permissions,
    list_facilities,
    prepare_environment,
    request_user_key,
)
from .client import MetrcClient
from .client import CallRecord, MetrcError
from .config import ConfigError, MetrcConfig
from .recorder import Recorder
from .steps import (
    Context,
    get_transfers_and_wholesale,
    read_lab_results,
    read_sweep,
    run_full,
)
from .workbook import map_workbook, write_results

DEFAULT_WORKBOOK = "evidence/metrc/Generic_Evaluation_for_All_States_MASTER_10.2025.xlsx"


def _client(config: MetrcConfig, recorder: Recorder) -> MetrcClient:
    return MetrcClient(config, recorder=recorder)


def cmd_setup_user(args, config: MetrcConfig, recorder: Recorder) -> int:
    client = _client(config, recorder)
    result = request_user_key(client, args.user_key or "")
    print(f"HTTP {result['status']}: {result['meaning']}")
    if result["body"]:
        print(f"body: {result['body']}")
    if result["status"] in (201, 202):
        print("\nRe-run this command in a minute, or check the contact email on file.")
        return 0
    if result["status"] == 200:
        print("\nSet METRC_USER_KEY to the value above and re-run `facilities`.")
        return 0
    if result["status"] == 204:
        print("\nNo setup exists for that key. Re-run without --user-key to create one.")
        return 1
    print("\nUnexpected status — check METRC_VENDOR_KEY.", file=sys.stderr)
    return 1


def cmd_facilities(args, config: MetrcConfig, recorder: Recorder) -> int:
    client = _client(config, recorder)
    facilities = list_facilities(client)
    if not facilities:
        print("no facilities returned — the user key may have no facility access")
        return 1
    for facility in facilities:
        lic = facility.get("License", {}).get("Number") or facility.get("LicenseNumber", "")
        print(f"\n{lic}  {facility.get('DisplayName', '')}")
        print(f"  type: {(facility.get('FacilityType') or {}).get('Name', '?')}")
        granted = [k for k, v in facility_permissions(facility).items() if v]
        print(f"  granted ({len(granted)}): {', '.join(sorted(granted)) or 'none'}")
    print("\nSet METRC_LICENSE_NUMBER to the license you want to evaluate against.")
    return 0


def cmd_bootstrap(args, config: MetrcConfig, recorder: Recorder) -> int:
    config.require("license_number")
    client = _client(config, recorder)
    env = prepare_environment(
        client,
        plant_tags=args.plant_tags,
        package_tags=args.package_tags,
        opening_packages=args.packages,
    )
    print(json.dumps({k: (v[:5] if isinstance(v, list) else v) for k, v in env.items()}, indent=2))
    path = os.path.join(recorder.run_dir, "environment.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(env, fh, indent=2)
    print(f"\nwrote {path}")
    return 0


def cmd_get_only(args, config: MetrcConfig, recorder: Recorder) -> int:
    config.require("license_number")
    client = _client(config, recorder)
    ctx = Context(license_number=config.license_number)

    failures = []
    for label, fn in [
        ("read sweep", lambda: read_sweep(client, ctx, window_days=args.window)),
        ("transfers tab", lambda: get_transfers_and_wholesale(client, ctx, window_days=args.window)),
        ("lab results", lambda: read_lab_results(client, ctx)),
    ]:
        try:
            fn()
            print(f"  ok   {label}")
        except Exception as exc:  # keep going: a partial run is still evidence
            failures.append((label, str(exc)))
            print(f"  FAIL {label}: {exc}")

    summary_path = recorder.write_summary()
    print(f"\n{len(recorder.records)} calls recorded -> {recorder.run_dir}")
    print(f"summary: {summary_path}")
    if failures:
        print(f"\n{len(failures)} section(s) incomplete — see above.")
    return 1 if failures else 0


def cmd_full(args, config: MetrcConfig, recorder: Recorder) -> int:
    """Run the write tabs. Needs tags and inventory — run `bootstrap` first."""
    config.require("license_number")
    client = _client(config, recorder)
    ctx = Context(license_number=config.license_number)

    env_path = args.environment
    if env_path and os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            env = json.load(fh)
        ctx.plant_tags = list(env.get("plant_tags") or [])
        ctx.package_tags = list(env.get("package_tags") or [])
        print(f"loaded {len(ctx.plant_tags)} plant / {len(ctx.package_tags)} package tags")
    else:
        print(f"no environment file at {env_path} — run `bootstrap` first", file=sys.stderr)
        return 1

    only = set(args.only.split(",")) if args.only else None
    results = run_full(client, ctx, only=only)
    print()
    for name, status, detail in results:
        print(f"  {status:<4} {name}" + (f": {detail}" if detail else ""))

    summary_path = recorder.write_summary()
    print(f"\n{len(recorder.records)} calls recorded -> {recorder.run_dir}")
    print(f"summary: {summary_path}")
    return 1 if any(s == "FAIL" for _, s, _ in results) else 0


def cmd_fill(args, config: MetrcConfig, recorder: Recorder) -> int:
    src = args.workbook
    if not os.path.exists(src):
        print(f"workbook not found: {src}", file=sys.stderr)
        return 1

    run_dir = args.run if os.path.isdir(args.run) else os.path.join(config.run_dir, args.run)
    calls_path = os.path.join(run_dir, "calls.jsonl")
    if not os.path.exists(calls_path):
        print(f"no transcript at {calls_path}", file=sys.stderr)
        return 1

    replay = Recorder(config.run_dir, run_id=os.path.basename(run_dir.rstrip("/")))
    replay.records = []
    with open(calls_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                replay.records.append(CallRecord(**json.loads(line)))

    company = None
    if args.company and os.path.exists(args.company):
        with open(args.company, encoding="utf-8") as fh:
            company = json.load(fh)

    written = write_results(src, args.out, replay, company=company)
    for sheet, count in written.items():
        print(f"  {sheet}: {count} step(s)")
    print(f"\nwrote {args.out}")
    return 0


def cmd_map(args, config: MetrcConfig, recorder: Recorder) -> int:
    for name, sm in map_workbook(args.workbook).items():
        print(f"\n{name}  (header row {sm.header_row})")
        print(f"  columns: {sm.columns}")
        for step, row in sm.steps.items():
            print(f"  {step:<9} row {row:<3} {sm.step_tasks.get(step, '')[:80]}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="metrc", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setup-user", help="mint or look up a sandbox industry user key")
    p.add_argument("--user-key", default="", help="existing key to look up")
    p.set_defaults(fn=cmd_setup_user)

    p = sub.add_parser("facilities", help="list facilities and their granted permissions")
    p.set_defaults(fn=cmd_facilities)

    p = sub.add_parser("bootstrap", help="mint tags and opening-balance packages")
    p.add_argument("--plant-tags", type=int, default=25)
    p.add_argument("--package-tags", type=int, default=25)
    p.add_argument("--packages", type=int, default=10)
    p.set_defaults(fn=cmd_bootstrap)

    p = sub.add_parser("get-only", help="run the read-only evaluation")
    p.add_argument("--window", type=int, default=90, help="lastModified window in days")
    p.set_defaults(fn=cmd_get_only)

    p = sub.add_parser("full", help="run the write tabs (Locations -> Packages)")
    p.add_argument("--environment", default="", help="environment.json from bootstrap")
    p.add_argument("--only", default="", help="comma-separated tab names")
    p.set_defaults(fn=cmd_full)

    p = sub.add_parser("fill", help="write a recorded run into the workbook")
    p.add_argument("--run", required=True, help="run id or directory")
    p.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    p.add_argument("--out", default="evidence/metrc/Evaluation_completed.xlsx")
    p.add_argument("--company", default="evidence/metrc/company.json")
    p.set_defaults(fn=cmd_fill)

    p = sub.add_parser("map", help="print the workbook's derived cell map")
    p.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    p.set_defaults(fn=cmd_map)

    args = parser.parse_args(argv)
    config = MetrcConfig.from_env()
    recorder = Recorder(config.run_dir)

    try:
        return args.fn(args, config, recorder)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except MetrcError as exc:
        record = exc.record
        print(f"\n{record.method} {record.path} -> HTTP {record.status}", file=sys.stderr)
        if record.status == 401:
            print(
                "  Invalid or missing credentials. Both keys are required: basic auth\n"
                "  with the vendor key as username and the industry user key as password.",
                file=sys.stderr,
            )
        elif record.status == 403:
            print("  The user key lacks permission for this facility.", file=sys.stderr)
        elif record.status == 400:
            print(f"  {record.response_body}", file=sys.stderr)
        print(f"\n  transcript: {recorder.run_dir}/calls.jsonl", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
