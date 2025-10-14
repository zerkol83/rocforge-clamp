"""
Utility helpers for writing per-run telemetry blobs for RocForge CI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def record_run(
    *,
    mode: str,
    clamp_manifest_path: Optional[str],
    verify_status: Optional[str],
    verify_message: Optional[str] = None,
    output_path: Path | str = Path("build/run.json"),
    extra: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = {
        "mode": mode,
        "timestamp": _timestamp(),
        "clamp_manifest_path": clamp_manifest_path,
        "verify_status": verify_status,
    }
    if verify_message:
        payload["verify_message"] = verify_message
    if extra:
        payload.update(dict(extra))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
