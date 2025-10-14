"""
Thin integration layer between RocForge CI and the Clamp SNAPI extension.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

from engine import bootstrap_extensions
from snapi import dispatch

_BOOTSTRAPPED = False


def _ensure_bootstrapped() -> None:
    global _BOOTSTRAPPED
    if not _BOOTSTRAPPED:
        bootstrap_extensions()
        _BOOTSTRAPPED = True


def clamp_manifest_path(base_dir: Path | str = Path("build/clamp"), filename: str = "manifest.json") -> Optional[Path]:
    base = Path(base_dir)
    candidate = base / filename
    if candidate.exists():
        return candidate.resolve()
    return None


def capture(payload: Optional[Mapping[str, Any]] = None) -> MutableMapping[str, Any]:
    _ensure_bootstrapped()
    return dispatch("clamp.capture", payload or {})


def restore(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    _ensure_bootstrapped()
    return dispatch("clamp.restore", payload)


def verify(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    _ensure_bootstrapped()
    return dispatch("clamp.verify", payload)


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
