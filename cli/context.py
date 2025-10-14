"""
Shared CLI context utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys


@dataclass
class CliContext:
    json_mode: bool = False
    quiet: bool = False
    verbose: bool = False
    color: bool = True

    def log(self, level: str, message: str) -> None:
        if self.quiet and level.lower() == "info":
            return
        formatted = f"[{level}] {message}" if self.verbose else message
        print(formatted, file=sys.stderr)

    def info(self, message: str) -> None:
        self.log("info", message)

    def warn(self, message: str) -> None:
        self.log("warn", message)

    def error(self, message: str) -> None:
        self.log("error", message)
