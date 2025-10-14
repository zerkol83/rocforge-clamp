"""
Utility helpers for GHCR diagnostics and environment inspection.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from typing import Any, Dict


def _parse_http_code(output: str) -> int | None:
    for line in output.splitlines():
        if line.startswith("HTTP/"):
            match = re.search(r"HTTP/\d\.\d\s+(\d+)", line)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None
    return None


def collect_diagnostics() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "environment": {
            "GHCR_USER": os.getenv("GHCR_USER") or "",
            "GHCR_TOKEN_length": len(os.getenv("GHCR_TOKEN") or ""),
            "GITHUB_TOKEN_length": len(os.getenv("GITHUB_TOKEN") or ""),
        },
        "dns": {},
        "auth": {
            "status": "no_token",
            "http_code": None,
            "message": "",
        },
    }

    try:
        addr = socket.gethostbyname("ghcr.io")
        info["dns"] = {"status": "ok", "address": addr}
    except socket.gaierror as exc:
        info["dns"] = {"status": "error", "error": str(exc)}

    user = os.getenv("GHCR_USER") or "token"
    token = os.getenv("GHCR_TOKEN") or os.getenv("GITHUB_TOKEN")

    if token:
        cmd = [
            "curl",
            "-sI",
            "-u",
            f"{user}:{token}",
            "https://ghcr.io/v2/",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            http_code = _parse_http_code(result.stdout)
            info["auth"]["http_code"] = http_code
            if result.returncode == 0:
                if http_code == 200:
                    status = "success"
                elif http_code == 401:
                    status = "unauthorized"
                elif http_code == 405:
                    status = "method_not_allowed"
                elif http_code:
                    status = f"http_{http_code}"
                else:
                    status = "unknown_response"
                info["auth"]["status"] = status
                info["auth"]["message"] = (result.stdout.strip().splitlines() or [""])[0]
            else:
                info["auth"]["status"] = "request_failed"
                info["auth"]["message"] = result.stderr.strip() or result.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            info["auth"]["status"] = "error"
            info["auth"]["message"] = str(exc)
    else:
        info["auth"]["message"] = "No GHCR_TOKEN or GITHUB_TOKEN exported."

    return info


def diagnostics_json() -> str:
    return json.dumps(collect_diagnostics(), indent=2)
