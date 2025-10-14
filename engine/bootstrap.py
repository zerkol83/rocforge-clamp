"""
Bootstraps built-in SNAPI extensions.
"""

from __future__ import annotations

import importlib
from typing import Dict

from snapi import ExtensionRecord

_KNOWN_EXTENSIONS = (
    "extensions.diagnostics",
    "extensions.clamp",
    "extensions.rocsync",
    "extensions.telemetry",
)


def bootstrap_extensions() -> Dict[str, Dict]:
    """
    Import the built-in extensions and register them with the SNAPI runtime.

    Returns a mapping keyed by extension id describing each registered extension.
    """

    registered: Dict[str, Dict] = {}
    for module_name in _KNOWN_EXTENSIONS:
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if callable(register):
            record: ExtensionRecord = register()
            registered[record.extension_id] = record.describe()
    return registered
