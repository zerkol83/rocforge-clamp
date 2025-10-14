"""
RocFoundry command-line entry point.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, Optional

from cli.commands import clamp as clamp_cmd
from cli.context import CliContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rocfoundry",
        description="RocFoundry command-line interface",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress non-critical logs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Increase logging verbosity")
    parser.add_argument("--no-color", action="store_true", help="Disable terminal colors")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    clamp_cmd.add_parser(subparsers)
    return parser


def configure_context(args: argparse.Namespace) -> CliContext:
    return CliContext(
        json_mode=getattr(args, "json", False),
        quiet=getattr(args, "quiet", False),
        verbose=getattr(args, "verbose", False),
        color=not getattr(args, "no_color", False),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = configure_context(args)

    if args.command == "clamp":
        result = clamp_cmd.handle(ctx, args)
    else:
        parser.print_help()
        return 1

    if ctx.json_mode and isinstance(result, Dict):
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return clamp_cmd.extract_exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
