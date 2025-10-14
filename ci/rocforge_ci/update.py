"""Update the ROCm matrix with fresh tags discovered in GHCR."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import os

import requests
import yaml

from .diagnostics import collect_diagnostics

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PACKAGE_ROOT / "rocm_matrix.yml"
REPOSITORY = "rocm/dev"
GHCR_TAGS_URL = f"https://ghcr.io/v2/{REPOSITORY}/tags/list"
HEADERS = {
    "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json",
    "User-Agent": "ROCForge-CI-Update/1.0",
}


def ghcr_auth():
    """Return an authentication tuple for GHCR if credentials are available."""
    user = os.getenv("GHCR_USER")
    token = os.getenv("GHCR_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        if not user:
            # GHCR accepts any non-empty username when using PATs; keep compatibility with GITHUB_TOKEN.
            user = "token"
        return (user, token)
    return None


@dataclass
class ImageEntry:
    version: str
    os_name: str
    digest: str
    added: str

    @property
    def tag(self) -> str:
        return f"{self.version}-{self.os_name}"

    def as_dict(self) -> Dict[str, str]:
        return {
            "version": self.version,
            "os": self.os_name,
            "digest": self.digest,
            "added": self.added,
        }


def load_matrix(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"Matrix file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    rocm = data.get("rocm")
    if rocm is None:
        raise ValueError("Matrix missing 'rocm' root")
    rocm.setdefault("images", [])
    rocm.setdefault("policy", {})
    return data


def existing_entries(matrix: Dict) -> Dict[Tuple[str, str], Dict]:
    mapping: Dict[Tuple[str, str], Dict] = {}
    for entry in matrix.get("rocm", {}).get("images", []):
        version = str(entry.get("version", "")).strip()
        os_name = str(entry.get("os", "")).strip()
        if version and os_name:
            mapping[(version, os_name)] = entry
    return mapping


def fetch_tags(prefix: Optional[str] = None) -> Iterable[str]:
    params = {"n": "200"}
    auth = ghcr_auth()
    response = requests.get(GHCR_TAGS_URL, headers=HEADERS, params=params, timeout=30, auth=auth)
    response.raise_for_status()
    payload = response.json()
    tags = payload.get("tags", [])
    for tag in tags:
        if not isinstance(tag, str):
            continue
        if tag == "latest" or tag.endswith("latest"):
            continue
        if prefix and not tag.endswith(prefix) and prefix not in tag:
            continue
        yield tag


def parse_tag(tag: str) -> Optional[Tuple[str, str]]:
    if "-" not in tag:
        return None
    version, os_name = tag.split("-", 1)
    if not version or not os_name:
        return None
    if version.lower().startswith("latest"):
        return None
    return version, os_name


def pull_digest(tag: str) -> Optional[str]:
    manifest_url = f"https://ghcr.io/v2/{REPOSITORY}/manifests/{tag}"
    auth = ghcr_auth()
    response = requests.head(manifest_url, headers=HEADERS, timeout=30, auth=auth)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    digest = response.headers.get("Docker-Content-Digest")
    return digest


def update_matrix(path: Path, target_os: str) -> List[ImageEntry]:
    data = load_matrix(path)
    rocm = data["rocm"]
    existing = existing_entries(data)

    today = dt.datetime.utcnow().date().isoformat()
    added_entries: List[ImageEntry] = []

    for tag in fetch_tags(prefix=target_os):
        parsed = parse_tag(tag)
        if not parsed:
            continue
        version, os_name = parsed
        if os_name != target_os:
            continue
        key = (version, os_name)
        if key in existing:
            continue
        digest = pull_digest(tag)
        if not digest:
            continue
        entry = ImageEntry(version=version, os_name=os_name, digest=digest, added=today)
        rocm.setdefault("images", []).append(entry.as_dict())
        added_entries.append(entry)

    if added_entries:
        rocm["images"] = sorted(
            rocm["images"],
            key=lambda item: (item.get("version", ""), item.get("os", "")),
        )
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump({"rocm": rocm}, handle, sort_keys=False)

    return added_entries


def cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Update ROCm matrix with new GHCR tags")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to the ROCm matrix YAML")
    parser.add_argument("--os", dest="target_os", default="ubuntu-22.04", help="Target OS suffix to track")
    parser.add_argument("--offline", action="store_true", help="Skip GHCR queries and leave matrix untouched")
    parser.add_argument("--auto", action="store_true", help="Choose online/offline mode automatically")
    args = parser.parse_args(argv)

    if args.offline and args.auto:
        parser.error("--offline and --auto are mutually exclusive")

    use_offline = args.offline
    if args.auto:
        diag = collect_diagnostics()
        http_code = diag.get("auth", {}).get("http_code")
        use_offline = http_code not in (200, 401)
        mode = "offline" if use_offline else "online"
        print(f"[update] auto mode selected {mode} (auth_code={http_code})")

    if use_offline:
        print("Offline mode: skipping GHCR update; using existing matrix.")
        return 0

    try:
        added = update_matrix(args.matrix, args.target_os)
    except Exception as exc:  # pragma: no cover
        print(f"Error updating matrix: {exc}", file=sys.stderr)
        return 1

    if not added:
        print("No new ROCm images discovered.")
    else:
        print("Added the following ROCm images:")
        for entry in added:
            print(f"  - {entry.tag} ({entry.digest})")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
