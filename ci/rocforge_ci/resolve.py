"""
Resolve ROCm container references according to project policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .diagnostics import collect_diagnostics
from .matrix import ImageMetadata, read_matrix

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PACKAGE_ROOT / "rocm_matrix.yml"
DEFAULT_MIRROR = "ghcr.io/zerkol83/rocm-dev"


class ResolveError(RuntimeError):
    """Raised when the resolver cannot determine a valid image."""


@dataclass
class ResolvedImage:
    image: str
    repository: str
    tag: str
    digest: str
    version: str
    os_name: str
    policy_mode: str
    signer: Optional[str]
    mode: str
    tarball: Optional[str] = None
    sha256: Optional[str] = None
    canonical: Optional[str] = None

    def snapshot(self, *, timestamp: str | None = None) -> Dict[str, str]:
        if not timestamp:
            timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        data = {
            "mode": self.mode,
            "timestamp": timestamp,
            "image": self.image,
            "repository": self.repository,
            "tag": self.tag,
            "digest": self.digest,
            "version": self.version,
            "os": self.os_name,
            "policy_mode": self.policy_mode,
            "resolved_at": timestamp,
        }
        if self.signer:
            data["signer"] = self.signer
        if self.tarball:
            data["tarball"] = self.tarball
        if self.sha256:
            data["sha256"] = self.sha256
        if self.canonical:
            data["canonical"] = self.canonical
        return data


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_docker_image_sha256(image: str) -> str:
    cmd = ["docker", "save", image]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise ResolveError("docker CLI not available to compute image hash") from exc

    hasher = hashlib.sha256()
    assert proc.stdout is not None
    for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
        if not chunk:
            break
        hasher.update(chunk)
    proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else ""
    return_code = proc.wait()
    if return_code != 0:
        raise ResolveError(f"Failed to compute docker image hash: {stderr.strip() or return_code}")
    return hasher.hexdigest()


def docker_load_tarball(tarball: Path) -> None:
    cmd = ["docker", "load", "-i", str(tarball)]
    try:
        proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise ResolveError("docker CLI not available to load local tarball") from exc
    if proc.returncode != 0:
        raise ResolveError(f"docker load failed: {proc.stderr.strip() or proc.stdout.strip()}")


def docker_pull_image(image: str) -> None:
    cmd = ["docker", "pull", image]
    try:
        proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise ResolveError("docker CLI not available to pull mirror image") from exc
    if proc.returncode != 0:
        raise ResolveError(f"docker pull failed for {image}: {proc.stderr.strip() or proc.stdout.strip()}")


def docker_tag_image(source: str, target: str) -> None:
    if source == target:
        return
    cmd = ["docker", "tag", source, target]
    proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise ResolveError(f"docker tag {source} -> {target} failed: {proc.stderr.strip() or proc.stdout.strip()}")


def select_metadata(entries: Dict[str, ImageMetadata], target_os: Optional[str]) -> ImageMetadata:
    if target_os:
        if target_os not in entries:
            raise ResolveError(f"No matrix entry for OS {target_os}")
        return entries[target_os]
    if not entries:
        raise ResolveError("Matrix must define at least one image")
    # deterministic ordering by OS name
    os_name = sorted(entries.keys())[0]
    return entries[os_name]


def resolve_image(
    matrix_path: Path = MATRIX_PATH,
    offline: bool = False,
    target_os: Optional[str] = None,
    prefer_local: bool = True,
    mirror_namespace: str = DEFAULT_MIRROR,
) -> ResolvedImage:
    entries = read_matrix(matrix_path)
    metadata = select_metadata(entries, target_os)
    policy_mode = "static"

    image_ref = metadata.image or ""
    if not image_ref:
        raise ResolveError(f"Matrix entry for {metadata.os_name} missing image tag")

    repository, tag = image_ref.split(":", 1) if ":" in image_ref else (image_ref, "")

    if offline:
        print(f"[resolve] offline mode selected for {metadata.os_name}")
        return ResolvedImage(
            image=image_ref,
            repository=repository,
            tag=tag,
            digest="",
            version=tag or metadata.os_name,
            os_name=metadata.os_name,
            policy_mode=policy_mode,
            signer=None,
            mode="offline",
            tarball=metadata.tarball,
            sha256=metadata.sha256,
            canonical=metadata.canonical_image,
        )

    # Prefer local tarball if available.
    if prefer_local and metadata.tarball:
        tarball_path = Path(metadata.tarball)
        if tarball_path.exists():
            if metadata.sha256:
                computed = compute_file_sha256(tarball_path)
                if computed != metadata.sha256:
                    raise ResolveError(
                        f"Local tarball hash mismatch for {metadata.os_name}: {computed} != {metadata.sha256}"
                    )
            print(f"[resolve] loading local ROCm image tarball {tarball_path}")
            docker_load_tarball(tarball_path)
            canonical_tag = metadata.canonical_image
            if canonical_tag and canonical_tag != image_ref:
                docker_tag_image(canonical_tag, image_ref)
            print(f"[resolve] mode local (tarball={tarball_path})")
            return ResolvedImage(
                image=image_ref,
                repository=repository,
                tag=tag,
                digest="",
                version=tag or metadata.os_name,
                os_name=metadata.os_name,
                policy_mode=policy_mode,
                signer=None,
                mode="local",
                tarball=str(tarball_path),
                sha256=metadata.sha256,
                canonical=metadata.canonical_image,
            )

    # Attempt mirror pull
    mirror_image = metadata.mirror or metadata.image or f"{mirror_namespace}:{tag}"
    try:
        print(f"[resolve] pulling mirror image {mirror_image}")
        docker_pull_image(mirror_image)
        canonical_tag = metadata.canonical_image
        if mirror_image != image_ref:
            docker_tag_image(mirror_image, image_ref)
        if canonical_tag and canonical_tag != image_ref:
            docker_tag_image(image_ref, canonical_tag)
        if metadata.sha256:
            target_tag = canonical_tag or image_ref
            computed = compute_docker_image_sha256(target_tag)
            if computed != metadata.sha256:
                raise ResolveError(
                    f"Mirror image hash mismatch for {metadata.os_name}: {computed} != {metadata.sha256}"
                )
        print(f"[resolve] mode mirror (image={mirror_image})")
        return ResolvedImage(
            image=image_ref,
            repository=repository,
            tag=tag,
            digest="",
            version=tag or metadata.os_name,
            os_name=metadata.os_name,
            policy_mode=policy_mode,
            signer=None,
            mode="mirror",
            tarball=metadata.tarball,
            sha256=metadata.sha256,
            canonical=metadata.canonical_image,
        )
    except ResolveError as exc:
        print(f"[resolve] mirror pull failed: {exc}")

    print(f"[resolve] falling back to offline metadata for {metadata.os_name}")
    return ResolvedImage(
        image=image_ref,
        repository=repository,
        tag=tag,
        digest="",
        version=tag or metadata.os_name,
        os_name=metadata.os_name,
        policy_mode=policy_mode,
        signer=None,
        mode="offline",
        tarball=metadata.tarball,
        sha256=metadata.sha256,
        canonical=metadata.canonical_image,
    )


def cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve ROCm container image")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to the ROCm matrix YAML")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write snapshot metadata")
    parser.add_argument("--offline", action="store_true", help="Force offline resolution without docker operations")
    parser.add_argument("--auto", action="store_true", help="Choose local/mirror/offline mode automatically")
    parser.add_argument("--os", dest="target_os", default=None, help="Target OS key to resolve (e.g. ubuntu-22.04)")
    args = parser.parse_args(argv)

    if args.offline and args.auto:
        parser.error("--offline and --auto are mutually exclusive")

    use_offline = args.offline
    prefer_local = not args.offline
    if args.auto:
        diag = collect_diagnostics()
        http_code = diag.get("auth", {}).get("http_code")
        use_offline = http_code not in (200, 401)
        prefer_local = True
        print(f"[resolve] auto mode selected {'offline' if use_offline else 'auto'} (auth_code={http_code})")

    try:
        resolved = resolve_image(
            matrix_path=args.matrix,
            offline=use_offline,
            target_os=args.target_os,
            prefer_local=prefer_local,
        )
    except ResolveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(resolved.snapshot(), handle, indent=2, sort_keys=True)
            handle.write("\n")

    print(resolved.image)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
