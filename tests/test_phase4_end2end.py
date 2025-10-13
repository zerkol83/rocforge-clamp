import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "ci" / "verify_rocm_digest.py"


COSIGN_STUB = """#!/usr/bin/env python3
import json
import os
import sys

def main():
    argv = sys.argv[1:]
    if not argv or argv[0] != "verify":
        sys.exit(1)
    # consume flags we don't emulate
    args = []
    skip_next = False
    image = None
    for idx, token in enumerate(argv[1:]):
        if skip_next:
            skip_next = False
            continue
        if token in {"--key", "--certificate-identity-regexp", "--certificate-oidc-issuer", "--output"}:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        image = token
    if image is None:
        sys.exit(1)

    if os.getenv("COSIGN_FAIL") == "1":
        print("signature invalid", file=sys.stderr)
        sys.exit(1)

    payload = [{
        "critical": {
            "identity": {
                "docker-reference": os.getenv("COSIGN_SUBJECT", image),
                "issuer": os.getenv("COSIGN_ISSUER", "sigstore"),
                "signedTimestamp": "2025-01-01T00:00:00Z"
            }
        },
        "logIndex": 123
    }]
    print(json.dumps(payload))

if __name__ == "__main__":
    main()
"""


def create_cosign_stub(directory: Path) -> Path:
    stub = directory / "cosign"
    stub.write_text(COSIGN_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def write_matrix(path: Path, version: str, os_name: str, digest: str) -> None:
    path.write_text(
        f"rocm:\n"
        f"  images:\n"
        f"    - version: \"{version}\"\n"
        f"      os: \"{os_name}\"\n"
        f"      digest: \"{digest}\"\n"
        f"      added: \"2030-01-01\"\n"
        f"      provenance:\n"
        f"        key_path: \"\"\n"
        f"  policy:\n"
        f"    default: [\"{version}\", \"{os_name}\"]\n"
        f"    prefer_os: \"{os_name}\"\n"
        f"    fallback_os: \"{os_name}\"\n"
        f"    fallback_version: \"{version}\"\n",
        encoding="utf-8",
    )


def write_policy(path: Path, mode: str, require_signature: bool) -> None:
    path.write_text(
        "policy:\n"
        f"  mode: {mode}\n"
        "  digest_ttl: 7\n"
        "  workflow: update-rocm.yml\n"
        "  auto_update_ref: main\n"
        f"  require_signature: {str(require_signature).lower()}\n"
        "  attest_mode: record\n",
        encoding="utf-8",
    )


def run_verifier(image: str, matrix: Path, policy: Path, env: dict, provenance_path: Path) -> subprocess.CompletedProcess:
    env = env.copy()
    env["PROVENANCE_OUTPUT"] = str(provenance_path)
    env.setdefault("CLAMP_SKIP_REMOTE_DIGEST", image.split("@", 1)[1] if "@" in image else "")
    result = subprocess.run(
        [sys.executable, str(VERIFIER), image, "--matrix", str(matrix), "--policy", str(policy)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    return result


def main() -> int:
    if not VERIFIER.exists():
        print("Verifier script not found", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        stub_dir = tmp / "bin"
        stub_dir.mkdir(parents=True, exist_ok=True)
        create_cosign_stub(stub_dir)

        matrix = tmp / "matrix.yml"
        policy = tmp / "policy.yml"
        digest = "sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        write_matrix(matrix, "test", "ubuntu", digest)

        env = os.environ.copy()
        env["PATH"] = f"{stub_dir}{os.pathsep}" + env.get("PATH", "")
        env.pop("COSIGN_FAIL", None)

        # Strict mode (require signature) should pass with stub
        write_policy(policy, "strict", True)
        provenance_path = tmp / "prov-strict.json"
        result = run_verifier(f"ghcr.io/rocm/dev:test-ubuntu@{digest}", matrix, policy, env, provenance_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
        assert data["provenance"]["trustStatus"] == "valid"

        # Force cosign failure -> expect exit code 3
        env["COSIGN_FAIL"] = "1"
        provenance_path_fail = tmp / "prov-fail.json"
        result_fail = run_verifier(f"ghcr.io/rocm/dev:test-ubuntu@{digest}", matrix, policy, env, provenance_path_fail)
        assert result_fail.returncode == 3
        env.pop("COSIGN_FAIL")

        # Warn mode without required signature should downgrade to warning (exit 0/1)
        write_policy(policy, "warn", False)
        provenance_path_warn = tmp / "prov-warn.json"
        result_warn = run_verifier(f"ghcr.io/rocm/dev:test-ubuntu@{digest}", matrix, policy, env, provenance_path_warn)
        assert result_warn.returncode in (0, 1)
        warn_data = json.loads(provenance_path_warn.read_text(encoding="utf-8"))
        assert warn_data["provenance"]["trustStatus"] in {"unsigned", "valid", "unknown"}

    return 0


if __name__ == "__main__":
    sys.exit(main())
