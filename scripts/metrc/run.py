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
import shutil
import sys
from datetime import datetime, timedelta, timezone

from .bootstrap import (
    facility_permissions,
    list_facilities,
    prepare_environment,
    request_user_key,
    seed_inventory,
)
from .client import MetrcClient
from .client import CallRecord, MetrcError, rows
from .config import ConfigError, MetrcConfig
from .recorder import Recorder
from .steps import (
    Context,
    get_transfers_and_wholesale,
    read_lab_results,
    read_sweep,
    run_full,
)
from .validate import load_records, to_json, validate
from .workbook import applicable_sheets, map_workbook, write_results

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
    resume = []
    for path in args.resume:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                resume.append(json.load(fh))
        else:
            print(f"  ! no environment at {path}", file=sys.stderr)

    env = prepare_environment(
        client,
        plant_tags=args.plant_tags,
        package_tags=args.package_tags,
        opening_packages=args.packages,
        resume=resume,
    )
    print(json.dumps({k: (v[:5] if isinstance(v, list) else v) for k, v in env.items()}, indent=2))
    path = os.path.join(recorder.run_dir, "environment.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(env, fh, indent=2)
    recorder.flush()
    print(f"\nwrote {path}")
    return 0


def cmd_get_only(args, config: MetrcConfig, recorder: Recorder) -> int:
    config.require("license_number")
    client = _client(config, recorder)
    ctx = Context(license_number=config.license_number)

    # Transfers and lab results may sit at a different facility than the one
    # being evaluated, so the read steps range over everything reachable.
    facilities = list_facilities(client)
    ctx.facilities = [
        (f.get("License") or {}).get("Number") or f.get("LicenseNumber")
        for f in facilities
    ]
    ctx.facilities = [lic for lic in ctx.facilities if lic]
    # Start with the configured facility so its data is preferred.
    if config.license_number in ctx.facilities:
        ctx.facilities.remove(config.license_number)
        ctx.facilities.insert(0, config.license_number)
    print(f"searching {len(ctx.facilities)} facilities\n")

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

        # Tags are single-use. Running against a stale environment spends tags
        # that are already consumed, and Metrc reports that as "Tag is not
        # valid" several steps later, which reads like a bug here.
        created = env.get("created_at")
        if created:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(created)
            if age > timedelta(hours=12):
                print(f"  ! this environment is {age.days}d {age.seconds // 3600}h old; "
                      "its tags are probably spent. Re-run bootstrap.", file=sys.stderr)
                return 1
        else:
            print("  ! environment has no created_at; cannot tell whether its tags "
                  "are still unused. Re-run bootstrap to be sure.", file=sys.stderr)
        if env.get("incomplete"):
            for item in env["incomplete"]:
                print(f"  ! bootstrap was incomplete — {item}", file=sys.stderr)
    else:
        print(f"no environment file at {env_path} — run `bootstrap` first", file=sys.stderr)
        return 1

    # Sales endpoints are unauthorized at a cultivator and grow endpoints at a
    # dispensary, so each tab runs where it is permitted.
    facilities = list_facilities(client)
    def _find(*needles):
        for f in facilities:
            name = (f.get("DisplayName") or "").lower()
            if all(n in name for n in needles):
                return (f.get("License") or {}).get("Number") or f.get("LicenseNumber")
        return None

    licenses = {
        "grow": config.license_number,
        "sales": args.sales_license or _find("dispensary"),
    }
    ctx.facilities = [
        (f.get("License") or {}).get("Number") or f.get("LicenseNumber") for f in facilities
    ]
    ctx.counterparty = args.recipient_license
    print(f"grow={licenses['grow']}  sales={licenses['sales']}"
          + (f"  recipient={ctx.counterparty}" if ctx.counterparty else ""))

    # The sales tabs need sellable inventory at the dispensary, which is a
    # different facility from the one bootstrap prepared.
    if licenses.get("sales") and licenses["sales"] != licenses["grow"]:
        with client.using(licenses["sales"]):
            existing = rows(
                client.get(
                    "/packages/v2/active", step="check inventory",
                    sheet="_bootstrap", raise_on_error=False,
                ).response_body
            )
            if not any((p.get("Quantity") or 0) > 1 for p in existing):
                try:
                    seed_inventory(client, ctx)
                    print(f"seeded inventory at {licenses['sales']}")
                except Exception as exc:
                    print(f"could not seed {licenses['sales']}: {exc}")

    only = set(args.only.split(",")) if args.only else None
    results = run_full(client, ctx, only=only, licenses=licenses)
    print()
    for name, status, detail in results:
        print(f"  {status:<18} {name:<28} {detail}")
    faults = [r for r in results if r[1] == "METRC SERVER FAULT"]
    if faults:
        print(f"\n{len(faults)} tab(s) blocked by a Metrc-side fault, not by the request. "
              "Retry later; nothing to change here.")

    summary_path = recorder.write_summary()
    print(f"\n{len(recorder.records)} calls recorded -> {recorder.run_dir}")
    print(f"summary: {summary_path}")
    return 1 if any(s != "ok" for _, s, _ in results) else 0


def cmd_fill(args, config: MetrcConfig, recorder: Recorder) -> int:
    src = args.workbook
    if not os.path.exists(src):
        print(f"workbook not found: {src}", file=sys.stderr)
        return 1

    # A complete evaluation is several runs — the read tabs and the write tabs
    # are separate passes — so runs merge, later ones winning per step.
    run_ids = [r.strip() for r in args.run.split(",") if r.strip()]
    replay = Recorder(config.run_dir, run_id=run_ids[-1])
    replay.records = []

    for run_id in run_ids:
        run_dir = run_id if os.path.isdir(run_id) else os.path.join(config.run_dir, run_id)
        calls_path = os.path.join(run_dir, "calls.jsonl")
        if not os.path.exists(calls_path):
            print(f"no transcript at {calls_path}", file=sys.stderr)
            return 1
        with open(calls_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    replay.records.append(CallRecord(**json.loads(line)))
    print(f"merged {len(run_ids)} run(s), {len(replay.records)} calls")

    company = {}
    if args.company and os.path.exists(args.company):
        with open(args.company, encoding="utf-8") as fh:
            company = {
                k: v for k, v in json.load(fh).items()
                if not k.startswith("_") and str(v).strip()
            }
    # The workbook asks for both API keys. They come from the environment at
    # fill time so they never need to live in a file that could be committed.
    if config.vendor_key:
        company["Vendor Key Used"] = config.vendor_key
    if config.user_key:
        company["User Key Used"] = config.user_key

    try:
        scope = applicable_sheets(src, config.state)
        print(f"{config.state.upper()} requires {len(scope)} tabs per the States matrix")
    except KeyError as exc:
        print(f"  {exc}; filling every tab", file=sys.stderr)
        scope = None

    permissions = None
    if args.permissions and os.path.exists(args.permissions):
        with open(args.permissions, encoding="utf-8") as fh:
            permissions = json.load(fh)

    # A refill from a worse run should not destroy a better workbook. Keep the
    # previous one alongside; runs against a flaky sandbox are not monotonic.
    if os.path.exists(args.out):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = f"{os.path.splitext(args.out)[0]}.{stamp}.xlsx"
        shutil.copy2(args.out, backup)
        print(f"  previous workbook kept at {backup}")

    written = write_results(
        src, args.out, replay, company=company,
        only_sheets=set(scope) if scope else None,
        permissions=permissions,
    )
    gaps = written.pop("_permission_gaps", [])
    for sheet, count in written.items():
        print(f"  {sheet}: {count} step(s)")
    if permissions:
        areas = [a for a, v in permissions.get("areas", {}).items() if v.get("get") or v.get("write")]
        print(f"  Permissions: {len(areas)} area(s) marked for "
              f"{', '.join(permissions.get('facility_types', [])) or 'no facility type'}")
        for gap in gaps:
            print(f"    ! {gap}")
    print(f"\nwrote {args.out}")

    # The same run, as data. A reviewer can diff it; the workbook they cannot.
    json_path = args.json or os.path.splitext(args.out)[0] + ".json"
    payload = to_json(args.out, replay.records, sheets=scope)
    payload["runs"] = run_ids
    payload["state"] = config.state
    payload["sandbox"] = config.sandbox
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"wrote {json_path}")

    # Filling without checking is how a blank cell reaches Metrc.
    report = validate(
        args.out, replay.records, sheets=scope,
        template_path=src if os.path.exists(src) else None,
        expected_host=config.base_url.split("//")[-1],
    )
    _print_report(report)
    return 0 if report.ok() else 1


def _print_report(report) -> None:
    print(f"\nvalidation: {report.cells_checked} cells, "
          f"{report.steps_ok}/{report.steps_total} steps at HTTP 200")
    for level, items in (("error", report.errors), ("warn", report.warnings)):
        for finding in items:
            print(f"  {finding}")
    info = [f for f in report.findings if f.level == "info"]
    if info:
        print(f"  ({len(info)} informational note(s); --verbose to show)")
    if report.errors:
        print(f"\n{len(report.errors)} error(s) — do not submit this workbook yet.")
    else:
        print("\nno errors.")


def cmd_validate(args, config: MetrcConfig, recorder: Recorder) -> int:
    run_dirs = [
        r if os.path.isdir(r) else os.path.join(config.run_dir, r)
        for r in (r.strip() for r in args.run.split(",")) if r
    ]
    missing = [d for d in run_dirs if not os.path.exists(f"{d}/calls.jsonl")]
    if missing:
        print(f"no transcript at: {', '.join(missing)}", file=sys.stderr)
        return 1

    records = load_records(run_dirs)
    try:
        scope = applicable_sheets(args.template, config.state)
    except (KeyError, FileNotFoundError):
        scope = None
    report = validate(
        args.workbook, records, sheets=scope,
        template_path=args.template if os.path.exists(args.template) else None,
        expected_host=config.base_url.split("//")[-1],
    )
    _print_report(report)
    if args.verbose:
        for finding in report.findings:
            if finding.level == "info":
                print(f"  {finding}")
    return 0 if report.ok() else 1


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
    p.add_argument("--resume", action="append", default=[],
                   help="carry unused tags forward from an earlier environment.json")
    p.set_defaults(fn=cmd_bootstrap)

    p = sub.add_parser("get-only", help="run the read-only evaluation")
    p.add_argument("--window", type=int, default=90, help="lastModified window in days")
    p.set_defaults(fn=cmd_get_only)

    p = sub.add_parser("full", help="run the write tabs (Locations -> Packages)")
    p.add_argument("--environment", default="", help="environment.json from bootstrap")
    p.add_argument("--only", default="", help="comma-separated tab names")
    p.add_argument("--sales-license", default="", help="facility for the sales tabs")
    p.add_argument(
        "--recipient-license", default="",
        help="counterparty licensee for transfers (e.g. a partner's facility)",
    )
    p.set_defaults(fn=cmd_full)

    p = sub.add_parser("fill", help="write a recorded run into the workbook")
    p.add_argument(
        "--run", required=True,
        help="run id or directory; comma-separate several to merge them",
    )
    p.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    p.add_argument("--out", default="evidence/metrc/Evaluation_completed.xlsx")
    p.add_argument("--company", default="evidence/metrc/company.json")
    p.add_argument("--json", default="", help="JSON output path (default: alongside --out)")
    p.add_argument("--permissions", default="evidence/metrc/permissions.json",
                   help="the access request to mark on the Permissions tab")
    p.set_defaults(fn=cmd_fill)

    p = sub.add_parser("validate", help="check a filled workbook against its transcript")
    p.add_argument("--run", required=True, help="run id(s), comma-separated")
    p.add_argument("--workbook", default="evidence/metrc/Evaluation_NY_completed.xlsx")
    p.add_argument("--template", default=DEFAULT_WORKBOOK)
    p.add_argument("--verbose", action="store_true", help="also show informational notes")
    p.set_defaults(fn=cmd_validate)

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
