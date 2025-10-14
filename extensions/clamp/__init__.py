"""
Clamp SNAPI extension providing capture/restore/verify workflows.
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from snapi import register_extension
from snapi.metadata import CommandStatus, utc_timestamp

EXTENSION_ID = "clamp"
EXTENSION_VERSION = "0.1.0"
DEFAULT_TARGET = Path("/opt/rocm")
DEFAULT_OUTPUT = Path("build/clamp")
MANIFEST_FILENAME = "manifest.json"
ENV_SCRIPT_FILENAME = "env.sh"

LIBRARY_PROBES = (
    "libamdhip64.so",
    "libhiprtc.so",
    "librocblas.so",
)


@dataclass
class CaptureContext:
    target_path: Path
    output_dir: Path
    manifest_path: Path
    env_path: Path
    create_archive: bool
    archive_dir: Path


def _path_from_payload(payload: Mapping[str, Any], key: str, default: Path) -> Path:
    raw = payload.get(key)
    if not raw:
        return default
    return Path(str(raw)).expanduser().resolve()


def _build_capture_context(payload: Mapping[str, Any]) -> CaptureContext:
    target_path = _path_from_payload(payload, "target_path", DEFAULT_TARGET)
    output_dir = _path_from_payload(payload, "output_dir", DEFAULT_OUTPUT)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_name = payload.get("manifest_name", MANIFEST_FILENAME)
    env_name = payload.get("env_name", ENV_SCRIPT_FILENAME)
    manifest_path = (output_dir / manifest_name).resolve()
    env_path = (output_dir / env_name).resolve()
    archive_requested = bool(payload.get("archive"))
    archive_dir = output_dir / "archives"
    if archive_requested:
        archive_dir.mkdir(parents=True, exist_ok=True)
    return CaptureContext(
        target_path=target_path,
        output_dir=output_dir,
        manifest_path=manifest_path,
        env_path=env_path,
        create_archive=archive_requested,
        archive_dir=archive_dir,
    )


def _detect_rocm_version(target: Path) -> Optional[str]:
    candidates = [
        target / ".info" / "version",
        target / ".info" / "version-dev",
        target / ".info" / "version-num",
        target / "version.txt",
        target / "VERSION",
    ]
    for path in candidates:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    hip_version_file = target / "bin" / "hipconfig"
    if hip_version_file.exists():
        try:
            import subprocess

            proc = subprocess.run(
                [str(hip_version_file), "--version"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
        except (OSError, ValueError):
            return None
        if proc.returncode == 0:
            return proc.stdout.strip()
    return None


def _probe_libraries(target: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    search_dirs = [target / "lib", target / "lib64"]
    lib_dir = target / "lib"
    if lib_dir.exists():
        for child in lib_dir.iterdir():
            if child.is_dir():
                search_dirs.append(child)
    for name in LIBRARY_PROBES:
        for directory in search_dirs:
            candidate = directory / name
            if candidate.exists():
                result[name] = str(candidate.resolve())
                break
    return result


def _collect_gpu_info(target: Path) -> Tuple[Iterable[str], str]:
    rocminfo = target / "bin" / "rocminfo"
    if not rocminfo.exists():
        return [], "unavailable"
    try:
        import subprocess

        proc = subprocess.run(
            [str(rocminfo)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, ValueError):
        return [], "rocminfo_failed"
    if proc.returncode != 0:
        return [], "rocminfo_error"
    names: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.lower().startswith("name:"):
            names.append(line.split(":", 1)[1].strip())
    return names, "rocminfo"


def _prepend_path(value: str, new_segment: str) -> str:
    if not value:
        return new_segment
    if value.split(":")[0] == new_segment:
        return value
    return f"{new_segment}:{value}"


def _captured_environment(target: Path) -> Dict[str, str]:
    captured: Dict[str, str] = {}
    target_bin = target / "bin"
    target_lib = target / "lib"
    target_lib64 = target / "lib64"
    env = os.environ.copy()
    captured["ROCM_PATH"] = str(target)
    captured["HIP_PATH"] = str(target)
    captured["HSA_PATH"] = str(target / "hsa")
    path_value = env.get("PATH", "")
    if target_bin.exists():
        path_value = _prepend_path(path_value, str(target_bin))
    captured["PATH"] = path_value
    ld_library = env.get("LD_LIBRARY_PATH", "")
    if target_lib64.exists():
        ld_library = _prepend_path(ld_library, str(target_lib64))
    if target_lib.exists():
        ld_library = _prepend_path(ld_library, str(target_lib))
    captured["LD_LIBRARY_PATH"] = ld_library
    lib_path = env.get("LIBRARY_PATH", "")
    if target_lib.exists():
        lib_path = _prepend_path(lib_path, str(target_lib))
    if target_lib64.exists():
        lib_path = _prepend_path(lib_path, str(target_lib64))
    captured["LIBRARY_PATH"] = lib_path
    return captured


def _write_env_script(env_path: Path, env_vars: Mapping[str, str]) -> None:
    lines = ["#!/usr/bin/env bash", "# Clamp environment exports", "set -euo pipefail"]
    for key, value in env_vars.items():
        quoted = shlex.quote(value)
        lines.append(f"export {key}={quoted}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o755)
    except OSError:
        pass


def _archive_rocm(target: Path, destination_dir: Path) -> Optional[Path]:
    timestamp = utc_timestamp().replace(":", "").replace("-", "")
    archive_path = destination_dir / f"rocm-{timestamp}.tar.gz"
    try:
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(str(target), arcname=target.name)
    except (OSError, tarfile.TarError):
        return None
    return archive_path


def capture(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    ctx = _build_capture_context(payload)
    target_exists = ctx.target_path.exists()
    rocm_version = _detect_rocm_version(ctx.target_path) if target_exists else None
    libraries = _probe_libraries(ctx.target_path) if target_exists else {}
    gpu_names, gpu_source = _collect_gpu_info(ctx.target_path) if target_exists else ([], "skipped")
    kernel_release = platform.uname().release

    env_vars = _captured_environment(ctx.target_path)
    _write_env_script(ctx.env_path, env_vars)

    artifacts = {
        "manifest_path": str(ctx.manifest_path),
        "env_path": str(ctx.env_path),
    }

    archive_path: Optional[Path] = None
    if ctx.create_archive and target_exists:
        archive_path = _archive_rocm(ctx.target_path, ctx.archive_dir)
        if archive_path:
            artifacts["archive_path"] = str(archive_path)

    manifest = {
        "extension": EXTENSION_ID,
        "version": EXTENSION_VERSION,
        "generated_at": utc_timestamp(),
        "target": {
            "path": str(ctx.target_path),
            "exists": target_exists,
            "rocm_version": rocm_version,
            "libraries": libraries,
        },
        "system": {
            "kernel": kernel_release,
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "gpu": {
            "names": list(gpu_names),
            "source": gpu_source,
        },
        "environment": {
            "captured": env_vars,
            "source": "capture",
        },
        "artifacts": artifacts,
    }

    ctx.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = "ok" if target_exists else "missing"
    message = "Clamp capture completed" if target_exists else f"ROCm path {ctx.target_path} not found"

    cmd_status = CommandStatus(status=status, message=message, extra=artifacts)
    response: MutableMapping[str, Any] = cmd_status.asdict()
    response["manifest"] = manifest
    return response


def _load_manifest(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load manifest at {path}: {exc}") from exc


def restore(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    manifest_path = payload.get("manifest_path")
    env_path = payload.get("env_path")
    manifest: Optional[Dict[str, Any]] = None
    if manifest_path:
        manifest = _load_manifest(Path(manifest_path))
    elif env_path:
        manifest_path = None
    else:
        return {
            "status": "error",
            "message": "restore requires manifest_path or env_path",
        }

    env_vars: Dict[str, str]
    if manifest:
        env_vars = dict(manifest.get("environment", {}).get("captured", {}))
        target_info = manifest.get("target", {})
        target_path = Path(target_info.get("path", DEFAULT_TARGET))
        missing_paths: list[str] = []
        for probe in target_info.get("libraries", {}).values():
            if probe and not Path(probe).exists():
                missing_paths.append(probe)
        status = "ok" if target_path.exists() and not missing_paths else "warn"
        message = "Environment prepared from manifest"
        if missing_paths:
            message += f"; missing libraries: {len(missing_paths)}"
        response: MutableMapping[str, Any] = CommandStatus(
            status=status,
            message=message,
            extra={
                "applied_env": env_vars,
                "manifest_path": manifest_path,
                "missing": missing_paths,
            },
        ).asdict()
        response["shell_hint"] = f"source {manifest.get('artifacts', {}).get('env_path', 'env.sh')}"
        return response

    # env_path branch (without manifest) - parse simple KEY=VALUE exports
    env_vars = {}
    parsed_path = Path(str(env_path))
    try:
        for line in parsed_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or not line.startswith("export "):
                continue
            key, _, value = line[len("export ") :].partition("=")
            env_vars[key.strip()] = value.strip().strip("'\"")
    except OSError as exc:
        return {
            "status": "error",
            "message": f"Failed to read env script {env_path}: {exc}",
        }

    response = CommandStatus(
        status="ok",
        message="Environment prepared from env script",
        extra={
            "applied_env": env_vars,
            "env_path": str(parsed_path),
        },
    ).asdict()
    response["shell_hint"] = f"source {parsed_path}"
    return response


def verify(payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
    manifest_path = payload.get("manifest_path")
    if not manifest_path:
        return {
            "status": "error",
            "message": "verify requires manifest_path",
        }
    manifest = _load_manifest(Path(manifest_path))
    target_info = manifest.get("target", {})
    target_path = Path(target_info.get("path", DEFAULT_TARGET))
    mismatches: list[Dict[str, Any]] = []

    if not target_path.exists():
        mismatches.append(
            {
                "field": "target.path",
                "expected": str(target_path),
                "actual": None,
                "reason": "missing",
            }
        )
    recorded_version = target_info.get("rocm_version")
    current_version = _detect_rocm_version(target_path) if target_path.exists() else None
    if recorded_version and current_version and recorded_version != current_version:
        mismatches.append(
            {
                "field": "target.rocm_version",
                "expected": recorded_version,
                "actual": current_version,
                "reason": "version_mismatch",
            }
        )
    for name, lib_path in target_info.get("libraries", {}).items():
        if lib_path and not Path(lib_path).exists():
            mismatches.append(
                {
                    "field": f"target.libraries.{name}",
                    "expected": lib_path,
                    "actual": None,
                    "reason": "missing_library",
                }
            )

    status = "pass" if not mismatches else "fail"
    message = "Clamp verification passed" if not mismatches else "Clamp verification detected mismatches"
    response = CommandStatus(
        status=status,
        message=message,
        extra={
            "manifest_path": manifest_path,
            "mismatches": mismatches,
        },
    ).asdict()
    return response


def register():
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["capture", "restore", "verify"],
        commands={
            "capture": capture,
            "restore": restore,
            "verify": verify,
        },
        metadata={"default_target": str(DEFAULT_TARGET)},
    )
