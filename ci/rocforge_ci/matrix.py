"""
Helpers for reading and writing ROCm image matrix metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

import yaml


@dataclass
class ImageMetadata:
    os_name: str
    image: str
    mirror: str | None = None
    canonical: str | None = None
    tarball: str | None = None
    sha256: str | None = None
    timestamp: str | None = None

    @property
    def preferred_image(self) -> str:
        return self.mirror or self.image

    @property
    def canonical_image(self) -> str:
        return self.canonical or self.image

    def as_dict(self) -> Dict[str, str]:
        payload: Dict[str, str] = {"image": self.image}
        if self.mirror and self.mirror != self.image:
            payload["mirror"] = self.mirror
        if self.canonical and self.canonical not in {self.image, self.mirror}:
            payload["canonical"] = self.canonical
        if self.tarball:
            payload["tarball"] = self.tarball
        if self.sha256:
            payload["sha256"] = self.sha256
        if self.timestamp:
            payload["timestamp"] = self.timestamp
        return payload


def load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=True)


def read_matrix(path: Path) -> Dict[str, ImageMetadata]:
    raw = load_yaml(path)
    entries: Dict[str, ImageMetadata] = {}
    for os_name, entry in raw.items():
        if isinstance(entry, str):
            metadata = ImageMetadata(os_name=os_name, image=entry, mirror=None, tarball=None, sha256=None)
        elif isinstance(entry, dict):
            image = str(entry.get("image") or "").strip()
            mirror = str(entry.get("mirror") or "").strip() or None
            canonical = str(entry.get("canonical") or "").strip() or None
            tarball = str(entry.get("tarball") or "").strip() or None
            sha256 = str(entry.get("sha256") or entry.get("hash") or "").strip() or None
            timestamp = str(entry.get("timestamp") or "").strip() or None
            metadata = ImageMetadata(
                os_name=os_name,
                image=image,
                mirror=mirror,
                canonical=canonical,
                tarball=tarball,
                sha256=sha256,
                timestamp=timestamp,
            )
        else:
            continue
        if metadata.image:
            entries[os_name] = metadata
    return entries


def write_matrix(path: Path, entries: Iterable[ImageMetadata]) -> None:
    payload = {entry.os_name: entry.as_dict() for entry in entries}
    write_yaml(path, payload)


def update_matrix_entry(path: Path, metadata: ImageMetadata) -> None:
    entries = read_matrix(path)
    entries[metadata.os_name] = metadata
    write_matrix(path, entries.values())
