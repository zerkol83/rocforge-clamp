"""
SNAPI diagnostics extension backed by the legacy ROCForge diagnostics module.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from ci.rocforge_ci.diagnostics import collect_diagnostics
from snapi import register_extension

EXTENSION_ID = "diagnostics"
EXTENSION_VERSION = "0.1.0"


def _snapshot(_: Mapping[str, Any]) -> MutableMapping[str, Any]:
    info = collect_diagnostics()
    return {
        "status": "ok",
        "message": "Diagnostic snapshot captured",
        "diagnostics": info,
    }


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["diagnostics"],
        commands={"snapshot": _snapshot},
        metadata={"source": "rocforge_ci"},
    )
