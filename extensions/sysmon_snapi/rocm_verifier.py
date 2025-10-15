"""
ROCm environment verification utilities for sysmon_snapi.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROCM_PARENT = Path("/opt")
ROCM_GLOB = "rocm*"
VERSION_FILES = (
    ".info/version",
    ".info/version-dev",
    ".info/version.txt",
    "version.txt",
    "VERSION",
)
LIB_COMPONENTS = {
    "rocblas": ("librocblas.so",),
    "rocfft": ("librocfft.so",),
    "rocthrust": ("librocthrust.so", "librocprim.so"),
    "hip": ("libamdhip64.so",),
    "hsa": ("libhsa-runtime64.so",),
}
RUNTIME_PROBES = (
    ("rocminfo", ("--summary",)),
    ("rocm-smi", ("--showproductname",)),
)


@dataclass
class LayerResult:
    ok: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


def _run_command(cmd: Iterable[str], timeout: float = 5.0) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            list(cmd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, "", ""
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _read_version_file(root: Path) -> Optional[str]:
    for relative in VERSION_FILES:
        candidate = root / relative
        try:
            if candidate.exists():
                value = candidate.read_text(encoding="utf-8", errors="ignore").strip()
                if value:
                    return value
        except OSError:
            continue
    return None


def _list_rocm_roots() -> List[Path]:
    try:
        return sorted(p for p in ROCM_PARENT.glob(ROCM_GLOB) if p.is_dir())
    except OSError:
        return []


def _detect_components_from_libs(root: Path) -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for component, libs in LIB_COMPONENTS.items():
        for pattern in libs:
            for lib_dir in (root / "lib", root / "lib64"):
                candidate = lib_dir / pattern
                if candidate.exists():
                    version = _extract_version_from_filename(candidate.name)
                    if version:
                        versions[component] = version
                        break
            if component in versions:
                break
    return versions


def _extract_version_from_filename(name: str) -> Optional[str]:
    # Attempt to parse a semantic version from library filename suffixes.
    match = re.search(r"\.so(?:\.[\d._-]+)+$", name)
    if not match:
        return None
    trailing = match.group(0).lstrip(".so.")
    trailing = trailing.replace("-", ".").replace("_", ".")
    return trailing


def _fingerprint(data: Dict[str, Any]) -> str:
    blob = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _ldd_check(binary: Path) -> LayerResult:
    if not binary.exists():
        return LayerResult(False, f"{binary} missing")
    rc, stdout, _ = _run_command(["ldd", str(binary)])
    if rc != 0:
        return LayerResult(False, f"ldd returned {rc}")
    missing = [line.strip() for line in stdout.splitlines() if "not found" in line]
    return LayerResult(not missing, "ldd scan", {"missing": missing})


def _library_presence(root: Path) -> LayerResult:
    missing: Dict[str, List[str]] = {}
    for component, libs in LIB_COMPONENTS.items():
        found = False
        for pattern in libs:
            for lib_dir in (root / "lib", root / "lib64"):
                if (lib_dir / pattern).exists():
                    found = True
                    break
            if found:
                break
        if not found:
            missing[component] = list(libs)
    return LayerResult(not missing, "library presence", {"missing": missing})


def _runtime_probe() -> LayerResult:
    for command, args in RUNTIME_PROBES:
        rc, stdout, stderr = _run_command([command, *args])
        if rc == 0:
            return LayerResult(True, command, {"output": stdout})
    return LayerResult(False, "runtime probes failed", {"commands": [cmd for cmd, _ in RUNTIME_PROBES]})


def _conflict_check(roots: List[Path]) -> LayerResult:
    versions = [_read_version_file(root) for root in roots]
    versions = [v for v in versions if v]
    unique_versions = sorted(set(versions))
    conflicted = len(unique_versions) > 1 or len(roots) > 1
    return LayerResult(not conflicted, "conflict check", {"roots": [str(r) for r in roots], "versions": unique_versions})


def collect_rocm_state() -> Dict[str, Any]:
    roots = _list_rocm_roots()
    primary_root = roots[0] if roots else Path("/opt/rocm")
    base_version = _read_version_file(primary_root)
    components = _detect_components_from_libs(primary_root) if primary_root.exists() else {}

    ldd_result = _ldd_check(primary_root / "bin" / "hipcc") if primary_root.exists() else LayerResult(False, "hipcc missing")
    library_result = _library_presence(primary_root) if primary_root.exists() else LayerResult(False, "rocm root missing")
    runtime_result = _runtime_probe()
    conflict_result = _conflict_check(roots)

    degraded = any(
        not layer.ok
        for layer in (ldd_result, library_result, runtime_result)
    )
    conflicted = not conflict_result.ok

    if not primary_root.exists():
        state = "broken"
    elif conflicted:
        state = "conflicted"
    elif degraded:
        state = "degraded"
    else:
        state = "clean"

    details = {
        "state": state,
        "base_version": base_version,
        "components": components,
        "layers": {
            "conflict": conflict_result.__dict__,
            "ldd": ldd_result.__dict__,
            "libraries": library_result.__dict__,
            "runtime": runtime_result.__dict__,
            "roots": [str(r) for r in roots],
        },
    }
    details["hash"] = _fingerprint(
        {
            "state": state,
            "base_version": base_version,
            "components": components,
            "roots": details["layers"]["roots"],
        }
    )
    return details


def summarize() -> Dict[str, Any]:
    """
    Public helper returning the spec-compliant payload.
    """

    info = collect_rocm_state()
    return {
        "state": info.get("state"),
        "base_version": info.get("base_version"),
        "components": info.get("components", {}),
        "hash": info.get("hash"),
        "layers": info.get("layers"),
    }
