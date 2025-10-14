"""
Telemetry SNAPI extension (stub).
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from snapi import register_extension

EXTENSION_ID = "telemetry"
EXTENSION_VERSION = "0.1.0"


def _record(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    return {
        "status": "ok",
        "message": "Telemetry record accepted",
        "record": dict(payload),
    }


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["record"],
        commands={"record": _record},
        metadata={"persistence": "memory"},
    )
