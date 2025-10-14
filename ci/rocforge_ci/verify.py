"""
Verify ROCm image integrity against the cached matrix.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .matrix import ImageMetadata, read_matrix
from .resolve import ResolveError, compute_docker_image_sha256, compute_file_sha256

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PACKAGE_ROOT / "rocm_matrix.yml"


class VerificationStatus:
    OK = 0
    FAIL = 2


@dataclass
class VerificationResult:
    metadata: ImageMetadata
    mode: str
    sha256: Optional[str]

    def to_json(self) -> str:
        payload = {
            "image": self.metadata.image,
            "mirror": self.metadata.mirror,
            "canonical": self.metadata.canonical,
            "tarball": self.metadata.tarball,
            "mode": self.mode,
            "sha256": self.sha256,
        }
        return json.dumps(payload, indent=2)


def find_metadata(entries: dict[str, ImageMetadata], image: str) -> Optional[ImageMetadata]:
    for metadata in entries.values():
        if metadata.image == image or metadata.mirror == image or metadata.canonical == image:
            return metadata
    return None


def verify_image(image: str, matrix_path: Path, offline: bool = False) -> VerificationResult:
    entries = read_matrix(matrix_path)
    metadata = find_metadata(entries, image)
    if not metadata:
        raise SystemExit(f"Image {image} not present in matrix {matrix_path}")

    expected = metadata.sha256
    if expected:
        if metadata.tarball:
            tarball_path = Path(metadata.tarball)
            if tarball_path.exists():
                actual = compute_file_sha256(tarball_path)
                if actual != expected:
                    raise SystemExit(
                        f"Local tarball hash mismatch for {metadata.os_name}: {actual} != {expected}"
                    )

        if not offline:
            try:
                target = metadata.canonical or metadata.image
                actual = compute_docker_image_sha256(target)
            except ResolveError as exc:
                raise SystemExit(str(exc))
            if actual != expected:
                raise SystemExit(
                    f"Docker image hash mismatch for {target}: {actual} != {expected}"
                )

    mode = "offline" if offline else ("local" if metadata.tarball else "mirror")
    return VerificationResult(metadata=metadata, mode=mode, sha256=expected)


def cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ROCm image integrity against cached metadata")
    parser.add_argument("image", help="Image tag to verify (canonical or mirror)")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Matrix file to consult")
    parser.add_argument("--offline", action="store_true", help="Skip docker-based verification")
    args = parser.parse_args(argv)

    try:
        result = verify_image(args.image, args.matrix, offline=args.offline)
    except SystemExit as exc:
        if exc.code == 0:
            return VerificationStatus.OK
        print(exc, file=sys.stderr)
        return VerificationStatus.FAIL

    print(result.to_json())
    return VerificationStatus.OK


if __name__ == "__main__":
    sys.exit(cli())
