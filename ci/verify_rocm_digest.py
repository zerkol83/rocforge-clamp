#!/usr/bin/env python3
"""Verify ROCm container digest integrity against the matrix."""
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

MATRIX_PATH = Path(__file__).resolve().parent / "rocm_matrix.yml"
POLICY_PATH = Path(__file__).resolve().parent / "rocm_policy.yml"
REPOSITORY = "ghcr.io/rocm/dev"
HEADERS = {
    "Accept": "application/vnd.docker.distribution.manifest.v2+json",
    "User-Agent": "Clamp-ROCm-Integrity/1.0",
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


def load_matrix(path: Path) -> Dict[Tuple[str, str], ImageRecord]:
    if not path.exists():
        raise FileNotFoundError(f"Matrix file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    rocm = data.get("rocm", {})
    mapping: Dict[Tuple[str, str], ImageRecord] = {}
    for raw in rocm.get("images", []):
        record = ImageRecord.from_dict(raw)
        if record.version and record.os_name:
            mapping[record.key] = record
    return mapping


def fetch_remote_digest(tag: str) -> Optional[str]:
    if const := os.getenv("CLAMP_SKIP_REMOTE_DIGEST"):
        return const.strip() or None
    url = f"https://ghcr.io/v2/rocm/dev/manifests/{tag}"
    response = requests.head(url, headers=HEADERS, timeout=30)
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
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("cosign CLI not found in PATH") from exc

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "cosign verify failed")

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unable to parse cosign output: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("cosign returned an empty verification payload")

    entry = payload[0]
    identity_info = entry.get("critical", {}).get("identity", {})
    return {
        "raw": payload,
        "subject": identity_info.get("docker-reference"),
        "issuer": identity_info.get("issuer"),
        "timestamp": identity_info.get("signedTimestamp"),
        "logIndex": entry.get("logIndex"),
    }


def write_provenance_output(image_ref: str, policy: Policy, provenance: Dict[str, object]) -> None:
    path = os.getenv("PROVENANCE_OUTPUT")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "image": image_ref,
                    "policyMode": policy.mode,
                    "requireSignature": policy.require_signature,
                    "attestMode": policy.attest_mode,
                    "provenance": provenance,
                },
                handle,
                indent=2,
            )
    except OSError as exc:
        print(f"Failed to write provenance output: {exc}", file=sys.stderr)


