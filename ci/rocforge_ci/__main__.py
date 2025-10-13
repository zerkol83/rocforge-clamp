"""
CLI entry point for ROCForge-CI utilities.

Usage:
    python -m rocforge_ci resolve [args...]
    python -m rocforge_ci verify [args...]
    python -m rocforge_ci update [args...]
"""

from __future__ import annotations

import argparse
import sys

from . import resolve_module, update_module, verify_module


COMMANDS = {
    "resolve": lambda argv: resolve_module().cli(argv),
    "verify": lambda argv: verify_module().cli(argv),
    "update": lambda argv: update_module().cli(argv),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rocforge-ci", description="ROCForge CI orchestrator")
    parser.add_argument("command", choices=sorted(COMMANDS.keys()), help="Command to execute")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the sub-command")
    parsed = parser.parse_args(argv)

    handler = COMMANDS.get(parsed.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(parsed.args)


if __name__ == "__main__":
    sys.exit(main())
