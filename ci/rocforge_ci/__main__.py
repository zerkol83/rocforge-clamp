"""
CLI entry point for ROCForge-CI utilities.

Usage:
    python -m rocforge_ci resolve [args...]
    python -m rocforge_ci verify [args...]
    python -m rocforge_ci update [args...]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import resolve_module, update_module, verify_module
from .clamp_bridge import clamp_manifest_path, restore as clamp_restore, verify as clamp_verify
from .diagnostics import collect_diagnostics
from .matrix import ImageMetadata, read_matrix, update_matrix_entry
from .resolve import DEFAULT_MIRROR, ResolveError, docker_tag_image, resolve_image
from .runlog import record_run

CI_MODE_FILE = Path(".ci_mode")


def current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def run_docker(cmd: list[str], *, error: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"docker CLI not available: {cmd[0]}") from exc
    if proc.returncode != 0:
        raise SystemExit(f"{error}: {proc.stderr.strip() or proc.stdout.strip() or proc.returncode}")
    return proc


def docker_push(image: str) -> None:
    run_docker(["docker", "push", image], error=f"docker push failed for {image}")


def read_ci_mode() -> Dict[str, Any] | None:
    try:
        content = CI_MODE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not content:
        return None

    try:
        payload = json.loads(content)
        if isinstance(payload, dict) and payload.get("mode"):
            return payload
    except json.JSONDecodeError:
        pass

    # Legacy format: plain string with mode.
    return {"mode": content, "timestamp": None, "snapshot": None}


def write_ci_mode(mode: str, *, snapshot: Path | str | None = None, timestamp: str | None = None) -> Dict[str, Any]:
    previous = read_ci_mode()
    prev_mode = previous.get("mode") if previous else None

    if snapshot:
        snapshot_path = Path(snapshot)
        snapshot_str = str(snapshot_path)
        if timestamp is None and snapshot_path.exists():
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    timestamp = payload.get("timestamp") or payload.get("resolved_at")
            except (OSError, json.JSONDecodeError):
                pass
    else:
        snapshot_str = None

    if timestamp is None:
        timestamp = current_timestamp()

    record: Dict[str, Any] = {"mode": mode, "timestamp": timestamp}
    if snapshot_str:
        record["snapshot"] = snapshot_str

    if prev_mode and prev_mode != mode:
        print(f"⚠️ Detected mode change: previous={prev_mode}, current={mode}")

    try:
        CI_MODE_FILE.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass

    return record


def emit_run_summary(record: Dict[str, Any]) -> None:
    summary = {
        "mode": record.get("mode"),
        "timestamp": record.get("timestamp"),
        "snapshot": record.get("snapshot"),
    }
    print(json.dumps(summary, sort_keys=True))


def offline_bootstrap(argv):
    from .resolve import cli as resolve_cli
    from .verify import cli as verify_cli

    matrix = Path("ci/rocm_matrix.yml")
    if not matrix.exists():
        matrix = Path("rocm_matrix.yml")
    if not matrix.exists():
        print("Fallback matrix not found (ci/rocm_matrix.yml)", file=os.sys.stderr)
        return 1

    print(f"[offline] Using matrix {matrix}")
    snapshot_path = Path("build/rocm_snapshot.json")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    result = resolve_cli([
        "--matrix",
        str(matrix),
        "--offline",
        "--output",
        str(snapshot_path),
    ])
    if result != 0:
        return result

    entries = read_matrix(matrix)
    for entry in entries.values():
        if not entry.image:
            continue
        print(f"[offline] verify {entry.image}")
        rc = verify_cli(["--matrix", str(matrix), entry.image, "--offline"])
        if rc != 0:
            return rc

    print("[offline] bootstrap complete")
    record = write_ci_mode("offline", snapshot=snapshot_path)
    emit_run_summary(record)
    clamp_path = clamp_manifest_path()
    clamp_manifest_str = str(clamp_path) if clamp_path else None
    if clamp_path:
        print(f"[offline] Clamp: manifest found at {clamp_path}")
        restore_result = clamp_restore({"manifest_path": str(clamp_path)})
        print(f"[offline] Clamp restore: {restore_result.get('message')}")
        verify_result = clamp_verify({"manifest_path": str(clamp_path)})
        print(f"[offline] Clamp verify: {verify_result.get('message')}")
        mismatches = verify_result.get("mismatches") or []
        if mismatches:
            for mismatch in mismatches:
                field = mismatch.get("field")
                reason = mismatch.get("reason")
                print(f"[offline] Clamp mismatch: {field} ({reason})")
        record_run(
            mode="offline",
            clamp_manifest_path=clamp_manifest_str,
            verify_status=verify_result.get("status"),
            verify_message=verify_result.get("message"),
        )
        if verify_result.get("status") != "pass":
            return 2
    else:
        print("[offline] Clamp: manifest not found; skipping verification.")
        record_run(
            mode="offline",
            clamp_manifest_path=None,
            verify_status="skipped",
            verify_message="no manifest",
        )
    return 0


def diagnostics(argv):
    parser = argparse.ArgumentParser(description="Display GHCR diagnostics")
    parser.add_argument("--json", action="store_true", help="Emit diagnostics as JSON")
    parser.add_argument("--ci", action="store_true", help="Emit condensed CI-friendly JSON line")
    args = parser.parse_args(argv)

    if args.json and args.ci:
        parser.error("--json and --ci cannot be used together")

    info = collect_diagnostics()

    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    if args.ci:
        env = info["environment"]
        dns = info.get("dns", {})
        auth = info.get("auth", {})
        ci_payload = {
            "timestamp": current_timestamp(),
            "ghcr_status": auth.get("status"),
            "ghcr_code": auth.get("http_code"),
            "dns_status": dns.get("status"),
            "ghcr_user": bool(env.get("GHCR_USER")),
            "ghcr_token_present": env.get("GHCR_TOKEN_length", 0) > 0,
            "github_token_present": env.get("GITHUB_TOKEN_length", 0) > 0,
        }
        print(json.dumps(ci_payload, sort_keys=True))
        return 0

    env = info["environment"]
    print("GHCR diagnostics")
    print("----------------")
    print(f"GHCR_USER: {env['GHCR_USER'] or '<unset>'}")
    print(f"GHCR_TOKEN length: {env['GHCR_TOKEN_length']}")
    print(f"GITHUB_TOKEN length: {env['GITHUB_TOKEN_length']}")

    dns = info.get("dns", {})
    if dns.get("status") == "ok":
        print(f"DNS: ghcr.io resolves to {dns['address']}")
    else:
        print(f"DNS: ghcr.io resolution failed ({dns.get('error', 'unknown error')})")

    auth = info.get("auth", {})
    status = auth.get("status", "unknown")
    http_code = auth.get("http_code")
    message = auth.get("message", "")
    if http_code:
        print(f"Auth: {status} (HTTP {http_code}) {message}".strip())
    else:
        print(f"Auth: {status} {message}".strip())

    return 0


def smart_bootstrap(argv):
    matrix_path = Path("ci/rocm_matrix.yml")
    if not matrix_path.exists():
        matrix_path = Path("rocm_matrix.yml")
    snapshot_path = Path("build/rocm_snapshot.json")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    entries = read_matrix(matrix_path)
    local_available = any(Path(meta.tarball).exists() for meta in entries.values() if meta.tarball)
    offline_mode = False

    if local_available:
        print("[smart] Local ROCm image tarball detected; preferring cached mode.")
    else:
        info = collect_diagnostics()
        auth = info.get("auth", {})
        http_code = auth.get("http_code")
        status = auth.get("status")
        if http_code not in (200, 401):
            offline_mode = True
            print(f"[smart] GHCR unavailable (status={status}, code={http_code}); using offline metadata.")
        else:
            print(f"[smart] GHCR reachable (status={status}, code={http_code}); mirror mode available.")

    try:
        resolved = resolve_image(matrix_path=matrix_path, offline=offline_mode, prefer_local=True)
    except ResolveError as exc:
        print(f"[smart] resolution failed ({exc}); falling back to offline bootstrap.")
        return offline_bootstrap(argv)

    with snapshot_path.open("w", encoding="utf-8") as handle:
        json.dump(resolved.snapshot(), handle, indent=2, sort_keys=True)
        handle.write("\n")

    record = write_ci_mode(resolved.mode, snapshot=snapshot_path)
    emit_run_summary(record)
    print(f"[smart] bootstrap completed (mode={resolved.mode}, image={resolved.image}).")

    verify_cli = verify_module().cli
    verify_args = ["--matrix", str(matrix_path), resolved.image]
    if resolved.mode == "offline":
        verify_args.append("--offline")
    rc = verify_cli(verify_args)
    if rc != 0:
        print("[smart] verification reported an issue.")
        return rc

    clamp_path = clamp_manifest_path()
    clamp_manifest_str = str(clamp_path) if clamp_path else None
    verify_status = "skipped"
    verify_message = "no manifest"
    if clamp_path:
        print(f"[smart] Clamp: manifest found at {clamp_path}")
        restore_result = clamp_restore({"manifest_path": clamp_manifest_str})
        print(f"[smart] Clamp restore: {restore_result.get('message')}")
        verify_result = clamp_verify({"manifest_path": clamp_manifest_str})
        verify_status = verify_result.get("status")
        verify_message = verify_result.get("message")
        print(f"[smart] Clamp verify: {verify_message}")
        mismatches = verify_result.get("mismatches") or []
        if mismatches:
            for mismatch in mismatches:
                field = mismatch.get("field")
                reason = mismatch.get("reason")
                print(f"[smart] Clamp mismatch: {field} ({reason})")
    else:
        print("[smart] Clamp: manifest not found; skipping verification.")

    record_run(
        mode=resolved.mode,
        clamp_manifest_path=clamp_manifest_str,
        verify_status=verify_status,
        verify_message=verify_message,
        extra={
            "snapshot_path": str(snapshot_path),
            "image": resolved.image,
        },
    )
    if clamp_path and verify_status != "pass":
        print("[smart] Clamp verification failed; aborting.")
        return 2

    return 0


COMMANDS = {
    "resolve": lambda argv: resolve_module().cli(argv),
    "verify": lambda argv: verify_module().cli(argv),
    "update": lambda argv: update_module().cli(argv),
    "offline-bootstrap": offline_bootstrap,
    "offline_bootstrap": offline_bootstrap,
    "smart-bootstrap": smart_bootstrap,
    "smart_bootstrap": smart_bootstrap,
    "diagnostics": diagnostics,
}


def mode_command(argv):
    parser = argparse.ArgumentParser(prog="rocforge-ci mode", description="Inspect or reset CI mode marker")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("show", help="Display the last recorded CI mode")
    subparsers.add_parser("reset", help="Clear the CI mode record")

    args = parser.parse_args(argv)
    if args.subcommand == "show":
        record = read_ci_mode() or {"mode": None, "timestamp": None, "snapshot": None}
        print(json.dumps(record, sort_keys=True))
        return 0
    if args.subcommand == "reset":
        timestamp = current_timestamp()
        try:
            CI_MODE_FILE.unlink()
            status = "reset"
        except FileNotFoundError:
            status = "noop"
        payload = {"mode": None, "snapshot": None, "status": status, "timestamp": timestamp}
        print(json.dumps(payload, sort_keys=True))
        return 0

    parser.print_help()
    return 1


COMMANDS["mode"] = mode_command


def cache_build(argv):
    parser = argparse.ArgumentParser(prog="rocforge-ci cache-build", description="Build and cache canonical ROCm image")
    parser.add_argument("--release", required=True, help="ROCm release identifier (e.g. 6.4.4)")
    parser.add_argument("--os", dest="target_os", required=True, help="Base OS identifier (e.g. ubuntu-22.04)")
    parser.add_argument("--image", default=None, help="Runtime image tag to publish (defaults to <mirror>:<release>-<os>)")
    parser.add_argument("--canonical", default=None, help="Canonical image tag to embed in the tarball (defaults to rocforge/rocm-dev:<release>-<os>)")
    parser.add_argument("--mirror", default=DEFAULT_MIRROR, help="Mirror namespace or full tag for GHCR mirror")
    parser.add_argument("--dockerfile", type=Path, default=Path("images/Dockerfile"), help="Dockerfile used to build the canonical image")
    parser.add_argument("--context", type=Path, default=Path("."), help="Build context directory")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH, help="Matrix file to update")
    parser.add_argument("--tar-dir", type=Path, default=Path("images"), help="Directory to store saved tarballs")
    parser.add_argument("--build-arg", action="append", default=[], help="Additional build arguments (KEY=VALUE)")
    parser.add_argument("--push", action="store_true", help="Push the mirror tag after building")
    args = parser.parse_args(argv)

    release = args.release
    os_key = args.target_os
    canonical_tag = args.canonical or f"rocforge/rocm-dev:{release}-{os_key}"
    if args.image:
        runtime_tag = args.image
    elif ":" in args.mirror:
        runtime_tag = args.mirror
    else:
        runtime_tag = f"{args.mirror}:{release}-{os_key}"
    if ":" in args.mirror:
        mirror_tag = args.mirror
    else:
        mirror_tag = runtime_tag

    build_cmd = [
        "docker",
        "build",
        "-t",
        canonical_tag,
        "-f",
        str(args.dockerfile),
    ]
    for build_arg in args.build_arg:
        build_cmd.extend(["--build-arg", build_arg])
    build_cmd.append(str(args.context))

    print(f"[cache-build] Building canonical image {canonical_tag}")
    run_docker(build_cmd, error="docker build failed")

    if runtime_tag != canonical_tag:
        print(f"[cache-build] Tagging runtime image {runtime_tag}")
        docker_tag_image(canonical_tag, runtime_tag)
    if mirror_tag not in {runtime_tag, canonical_tag}:
        print(f"[cache-build] Tagging mirror image {mirror_tag}")
        docker_tag_image(canonical_tag, mirror_tag)

    images_dir = args.tar_dir
    images_dir.mkdir(parents=True, exist_ok=True)
    safe_tag = canonical_tag.replace("/", "_").replace(":", "-")
    tarball_path = images_dir / f"{safe_tag}.tar.gz"

    print(f"[cache-build] Saving tarball to {tarball_path}")
    try:
        proc = subprocess.Popen(["docker", "save", canonical_tag], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise SystemExit("docker CLI not available: docker save") from exc

    assert proc.stdout is not None
    with gzip.open(tarball_path, "wb") as handle:
        for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
            if not chunk:
                break
            handle.write(chunk)
    proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else ""
    if proc.wait() != 0:
        tarball_path.unlink(missing_ok=True)
        raise SystemExit(f"docker save failed: {stderr.strip()}")

    sha256 = compute_sha256(tarball_path)
    timestamp = current_timestamp()

    metadata = ImageMetadata(
        os_name=os_key,
        image=runtime_tag,
        mirror=mirror_tag,
        canonical=canonical_tag,
        tarball=str(tarball_path),
        sha256=sha256,
        timestamp=timestamp,
    )
    update_matrix_entry(args.matrix, metadata)
    print(f"[cache-build] Updated matrix {args.matrix} with {runtime_tag} (sha256={sha256})")

    if args.push:
        print(f"[cache-build] Pushing runtime tag {runtime_tag}")
        docker_push(runtime_tag)

    print("[cache-build] Complete")
    return 0


COMMANDS["cache-build"] = cache_build
COMMANDS["cache_build"] = cache_build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rocforge-ci", description="ROCForge CI orchestrator")
    parser.add_argument("command", choices=sorted(COMMANDS.keys()), help="Command to execute")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the sub-command")
    parsed = parser.parse_args(argv)

    handler = COMMANDS.get(parsed.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(parsed.args)


if __name__ == "__main__":
    os.sys.exit(main())
