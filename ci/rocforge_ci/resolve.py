"""
Resolve ROCm container references according to project policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PACKAGE_ROOT / "rocm_matrix.yml"
POLICY_PATH = PACKAGE_ROOT / "rocm_policy.yml"
REPOSITORY = "ghcr.io/rocm/dev"


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

    def snapshot(self) -> Dict[str, str]:
        timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        data = {
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
        return data


def load_yaml(path: Path) -> Dict:
    if not path.exists():
        raise ResolveError(f"Required YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_matrix(path: Path) -> Dict:
    data = load_yaml(path)
    if "rocm" not in data:
        raise ResolveError("Invalid matrix format: missing 'rocm' root")
    return data["rocm"]


def index_images(images: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    mapping: Dict[Tuple[str, str], Dict] = {}
    for entry in images:
        version = str(entry.get("version", "")).strip()
        os_id = str(entry.get("os", "")).strip()
        if not version or not os_id:
            continue
        mapping[(version, os_id)] = entry
    return mapping


def build_candidate_order(policy: Dict) -> List[Tuple[str, str]]:
    default = policy.get("default", [])
    if isinstance(default, (list, tuple)) and len(default) == 2:
        default_version, default_os = str(default[0]), str(default[1])
    elif isinstance(default, dict):
        default_version = str(default.get("version", ""))
        default_os = str(default.get("os", ""))
    else:
        raise ResolveError("Policy.default must define version and os")

    prefer_os = str(policy.get("prefer_os", default_os)) if policy.get("prefer_os") else default_os
    fallback_os = str(policy.get("fallback_os", default_os))
    fallback_version = str(policy.get("fallback_version", default_version))

    candidates: List[Tuple[str, str]] = []

    preferred = (default_version, prefer_os)
    if preferred not in candidates:
        candidates.append(preferred)

    default_pair = (default_version, default_os)
    if default_pair not in candidates:
        candidates.append(default_pair)

    fallback_pair = (fallback_version, fallback_os)
    if fallback_pair not in candidates:
        candidates.append(fallback_pair)

    return candidates


def run_manifest_inspect(image_ref: str) -> Optional[Dict]:
    env_skip = os.getenv("CLAMP_SKIP_MANIFEST")
    if env_skip:
        return {"digest": None}
    try:
        proc = subprocess.run(
            ["docker", "manifest", "inspect", "--verbose", image_ref],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ResolveError("docker CLI not available for manifest inspection") from exc

    if proc.returncode != 0:
        return None

    digest = None
    for chunk in filter(None, proc.stdout.strip().splitlines()):
        chunk = chunk.strip()
        try:
            payload = json.loads(chunk)
        except json.JSONDecodeError:
            match = re.search(r'"digest"\s*:\s*"(sha256:[a-f0-9]+)"', chunk)
            if match:
                digest = match.group(1)
                break
            continue

        descriptor = payload.get("Descriptor")
        if isinstance(descriptor, dict) and descriptor.get("digest"):
            digest = descriptor["digest"]
            break
        if not digest and isinstance(payload.get("manifests"), list):
            manifest_list = payload["manifests"]
            for item in manifest_list:
                dig = item.get("digest")
                if isinstance(dig, str):
                    digest = dig
                    break
            if digest:
                break

    return {"digest": digest}


def resolve_image(matrix_path: Path = MATRIX_PATH, policy_path: Path = POLICY_PATH) -> ResolvedImage:
    matrix = load_matrix(matrix_path)
    images = index_images(matrix.get("images", []))
    if not images:
        raise ResolveError("Image list is empty in matrix")

    policy = matrix.get("policy", {}).copy()
    if policy_path.exists():
        policy_data = load_yaml(policy_path)
        if isinstance(policy_data, dict):
            policy.update(policy_data.get("policy", {}))
    policy_mode = str(policy.get("mode", "")).strip() or "strict"
    candidates = build_candidate_order(policy)

    first_error: Optional[str] = None

    for version, os_id in candidates:
        entry = images.get((version, os_id))
        if not entry:
            if first_error is None:
                first_error = f"No matrix entry for {version}-{os_id}"
            continue

        tag = f"{version}-{os_id}"
        ref = f"{REPOSITORY}:{tag}"
        manifest = run_manifest_inspect(ref)
        if manifest is None:
            if first_error is None:
                first_error = f"Manifest inspection failed for {ref}"
            continue

        digest = str(entry.get("digest", "")).strip()
        if digest and digest.startswith("sha256:") and not digest.endswith("TODO_NEXT_RELEASE"):
            resolved_digest = digest
        else:
            resolved_digest = manifest.get("digest")

        if not resolved_digest:
            if first_error is None:
                first_error = f"Digest unavailable for {ref}"
            continue

        signer = None
        provenance = entry.get("provenance")
        if isinstance(provenance, dict):
            signer = provenance.get("signer")

        image_ref = f"{ref}@{resolved_digest}"
        return ResolvedImage(
            image=image_ref,
            repository=REPOSITORY,
            tag=tag,
            digest=resolved_digest,
            version=version,
            os_name=os_id,
            policy_mode=policy_mode,
            signer=signer,
        )

    raise ResolveError(first_error or "No valid ROCm image found")


def cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve ROCm container image")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to the ROCm matrix YAML")
    parser.add_argument("--policy", type=Path, default=POLICY_PATH, help="Path to the ROCm policy YAML")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write snapshot metadata")
    args = parser.parse_args(argv)

    try:
        resolved = resolve_image(args.matrix, args.policy)
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
