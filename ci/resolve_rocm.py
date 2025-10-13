#!/usr/bin/env python3
"""Backward-compatible shim for rocforge_ci.resolve."""
from __future__ import annotations

import sys

from rocforge_ci.resolve import cli

if __name__ == "__main__":
    sys.exit(cli())
