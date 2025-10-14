"""
Simple SNAPI (Snapshot Application Interface) runtime for Clamp.

This package exposes a minimal registry + dispatch surface that extensions can
register against. Commands are addressed using the ``extension.command`` form
and receive/return plain dictionaries to keep the integration friction-free.
"""

from __future__ import annotations

from dataclasses import dataclass
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


_GLOBAL_REGISTRY = ExtensionRegistry()


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
