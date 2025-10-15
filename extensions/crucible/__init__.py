"""
Crucible placeholder extension for future automation flows.
"""

from __future__ import annotations

from snapi import register_extension

EXTENSION_ID = "crucible"
EXTENSION_VERSION = "0.0.1"


def _noop(_payload=None):
    return {
        "status": "noop",
        "message": "Crucible automation hooks not yet implemented",
    }


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["automation"],
        commands={"describe": _noop},
        metadata={"phase": "planning"},
    )
