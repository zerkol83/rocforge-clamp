"""
Convenience helpers for command dispatch.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from . import dispatch as _dispatch


def call(command: str, payload: Optional[Mapping[str, Any]] = None) -> MutableMapping[str, Any]:
    """
    Proxy to the process-global SNAPI dispatch entry point.
    """

    return _dispatch(command, payload)
