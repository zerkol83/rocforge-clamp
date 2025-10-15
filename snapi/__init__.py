"""
Simple SNAPI (Snapshot Application Interface) runtime for Clamp.

This package exposes a minimal registry + dispatch surface that extensions can
register against. Commands are addressed using the ``extension.command`` form
and receive/return plain dictionaries to keep the integration friction-free.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional

from .errors import ExtensionAlreadyRegistered, ExtensionNotFound, InvalidCommand

__all__ = [
    "CommandPayload",
    "CommandResult",
    "CommandSpec",
    "CommandHandler",
    "ExtensionRecord",
    "ExtensionRegistry",
    "register_extension",
    "describe_extension",
    "dispatch",
    "registry",
    "unregister_extension",
    "load_extension",
    "unload_extension",
    "list_loaded",
]

CommandPayload = Mapping[str, Any]
CommandResult = MutableMapping[str, Any]
CommandHandler = Callable[[CommandPayload], CommandResult]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: CommandHandler
    description: Optional[str] = None


@dataclass
class ExtensionRecord:
    extension_id: str
    version: str
    capabilities: Iterable[str]
    commands: Dict[str, CommandSpec]
    metadata: Dict[str, Any]

    def describe(self) -> Dict[str, Any]:
        return {
            "id": self.extension_id,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "commands": sorted(self.commands.keys()),
            "metadata": dict(self.metadata),
        }


class ExtensionRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, ExtensionRecord] = {}

    def register(
        self,
        *,
        extension_id: str,
        version: str,
        capabilities: Iterable[str],
        commands: Mapping[str, CommandHandler],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ExtensionRecord:
        if extension_id in self._registry:
            raise ExtensionAlreadyRegistered(extension_id)
        command_entries = {
            command: CommandSpec(name=command, handler=handler)
            for command, handler in commands.items()
        }
        record = ExtensionRecord(
            extension_id=extension_id,
            version=version,
            capabilities=list(capabilities),
            commands=command_entries,
            metadata=dict(metadata or {}),
        )
        self._registry[extension_id] = record
        return record

    def get(self, extension_id: str) -> ExtensionRecord:
        try:
            return self._registry[extension_id]
        except KeyError as exc:
            raise ExtensionNotFound(extension_id) from exc

    def dispatch(self, extension_id: str, command: str, payload: Optional[CommandPayload] = None) -> CommandResult:
        record = self.get(extension_id)
        try:
            spec = record.commands[command]
        except KeyError as exc:
            raise InvalidCommand(extension_id, command) from exc
        return spec.handler(payload or {})

    def extensions(self) -> Iterable[ExtensionRecord]:
        return self._registry.values()

    def unregister(self, extension_id: str) -> None:
        self._registry.pop(extension_id, None)


_GLOBAL_REGISTRY = ExtensionRegistry()
SNAPI_REGISTRY: Dict[str, "LoadedExtension"] = {}


@dataclass
class LoadedExtension:
    module_name: str
    module: ModuleType
    extension_id: Optional[str]
    record: Optional[ExtensionRecord]


def register_extension(
    extension_id: str,
    *,
    version: str,
    capabilities: Iterable[str],
    commands: Mapping[str, CommandHandler],
    metadata: Optional[Mapping[str, Any]] = None,
) -> ExtensionRecord:
    """
    Register a new extension with the process-global registry.
    """

    return _GLOBAL_REGISTRY.register(
        extension_id=extension_id,
        version=version,
        capabilities=capabilities,
        commands=commands,
        metadata=metadata,
    )


def describe_extension(extension_id: str) -> Dict[str, Any]:
    return _GLOBAL_REGISTRY.get(extension_id).describe()


def dispatch(command: str, payload: Optional[CommandPayload] = None) -> CommandResult:
    """
    Dispatch a command using the ``extension.command`` addressing convention.
    """

    if "." not in command:
        raise InvalidCommand("<unknown>", command)
    extension_id, command_name = command.split(".", 1)
    return _GLOBAL_REGISTRY.dispatch(extension_id, command_name, payload)


def registry() -> ExtensionRegistry:
    return _GLOBAL_REGISTRY


def unregister_extension(extension_id: str) -> None:
    """
    Remove a previously registered extension from the command registry.
    """

    _GLOBAL_REGISTRY.unregister(extension_id)


def _normalize_module_name(module_name: str) -> tuple[str, str]:
    if not module_name:
        raise ValueError("module_name must be provided")
    if "." not in module_name:
        qualified = f"extensions.{module_name}"
    else:
        qualified = module_name
    key = qualified.split(".", maxsplit=1)[-1]
    return qualified, key


def load_extension(module_name: str) -> Optional[ExtensionRecord]:
    qualified, key = _normalize_module_name(module_name)
    if key in SNAPI_REGISTRY:
        return SNAPI_REGISTRY[key].record

    module = importlib.import_module(qualified)
    register_fn = getattr(module, "register", None)
    record: Optional[ExtensionRecord] = None
    extension_id: Optional[str] = None
    if callable(register_fn):
        record = register_fn()
        if isinstance(record, ExtensionRecord):
            extension_id = record.extension_id
    SNAPI_REGISTRY[key] = LoadedExtension(
        module_name=qualified,
        module=module,
        extension_id=extension_id,
        record=record,
    )
    print(f"[✓] SNAPI loaded: {key}")
    return record


def unload_extension(module_name: str) -> None:
    qualified, key = _normalize_module_name(module_name)
    handle = SNAPI_REGISTRY.pop(key, None)
    if not handle:
        return

    unregister_fn = getattr(handle.module, "unregister", None)
    if callable(unregister_fn):
        unregister_fn()
    if handle.extension_id:
        _GLOBAL_REGISTRY.unregister(handle.extension_id)
    sys.modules.pop(handle.module.__name__, None)
    sys.modules.pop(qualified, None)
    print(f"[⏹] SNAPI unloaded: {key}")


def list_loaded() -> list[str]:
    return list(SNAPI_REGISTRY.keys())
