"""
Lightweight metadata utilities shared by SNAPI extensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class CommandStatus:
    status: str
    message: str
    recorded_at: str = field(default_factory=utc_timestamp)
    extra: Dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> Dict[str, Any]:
        payload = {
            "status": self.status,
            "message": self.message,
            "recorded_at": self.recorded_at,
        }
        payload.update(self.extra)
        return payload
