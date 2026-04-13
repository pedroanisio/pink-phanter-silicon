import argparse
import sys
from pathlib import Path

from .engine import Engine
from .models import Command, EngineInput


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codebase-refactor",
        description="Scan, plan, and execute structural codebase refactors.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- scan --
    scan_p = sub.add_parser("scan", help="Scan a directory and propose a refactor plan")
    scan_p.add_argument("root_dir", help="Root directory to scan")
    scan_p.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Glob pattern to ignore (repeatable)",
    )
    scan_p.add_argument(
        "--out",
        default=None,
        help="Write plan YAML to this file (default: stdout)",
    )
    scan_p.add_argument("--check-invariants", action="store_true", default=False)
    scan_p.add_argument("-v", "--verbose", action="store_true", default=False)

    # -- execute --
    exec_p = sub.add_parser("execute", help="Execute a refactor plan")
    exec_p.add_argument("root_dir", help="Root directory to refactor")
    exec_p.add_argument(
        "--plan",
        required=True,
        help="Path to plan YAML file",
    )
    exec_p.add_argument("--dry-run", action="store_true", default=False)
    exec_p.add_argument(
        "--backup-dir",
        default=".refactor-backup",
        help="Name of backup directory (default: .refactor-backup)",
    )
    exec_p.add_argument("--check-invariants", action="store_true", default=False)
    exec_p.add_argument("-v", "--verbose", action="store_true", default=False)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    plan_yaml = None
    if args.command == "execute":
        try:
            with Path(args.plan).open(encoding="utf-8") as f:
                plan_yaml = f.read()
        except OSError as e:
            print(f"Error reading plan file: {e}", file=sys.stderr)
            return 2

    inp = EngineInput(
        command=Command.SCAN if args.command == "scan" else Command.EXECUTE,
        root_dir=args.root_dir,
        plan_yaml=plan_yaml,
        dry_run=getattr(args, "dry_run", False),
        extra_ignore=getattr(args, "ignore", []),
        backup_dir_name=getattr(args, "backup_dir", ".refactor-backup"),
    )

    try:
        engine = Engine(inp, check_invariants=args.check_invariants)
        output = engine.run()
    except (OSError, RuntimeError, ValueError) as e:
        print(f"Internal error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        for line in output.log:
            print(line, file=sys.stderr)

    if output.error_message:
        print(f"FAILED: {output.error_message}", file=sys.stderr)
        return 1

    if args.command == "scan" and output.plan_yaml:
        out_dest = getattr(args, "out", None)
        if out_dest:
            with Path(out_dest).open("w", encoding="utf-8") as f:
                f.write(output.plan_yaml)
            print(f"Plan written to {out_dest}", file=sys.stderr)
        else:
            print(output.plan_yaml)

    if args.command == "execute" and output.report_json:
        print(output.report_json)

    return 0
