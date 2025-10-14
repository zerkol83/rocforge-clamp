"""
Clamp subcommand handler for the RocFoundry CLI.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from engine import bootstrap_extensions
from cli.context import CliContext
from snapi import dispatch


STATUS_EXIT = {
    "ok": 0,
    "pass": 0,
    "success": 0,
    "noop": 0,
    "warn": 1,
    "warning": 1,
    "missing": 1,
    "skip": 1,
    "skipped": 1,
    "fail": 2,
    "error": 2,
}


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    clamp_parser = subparsers.add_parser(
        "clamp",
        help="Manage Clamp environment captures",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    clamp_parser.set_defaults(command="clamp")

    sub = clamp_parser.add_subparsers(dest="action", metavar="<action>")

    capture = sub.add_parser("capture", help="Capture the ROCm environment")
    capture.add_argument("target_path", nargs="?", default="/opt/rocm", help="Path to ROCm installation")
    capture.add_argument("--output", "-o", default="build/clamp", help="Directory for capture artifacts")
    capture.add_argument("--archive", action="store_true", help="Create a ROCm archive tarball")
    capture.add_argument("--force", action="store_true", help="Overwrite existing capture artifacts")

    restore = sub.add_parser("restore", help="Prepare environment from a manifest")
    restore.add_argument("manifest_path", help="Clamp manifest path")
    mode = restore.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Emit shell exports for eval/exec")
    mode.add_argument("--print", action="store_true", help="Print key=value pairs")

    verify = sub.add_parser("verify", help="Verify system state against a manifest")
    verify.add_argument("manifest_path", help="Clamp manifest path")
    strictness = verify.add_mutually_exclusive_group()
    strictness.add_argument("--strict", action="store_true", help="Treat mismatches as errors (exit code 2)")
    strictness.add_argument("--lenient", action="store_true", help="Treat mismatches as warnings (exit code 1)")

    show = sub.add_parser("show", help="Display manifest details")
    show.add_argument("manifest_path", help="Clamp manifest path")
    view = show.add_mutually_exclusive_group()
    view.add_argument("--env", action="store_true", help="Display environment exports")
    view.add_argument("--summary", action="store_true", help="Display manifest summary")


def handle(ctx: CliContext, args: argparse.Namespace) -> MutableMapping[str, Any]:
    if not args.action:
        raise SystemExit("clamp command requires an action (capture, restore, verify, show)")
    action = args.action
    if action == "capture":
        return _handle_capture(ctx, args)
    if action == "restore":
        return _handle_restore(ctx, args)
    if action == "verify":
        return _handle_verify(ctx, args)
    if action == "show":
        return _handle_show(ctx, args)
    raise SystemExit(f"Unknown clamp action: {action}")


def _handle_capture(ctx: CliContext, args: argparse.Namespace) -> MutableMapping[str, Any]:
    output_dir = Path(args.output).expanduser()
    manifest_path = output_dir / "manifest.json"
    env_path = output_dir / "env.sh"

    if not args.force:
        for path in (manifest_path, env_path):
            if path.exists():
                ctx.warn(f"{path} already exists; use --force to overwrite")
                return {
                    "status": "warning",
                    "message": f"{path} already exists",
                    "path": str(path),
                }

    payload: Dict[str, Any] = {
        "target_path": args.target_path,
        "output_dir": str(output_dir),
    }
    if args.archive:
        payload["archive"] = True

    ctx.info(f"Capturing ROCm environment from {args.target_path} into {output_dir}")
    _ensure_bootstrapped()
    result = dispatch("clamp.capture", payload)
    _emit_human_output(ctx, "capture", result)
    return result


def _handle_restore(ctx: CliContext, args: argparse.Namespace) -> MutableMapping[str, Any]:
    manifest = Path(args.manifest_path).expanduser()
    if not manifest.exists():
        ctx.error(f"Manifest not found: {manifest}")
        return {
            "status": "error",
            "message": f"Manifest not found: {manifest}",
            "manifest_path": str(manifest),
        }

    ctx.info(f"Restoring environment from {manifest}")
    _ensure_bootstrapped()
    result = dispatch("clamp.restore", {"manifest_path": str(manifest)})

    env_vars = result.get("applied_env") or result.get("extra", {}).get("applied_env")
    if env_vars is None:
        env_vars = result.get("extra", {}).get("applied_env")

    if ctx.json_mode:
        if args.apply:
            result["apply_exports"] = _format_exports(env_vars or {})
        elif args.print:
            result["env_pairs"] = env_vars or {}
    else:
        if args.apply and env_vars:
            sys.stdout.write(_format_exports(env_vars))
            sys.stdout.flush()
        elif args.print and env_vars:
            for key, value in env_vars.items():
                print(f"{key}={value}")

    if not ctx.json_mode:
        _emit_human_output(ctx, "restore", result)
    return result


def _handle_verify(ctx: CliContext, args: argparse.Namespace) -> MutableMapping[str, Any]:
    manifest = Path(args.manifest_path).expanduser()
    if not manifest.exists():
        ctx.error(f"Manifest not found: {manifest}")
        return {
            "status": "error",
            "message": f"Manifest not found: {manifest}",
            "manifest_path": str(manifest),
        }

    ctx.info(f"Verifying environment with {manifest}")
    _ensure_bootstrapped()
    result = dispatch("clamp.verify", {"manifest_path": str(manifest)})

    status = str(result.get("status", "")).lower()
    if status == "fail":
        mismatches = result.get("mismatches") or result.get("extra", {}).get("mismatches") or []
        if mismatches and not ctx.json_mode:
            for mismatch in mismatches:
                field = mismatch.get("field")
                reason = mismatch.get("reason")
                ctx.warn(f"Mismatch: {field} ({reason})")

    if status == "fail" and args.lenient:
        result["status"] = "warning"
        result["lenient"] = True
    elif status == "fail" and args.strict:
        result["strict"] = True

    if not ctx.json_mode:
        _emit_human_output(ctx, "verify", result)
    return result


def _handle_show(ctx: CliContext, args: argparse.Namespace) -> MutableMapping[str, Any]:
    manifest = Path(args.manifest_path).expanduser()
    if not manifest.exists():
        ctx.error(f"Manifest not found: {manifest}")
        return {
            "status": "error",
            "message": f"Manifest not found: {manifest}",
            "manifest_path": str(manifest),
        }

    ctx.info(f"Loading manifest {manifest}")
    try:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.error(f"Failed to read manifest: {exc}")
        return {
            "status": "error",
            "message": str(exc),
            "manifest_path": str(manifest),
        }

    display_env = args.env
    if not args.env and not args.summary:
        display_env = False

    summary = {
        "status": "ok",
        "manifest_path": str(manifest),
        "manifest": manifest_payload,
    }

    if ctx.json_mode:
        if display_env:
            env_vars = manifest_payload.get("environment", {}).get("captured", {})
            summary["environment"] = env_vars
        else:
            summary["summary"] = _manifest_summary(manifest_payload)
        return summary

    if display_env:
        env_vars = manifest_payload.get("environment", {}).get("captured", {})
        for key, value in env_vars.items():
            print(f"{key}={value}")
    else:
        info = _manifest_summary(manifest_payload)
        for key, value in info.items():
            ctx.info(f"{key}: {value}")
    return summary


def _manifest_summary(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    target = manifest.get("target", {})
    system = manifest.get("system", {})
    gpu = manifest.get("gpu", {})
    return {
        "extension": manifest.get("extension"),
        "version": manifest.get("version"),
        "target_path": target.get("path"),
        "target_exists": target.get("exists"),
        "rocm_version": target.get("rocm_version"),
        "kernel": system.get("kernel"),
        "machine": system.get("machine"),
        "gpu_names": ", ".join(gpu.get("names", [])),
    }


def _emit_human_output(ctx: CliContext, action: str, result: Mapping[str, Any]) -> None:
    status = result.get("status", "ok")
    message = result.get("message")
    if message:
        ctx.info(message)
    else:
        ctx.info(f"{action} completed with status {status}")

    if action == "capture":
        artifacts = {
            "manifest_path": result.get("manifest_path"),
            "env_path": result.get("env_path"),
            "archive_path": result.get("archive_path"),
        }
        for key, value in artifacts.items():
            if value:
                ctx.info(f"{key}: {value}")


def _format_exports(env_vars: Mapping[str, Any]) -> str:
    lines = []
    for key, value in env_vars.items():
        lines.append(f"export {key}={shlex.quote(str(value))}")
    return "\n".join(lines) + ("\n" if lines else "")


def extract_exit_code(result: Mapping[str, Any]) -> int:
    status = str(result.get("status", "ok")).lower()
    return STATUS_EXIT.get(status, 0)
_BOOTSTRAPPED = False


def _ensure_bootstrapped() -> None:
    global _BOOTSTRAPPED
    if not _BOOTSTRAPPED:
        bootstrap_extensions()
        _BOOTSTRAPPED = True
