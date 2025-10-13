#!/usr/bin/env python3
"""Backward-compatible shim for rocforge_ci.verify."""
from __future__ import annotations

import sys

from rocforge_ci.verify import cli

if __name__ == "__main__":
    sys.exit(cli())
