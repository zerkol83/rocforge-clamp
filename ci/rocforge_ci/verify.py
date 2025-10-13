"""
Verify ROCm container digest integrity against the project matrix.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PACKAGE_ROOT / "rocm_matrix.yml"
POLICY_PATH = PACKAGE_ROOT / "rocm_policy.yml"
REPOSITORY = "ghcr.io/rocm/dev"
HEADERS = {
    "Accept": "application/vnd.docker.distribution.manifest.v2+json",
    "User-Agent": "ROCForge-CI-Verify/1.0",
}


class VerificationStatus:
    OK = 0
    WARN = 1
    FAIL = 2
    SIGNATURE_FAIL = 3


@dataclass
class Policy:
    mode: str = "strict"
    digest_ttl: int = 7
    workflow: str = "update-rocm.yml"
    auto_update_ref: str = "main"
    require_signature: bool = False
    attest_mode: str = "none"

    @classmethod
    def load(cls, path: Path) -> "Policy":
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        policy = data.get("policy", {}) if isinstance(data, dict) else {}
        return cls(
            mode=str(policy.get("mode", cls.mode)).strip() or cls.mode,
            digest_ttl=int(policy.get("digest_ttl", cls.digest_ttl)),
            workflow=str(policy.get("workflow", cls.workflow)).strip() or cls.workflow,
            auto_update_ref=str(policy.get("auto_update_ref", cls.auto_update_ref)).strip() or cls.auto_update_ref,
            require_signature=bool(policy.get("require_signature", cls.require_signature)),
            attest_mode=str(policy.get("attest_mode", cls.attest_mode)).strip() or cls.attest_mode,
        )

    @property
    def is_strict(self) -> bool:
        return self.mode.lower() == "strict"

    @property
    def is_warn(self) -> bool:
        return self.mode.lower() == "warn"

    @property
    def is_auto_update(self) -> bool:
        return self.mode.lower() == "auto_update"


@dataclass
class ImageRecord:
    version: str
    os_name: str
    digest: str
    added: Optional[str]
    provenance: Dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str]:
        return self.version, self.os_name

    @property
    def tag(self) -> str:
        return f"{self.version}-{self.os_name}"

    @classmethod
    def from_dict(cls, entry: Dict) -> "ImageRecord":
        return cls(
            version=str(entry.get("version", "")).strip(),
            os_name=str(entry.get("os", "")).strip(),
            digest=str(entry.get("digest", "")).strip(),
            added=entry.get("added"),
            provenance=entry.get("provenance", {}) or {},
        )


def parse_image_ref(ref: str) -> Tuple[str, str, Optional[str]]:
    if "@" in ref:
        base, digest = ref.split("@", 1)
    else:
        base, digest = ref, None
    if ":" not in base:
        raise ValueError(f"Image reference must include a tag: {ref}")
    repo, tag = base.split(":", 1)
    return repo, tag, digest


def load_matrix(path: Path) -> Tuple[str, Dict[Tuple[str, str], ImageRecord]]:
    if not path.exists():
        raise FileNotFoundError(f"Matrix file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if "rocm" in data:
        rocm = data.get("rocm", {})
        mapping: Dict[Tuple[str, str], ImageRecord] = {}
        for raw in rocm.get("images", []):
            record = ImageRecord.from_dict(raw)
            if record.version and record.os_name:
                mapping[record.key] = record
        return "rich", mapping

    # simple mapping fallback
    mapping = {}
    for os_name, entry in data.items():
        image = entry.get("image") if isinstance(entry, dict) else str(entry)
        if not image:
            continue
        record = ImageRecord(version=image.split(":")[-1], os_name=os_name, digest="", added=None)
        mapping[(record.version, record.os_name)] = record
    return "simple", mapping


def fetch_remote_digest(tag: str) -> Optional[str]:
    if const := os.getenv("CLAMP_SKIP_REMOTE_DIGEST"):
        return const.strip() or None
    url = f"https://ghcr.io/v2/rocm/dev/manifests/{tag}"
    headers = HEADERS.copy()
    user = os.getenv("GHCR_USER")
    token = os.getenv("GHCR_TOKEN") or os.getenv("GITHUB_TOKEN")
    auth = (user, token) if user and token else None
    response = requests.head(url, headers=headers, auth=auth, timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.headers.get("Docker-Content-Digest")


def parse_added_date(record: ImageRecord) -> Optional[dt.date]:
    if not record.added:
        return None
    try:
        return dt.datetime.strptime(record.added, "%Y-%m-%d").date()
    except ValueError:
        return None


def trigger_auto_update(policy: Policy, reason: str) -> None:
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY") or os.getenv("REPO_NAME")
    if not token or not repository:
        print("Auto-update requested but missing GITHUB_TOKEN or GITHUB_REPOSITORY", file=sys.stderr)
        return

    url = f"https://api.github.com/repos/{repository}/actions/workflows/{policy.workflow}/dispatches"
    payload = {"ref": policy.auto_update_ref}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"Failed to trigger auto-update workflow: {exc}", file=sys.stderr)
        return
    if resp.status_code >= 300:
        print(f"Failed to trigger auto-update workflow: {resp.status_code} {resp.text}", file=sys.stderr)
    else:
        print("Auto-update workflow dispatched.")


def classify_status(status: int, policy: Policy, reason: str) -> int:
    if status != VerificationStatus.FAIL:
        return status

    if policy.is_auto_update:
        trigger_auto_update(policy, reason=reason)
        return VerificationStatus.WARN

    if policy.is_strict:
        return VerificationStatus.FAIL

    return VerificationStatus.WARN


def current_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cosign_verify(image_ref: str, key_path: Optional[str], identity: Optional[str], issuer: Optional[str]) -> Dict:
    cmd = ["cosign", "verify", "--output", "json"]
    if key_path:
        cmd.extend(["--key", key_path])
    else:
        if identity:
            cmd.extend(["--certificate-identity-regexp", identity])
        if issuer:
            cmd.extend(["--certificate-oidc-issuer", issuer])
    cmd.append(image_ref)

    try:
        proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except FileNotFoundError:
        return {"status": VerificationStatus.SIGNATURE_FAIL, "error": "cosign not available"}
    except subprocess.SubprocessError as exc:
        return {"status": VerificationStatus.SIGNATURE_FAIL, "error": str(exc)}

    if proc.returncode != 0:
        return {"status": VerificationStatus.SIGNATURE_FAIL, "error": proc.stderr.strip()}

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"raw": proc.stdout}
    return {"status": VerificationStatus.OK, "details": payload}


def verify_image(image_ref: str, matrix_path: Path = MATRIX_PATH, policy_path: Path = POLICY_PATH) -> int:
    policy = Policy.load(policy_path)
    matrix_kind, matrix = load_matrix(matrix_path)

    repo, tag, digest = parse_image_ref(image_ref)
    if repo != REPOSITORY:
        print(f"Warning: repository mismatch ({repo} != {REPOSITORY})", file=sys.stderr)

    if matrix_kind == "simple":
        # basic validation: ensure tag exists in mapping
        target = None
        for (_, os_name), record in matrix.items():
            if record.os_name in tag or record.version == tag:
                target = record
                break
        if target is None:
            print(f"Image {tag} not present in matrix", file=sys.stderr)
            return VerificationStatus.FAIL
        snapshot = {
            "image": image_ref,
            "digest": digest or "",
            "policy_mode": policy.mode,
            "checked_at": current_timestamp(),
        }
        print(json.dumps(snapshot, indent=2))
        return VerificationStatus.OK

    version, os_name = tag.split("-", 1) if "-" in tag else (tag, "")
    record = matrix.get((version, os_name))
    if not record:
        print(f"Image {tag} not present in matrix", file=sys.stderr)
        return VerificationStatus.FAIL

    expected_digest = record.digest
    if digest and digest != expected_digest:
        print(f"Digest mismatch: {digest} != {expected_digest}", file=sys.stderr)
        return VerificationStatus.FAIL

    remote_digest = fetch_remote_digest(tag)
    if remote_digest and remote_digest != expected_digest:
        reason = f"Remote digest {remote_digest} differs from matrix {expected_digest}"
        print(reason, file=sys.stderr)
        return classify_status(VerificationStatus.FAIL, policy, reason)

    if policy.require_signature:
        provenance = record.provenance or {}
        key_path = provenance.get("key")
        identity = provenance.get("identity")
        issuer = provenance.get("issuer")
        cosign_result = run_cosign_verify(image_ref, key_path, identity, issuer)
        status = cosign_result.get("status", VerificationStatus.SIGNATURE_FAIL)
        if status != VerificationStatus.OK:
            reason = cosign_result.get("error", "signature verification failed")
            return classify_status(VerificationStatus.FAIL, policy, reason)

    added_date = parse_added_date(record)
    if added_date and policy.digest_ttl > 0:
        max_age = added_date + dt.timedelta(days=policy.digest_ttl)
        if dt.date.today() > max_age:
            reason = f"Digest for {tag} is older than {policy.digest_ttl} days"
            print(reason, file=sys.stderr)
            return classify_status(VerificationStatus.WARN, policy, reason)

    snapshot = {
        "image": image_ref,
        "digest": digest or expected_digest,
        "policy_mode": policy.mode,
        "checked_at": current_timestamp(),
    }
    print(json.dumps(snapshot, indent=2))
    return VerificationStatus.OK


def cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ROCm container digest integrity")
    parser.add_argument("image", help="Resolved ROCm image reference (with digest)")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to the ROCm matrix YAML")
    parser.add_argument("--policy", type=Path, default=POLICY_PATH, help="Path to the ROCm policy YAML")
    args = parser.parse_args(argv)

    status = verify_image(args.image, args.matrix, args.policy)
    return status


if __name__ == "__main__":
    sys.exit(cli())
