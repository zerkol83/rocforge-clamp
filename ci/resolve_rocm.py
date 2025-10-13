#!/usr/bin/env python3
"""Resolve a ROCm container image reference with digest based on policy."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover - handled in CI setup
    raise SystemExit("PyYAML is required to run the resolver") from exc

MATRIX_PATH = Path(__file__).resolve().parent / "rocm_matrix.yml"
REPOSITORY = "ghcr.io/rocm/dev"


class ResolveError(RuntimeError):
    """Raised when the resolver cannot determine a valid image."""


def load_matrix(path: Path) -> Dict:
    if not path.exists():
        raise ResolveError(f"Matrix file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "rocm" not in data:
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

    # `docker manifest inspect --verbose` may output multiple JSON documents
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


def resolve_image(matrix_path: Path = MATRIX_PATH) -> str:
    matrix = load_matrix(matrix_path)

    images = index_images(matrix.get("images", []))
    if not images:
        raise ResolveError("Image list is empty in matrix")

    policy = matrix.get("policy", {})
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

        digest = entry.get("digest")
        if digest and digest.startswith("sha256:") and not digest.endswith("TODO_NEXT_RELEASE"):
            resolved_digest = digest
        else:
            resolved_digest = manifest.get("digest")

        if not resolved_digest:
            if first_error is None:
                first_error = f"Digest unavailable for {ref}"
            continue

        return f"{ref}@{resolved_digest}"

    raise ResolveError(first_error or "No valid ROCm image found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve ROCm container image")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to the ROCm matrix YAML")
    args = parser.parse_args()

    try:
        image = resolve_image(args.matrix)
        print(image)
    except ResolveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
