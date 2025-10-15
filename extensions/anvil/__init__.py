"""
Anvil placeholder extension for future build orchestration.
"""

from __future__ import annotations

from snapi import register_extension

EXTENSION_ID = "anvil"
EXTENSION_VERSION = "0.0.1"


def _noop(_payload=None):
    return {
        "status": "noop",
        "message": "Anvil build orchestration not yet implemented",
    }


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["build"],
        commands={"describe": _noop},
        metadata={"phase": "planning"},
    )
