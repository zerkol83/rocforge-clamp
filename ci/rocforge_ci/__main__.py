"""
CLI entry point for ROCForge-CI utilities.

Usage:
    python -m rocforge_ci resolve [args...]
    python -m rocforge_ci verify [args...]
    python -m rocforge_ci update [args...]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import resolve_module, update_module, verify_module
from .diagnostics import collect_diagnostics

CI_MODE_FILE = Path(".ci_mode")


def current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

    import yaml

    data = yaml.safe_load(matrix.read_text()) or {}
    images = []
    if "rocm" in data:
        for entry in data["rocm"].get("images", []):
            if isinstance(entry, dict):
                image = entry.get("image")
                if image:
                    images.append(image)
    else:
        for entry in data.values():
            if isinstance(entry, dict):
                image = entry.get("image")
                if image:
                    images.append(image)

    for image in images:
        print(f"[offline] verify {image}")
        rc = verify_cli(["--matrix", str(matrix), image, "--offline"])
        if rc != 0:
            return rc

    print("[offline] bootstrap complete")
    record = write_ci_mode("offline", snapshot=snapshot_path)
    emit_run_summary(record)
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
    info = collect_diagnostics()
    auth = info.get("auth", {})
    http_code = auth.get("http_code")
    status = auth.get("status")

    if http_code in (200, 401):
        print(f"[smart] GHCR reachable (status={status}, code={http_code}). Running live update.")
        rc = update_module().cli([])
        if rc != 0:
            print("[smart] update failed; falling back to offline bootstrap.")
            return offline_bootstrap(argv)
        snapshot_path = Path("build/rocm_snapshot.json")
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        rc = resolve_module().cli(["--output", str(snapshot_path)])
        if rc != 0:
            print("[smart] resolve failed; falling back to offline bootstrap.")
            return offline_bootstrap(argv)
        record = write_ci_mode("online", snapshot=snapshot_path)
        emit_run_summary(record)
        print("[smart] live update completed successfully.")
        return 0

    print(f"[smart] GHCR unavailable (status={status}, code={http_code}). Using offline fallback.")
    return offline_bootstrap(argv)


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
