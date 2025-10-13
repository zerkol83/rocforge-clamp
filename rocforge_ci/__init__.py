"""
Convenience shim that exposes the ROCForge-CI package located under ./ci.
"""

from importlib import import_module

_PKG = import_module("ci.rocforge_ci")

resolve_module = _PKG.resolve_module
verify_module = _PKG.verify_module
update_module = _PKG.update_module
