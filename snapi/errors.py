"""
Custom exceptions for the SNAPI registry/dispatch layer.
"""

from __future__ import annotations


class SNAPIError(RuntimeError):
    pass


class ExtensionAlreadyRegistered(SNAPIError):
    def __init__(self, extension_id: str) -> None:
        super().__init__(f"Extension '{extension_id}' already registered")
        self.extension_id = extension_id


class ExtensionNotFound(SNAPIError):
    def __init__(self, extension_id: str) -> None:
        super().__init__(f"Extension '{extension_id}' not found")
        self.extension_id = extension_id


class InvalidCommand(SNAPIError):
    def __init__(self, extension_id: str, command: str) -> None:
        super().__init__(f"Command '{command}' invalid for extension '{extension_id}'")
        self.extension_id = extension_id
        self.command = command
