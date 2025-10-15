"""
SysMon SNAPI extension providing live ROCm environment monitoring.
"""

from __future__ import annotations

import os
import select
import shutil
import signal
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from snapi import register_extension

from . import rocm_verifier


EXTENSION_ID = "sysmon_snapi"
EXTENSION_VERSION = "0.4.0"

COLOR_MAP = {
    "clean": "\033[32m",
    "degraded": "\033[33m",
    "conflicted": "\033[31m",
    "broken": "\033[31m",
}
RESET = "\033[0m"


def _colorize(text: str, state: str) -> str:
    if not sys.stdout.isatty():
        return text
    color = COLOR_MAP.get(state)
    if not color:
        return text
    return f"{color}{text}{RESET}"


def register():
    sys.stderr.write(f"[✓] SNAPI Loaded — sysmon_snapi v{EXTENSION_VERSION}\n")
    return register_extension(
        EXTENSION_ID,
        version=EXTENSION_VERSION,
        capabilities=["monitor"],
        commands={
            "monitor": monitor,
            "fingerprint": fingerprint,
        },
        metadata={"author": "RocFoundry"},
    )


def monitor(_: Mapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    payload = rocm_verifier.summarize()
    header = _screenfetch_output()
    summary_lines = _render_summary(payload)

    if not sys.stdout.isatty():
        for line in header:
            print(line)
        for line in summary_lines:
            print(line)
        metrics = _collect_metrics()
        output = {
            "status": "ok",
            "fingerprint": payload,
            "metrics": metrics,
        }
        sys.stderr.write("[⏹] SNAPI Stopped — sysmon_snapi\n")
        return output

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    stop_requested = False

    def _handle_sigint(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    prev_handler = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        while not stop_requested:
            metrics = _collect_metrics()
            _draw_screen(header, summary_lines, payload, metrics)
            if _input_ready(fd):
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    break
            time.sleep(1.0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        signal.signal(signal.SIGINT, prev_handler)
        sys.stderr.write("[⏹] SNAPI Stopped — sysmon_snapi\n")

    return {
        "status": "ok",
        "fingerprint": payload,
    }


def fingerprint(_: Mapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    return {
        "status": "ok",
        "fingerprint": rocm_verifier.summarize(),
    }


def _screenfetch_output() -> list[str]:
    cmd = shutil.which("screenfetch")
    if not cmd:
        return ["screenfetch not available"]
    rc = os.system(f"{cmd} -N > /tmp/.sysmon_screenfetch 2>/dev/null")
    if rc != 0:
        return ["screenfetch failed"]
    try:
        return Path("/tmp/.sysmon_screenfetch").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["screenfetch output unavailable"]


def _render_summary(info: Dict[str, Any]) -> list[str]:
    state = info.get("state") or "unknown"
    base_version = info.get("base_version") or "<unknown>"
    lines = [
        _colorize(f"ROCm Environment: {state.upper()}", state),
        f"Base Version: {base_version}",
        f"Fingerprint: {info.get('hash', '<none>')}",
    ]
    components = info.get("components", {})
    if components:
        lines.append("Components:")
        for name, version in sorted(components.items()):
            lines.append(f"  - {name}: {version}")
    if info.get("layers", {}).get("conflict", {}).get("ok") is False:
        lines.append(_colorize("❌ Multiple ROCm roots detected", "conflicted"))
    missing_libs = info.get("layers", {}).get("libraries", {}).get("details", {}).get("missing", {})
    missing = [comp for comp, libs in missing_libs.items() if libs]
    if missing:
        lines.append(_colorize(f"❌ Missing libraries: {', '.join(missing)}", "degraded"))
    runtime_ok = info.get("layers", {}).get("runtime", {}).get("ok")
    if not runtime_ok:
        lines.append(_colorize("❌ Runtime probes failed (rocminfo / rocm-smi)", "degraded"))
    return lines


def _collect_metrics() -> Dict[str, Any]:
    cpu = _cpu_usage()
    mem = _memory_usage()
    gpu = _gpu_usage()
    temp = _temperature()
    return {
        "cpu": cpu,
        "memory": mem,
        "gpu": gpu,
        "temperature": temp,
    }


def _draw_screen(header: list[str], summary: list[str], info: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    sys.stdout.write("\033[2J\033[H")
    for line in header:
        print(line)
    print("")
    for line in summary:
        print(line)
    print("")
    print(_render_bar("CPU", metrics["cpu"]))
    print(_render_bar("GPU", metrics["gpu"]))
    print(_render_bar("RAM", metrics["memory"]))
    print(_render_bar("TEMP", metrics["temperature"], unit="°C"))
    print("")
    print("Press Enter to exit.")
    sys.stdout.flush()


def _render_bar(label: str, value: Dict[str, Any], width: int = 40, unit: str = "%") -> str:
    percent = max(0.0, min(100.0, float(value.get("percent", 0.0))))
    filled = int(width * percent / 100.0)
    bar = "█" * filled + "-" * (width - filled)
    suffix = f"{percent:5.1f}{unit}"
    if label == "TEMP":
        suffix = f"{value.get('current', 0.0):5.1f}{unit}"
    return f"{label:<6} [{bar}] {suffix}"


def _cpu_usage() -> Dict[str, Any]:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            line = handle.readline()
        parts = [float(p) for p in line.split()[1:]]
        idle = parts[3]
        total = sum(parts)
    except (OSError, ValueError, IndexError):
        return {"percent": 0.0}

    time.sleep(0.1)
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            line2 = handle.readline()
        parts2 = [float(p) for p in line2.split()[1:]]
        idle2 = parts2[3]
        total2 = sum(parts2)
    except (OSError, ValueError, IndexError):
        return {"percent": 0.0}

    idle_delta = idle2 - idle
    total_delta = total2 - total
    percent = 0.0
    if total_delta:
        percent = (1.0 - idle_delta / total_delta) * 100.0
    return {"percent": max(0.0, min(100.0, percent))}


def _memory_usage() -> Dict[str, Any]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            data = handle.read()
        total = _extract_meminfo(data, "MemTotal")
        free = _extract_meminfo(data, "MemAvailable")
        if total:
            used = total - free
            percent = used / total * 100.0
            return {"percent": percent}
    except (OSError, ValueError):
        pass
    return {"percent": 0.0}


def _extract_meminfo(blob: str, key: str) -> float:
    for line in blob.splitlines():
        if line.startswith(key):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[1])
    return 0.0


def _gpu_usage() -> Dict[str, Any]:
    cmd = shutil.which("rocm-smi")
    if not cmd:
        return {"percent": 0.0}
    rc, stdout, _ = rocm_verifier._run_command([cmd, "--showuse"], timeout=2.0)  # type: ignore[attr-defined]
    if rc != 0 or not stdout:
        return {"percent": 0.0}
    percent = _parse_percentage(stdout)
    return {"percent": percent}


def _parse_percentage(output: str) -> float:
    for token in output.split():
        if token.endswith("%"):
            try:
                return float(token.rstrip("%"))
            except ValueError:
                continue
    return 0.0


def _temperature() -> Dict[str, Any]:
    zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for zone in zones:
        try:
            value = int(zone.read_text().strip()) / 1000.0
            return {"percent": min(100.0, value), "current": value}
        except (OSError, ValueError):
            continue
    return {"percent": 0.0, "current": 0.0}


def _input_ready(fd: int) -> bool:
    rlist, _, _ = select.select([fd], [], [], 0.0)
    return bool(rlist)