def verify(image_ref: str, matrix_path: Path, policy_path: Path) -> int:
    policy = Policy.load(policy_path)
    records = load_matrix(matrix_path)

    repo, tag, resolved_digest = parse_image_ref(image_ref)
    if repo != REPOSITORY:
        print(f"Warning: repository mismatch ({repo} != {REPOSITORY}). Proceeding.")

    if "-" not in tag:
        raise ValueError(f"Unable to parse version/os from tag '{tag}'")
    version, os_name = tag.split("-", 1)

    record = records.get((version, os_name))
    if not record:
        print(f"No matrix entry for {tag}", file=sys.stderr)
        return VerificationStatus.FAIL if policy.is_strict else VerificationStatus.WARN

    expected_digest = record.digest
    digest_algorithm = expected_digest.split(":", 1)[0] if ":" in expected_digest else "unknown"
    if not expected_digest or not expected_digest.startswith("sha256:"):
        print(f"Matrix digest missing for {tag}", file=sys.stderr)
        return VerificationStatus.FAIL if policy.is_strict else VerificationStatus.WARN

    remote_digest = fetch_remote_digest(tag)
    if not remote_digest:
        print(f"Unable to fetch remote digest for {tag}", file=sys.stderr)
        return VerificationStatus.FAIL if policy.is_strict else VerificationStatus.WARN

    status = VerificationStatus.OK

    if resolved_digest and resolved_digest != expected_digest:
        print(f"Resolver digest {resolved_digest} differs from matrix digest {expected_digest}", file=sys.stderr)
        status = VerificationStatus.FAIL

    if expected_digest != remote_digest:
        print(f"Digest drift detected for {tag}: matrix={expected_digest}, remote={remote_digest}", file=sys.stderr)
        status = VerificationStatus.FAIL

    ttl_expired = False
    added_date = parse_added_date(record)
    if added_date is not None:
        age_days = (dt.date.today() - added_date).days
        if age_days > policy.digest_ttl:
            print(f"Digest for {tag} is {age_days} days old (TTL={policy.digest_ttl}).", file=sys.stderr)
            status = max(status, VerificationStatus.WARN)
            ttl_expired = True

    provenance_summary: Dict[str, Optional[str]]
    signature_required = policy.require_signature or policy.attest_mode.lower() in {"record", "enforce"}

    if signature_required:
        key_path = record.provenance.get("key_path") if record.provenance else None
        identity = record.provenance.get("identity") if record.provenance else None
        issuer = record.provenance.get("issuer") if record.provenance else None
        image_for_signing = image_ref if "@" in image_ref else f"{repo}:{tag}@{expected_digest}"

        try:
            cosign_result = run_cosign_verify(image_for_signing, key_path, identity, issuer)
            provenance_summary = {
                "status": "verified",
                "subject": cosign_result.get("subject"),
                "issuer": cosign_result.get("issuer"),
                "logIndex": cosign_result.get("logIndex"),
                "timestamp": cosign_result.get("timestamp"),
            }
            print(f"[PROVENANCE] Verified signature for {tag} (issuer={provenance_summary['issuer']}).")
        except RuntimeError as exc:
            print(f"Signature verification failed for {tag}: {exc}", file=sys.stderr)
            if policy.require_signature:
                write_provenance_output(
                    image_for_signing,
                    policy,
                    {
                        "status": "failed",
                        "error": str(exc),
                        "timestamp": current_timestamp(),
                        "digestAlgorithm": digest_algorithm,
                        "policyDecision": f"mode={policy.mode}|require_sig={policy.require_signature}|attest={policy.attest_mode}|status={VerificationStatus.SIGNATURE_FAIL}",
                        "trustStatus": "invalid",
                    },
                )
                return VerificationStatus.SIGNATURE_FAIL
            if policy.attest_mode.lower() == "enforce":
                write_provenance_output(
                    image_for_signing,
                    policy,
                    {
                        "status": "failed",
                        "error": str(exc),
                        "timestamp": current_timestamp(),
                        "digestAlgorithm": digest_algorithm,
                        "policyDecision": f"mode={policy.mode}|require_sig={policy.require_signature}|attest={policy.attest_mode}|status={VerificationStatus.SIGNATURE_FAIL}",
                        "trustStatus": "invalid",
                    },
                )
                return VerificationStatus.SIGNATURE_FAIL
            status = max(status, VerificationStatus.WARN)
            provenance_summary = {
                "status": "unverified",
                "error": str(exc),
            }
        else:
            if policy.attest_mode.lower() == "enforce" and provenance_summary["status"] != "verified":
                write_provenance_output(image_for_signing, policy, provenance_summary)
                return VerificationStatus.SIGNATURE_FAIL
    else:
        provenance_summary = {
            "status": "skipped",
            "reason": "signature_not_required",
        }
        image_for_signing = image_ref if "@" in image_ref else f"{repo}:{tag}@{expected_digest}"

    final_status = classify_status(status, policy, reason=f"Digest drift for {tag}")

    provenance_summary.setdefault("timestamp", current_timestamp())
    provenance_summary["digestAlgorithm"] = digest_algorithm
    provenance_summary["policyDecision"] = (
        f"mode={policy.mode}|require_sig={policy.require_signature}|attest={policy.attest_mode}|status={final_status}"
    )

    if ttl_expired:
        trust_status = "expired"
    elif final_status == VerificationStatus.SIGNATURE_FAIL:
        trust_status = "invalid"
    elif provenance_summary.get("status") == "verified":
        trust_status = "valid"
    elif provenance_summary.get("status") == "unverified":
        trust_status = "invalid"
    elif provenance_summary.get("status") == "skipped":
        trust_status = "unsigned"
    else:
        trust_status = "unknown"

    provenance_summary["trustStatus"] = trust_status

    write_provenance_output(image_for_signing, policy, provenance_summary)

    return final_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ROCm container digest integrity")
    parser.add_argument("image", help="Image reference from the resolver (with optional digest)")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Path to rocm_matrix.yml")
    parser.add_argument("--policy", type=Path, default=POLICY_PATH, help="Path to rocm_policy.yml")
    args = parser.parse_args()

    try:
        status = verify(args.image, args.matrix, args.policy)
    except Exception as exc:  # pragma: no cover - surfaces issues in CI
        print(f"Verification error: {exc}", file=sys.stderr)
        return VerificationStatus.FAIL
    return status


if __name__ == "__main__":
    sys.exit(main())
