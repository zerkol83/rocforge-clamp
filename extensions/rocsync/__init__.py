"""
Placeholder RocSync SNAPI extension.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from snapi import register_extension

EXTENSION_ID = "rocsync"
EXTENSION_VERSION = "0.0.0"


def _stub(_: Mapping[str, Any]) -> MutableMapping[str, Any]:
    return {
        "status": "noop",
        "message": "RocSync extension not implemented in this phase",
    }


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["sync"],
        commands={"describe": _stub},
        metadata={"phase": "foundation"},
    )
