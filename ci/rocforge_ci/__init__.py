"""
ROCForge-CI toolkit.

Provides resolve, verify, and update commands for ROCm image metadata,
decoupled from the Clamp runtime.
"""

from importlib import import_module

__all__ = ["resolve_module", "verify_module", "update_module"]


def resolve_module():
    return import_module(".resolve", __name__)


def verify_module():
    return import_module(".verify", __name__)


def update_module():
    return import_module(".update", __name__)
