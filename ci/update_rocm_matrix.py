#!/usr/bin/env python3
"""Backward-compatible shim for rocforge_ci.update."""
from __future__ import annotations

import sys

from rocforge_ci.update import cli

if __name__ == "__main__":
    sys.exit(cli())
