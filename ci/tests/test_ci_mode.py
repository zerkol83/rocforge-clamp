import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.rocforge_ci.__main__ import (  # noqa: E402
    CI_MODE_FILE,
    mode_command,
    offline_bootstrap,
    smart_bootstrap,
)
from ci.rocforge_ci.resolve import ResolvedImage  # noqa: E402


class DummyModule:
    def __init__(self, handler):
        self._handler = handler

    def cli(self, args):
        return self._handler(args)


class CiModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cwd = Path.cwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        local_ci = Path("ci")
        local_ci.mkdir(exist_ok=True)
        for name in ("rocm_matrix.yml", "rocm_matrix_fallback.yml"):
            src = ROOT / "ci" / name
            if src.exists():
                target = local_ci / name
                target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        local_images = Path("images")
        local_images.mkdir(exist_ok=True)
        src_images = ROOT / "images"
        if src_images.exists():
            for item in src_images.glob("*.tar.gz"):
                (local_images / item.name).write_bytes(item.read_bytes())

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_offline_bootstrap_records_mode_and_snapshot(self):
        rc = offline_bootstrap([])
        self.assertEqual(rc, 0)
        self.assertTrue(CI_MODE_FILE.exists())
        record = json.loads(CI_MODE_FILE.read_text())
        self.assertEqual(record["mode"], "offline")
        snapshot_path = Path(record["snapshot"])
        self.assertTrue(snapshot_path.exists())
        payload = json.loads(snapshot_path.read_text())
        self.assertEqual(payload["mode"], "offline")
        self.assertIn("timestamp", payload)
        self.assertEqual(payload["timestamp"], payload["resolved_at"])

    def test_smart_bootstrap_online_records_mode(self):
        resolved = ResolvedImage(
            image="ghcr.io/zerkol83/rocm-dev:6.4.4-ubuntu-20.04",
            repository="ghcr.io/zerkol83/rocm-dev",
            tag="6.4.4-ubuntu-20.04",
            digest="",
            version="6.4.4-ubuntu-20.04",
            os_name="ubuntu-20.04",
            policy_mode="static",
            signer=None,
            mode="local",
            tarball="images/rocm-dev-6.4.4-ubuntu-20.04.tar.gz",
            sha256="dc6c257646e1ed09f4eacff5594b12b8adb4c31f6917d337ca09925d536e629a",
            canonical="rocforge/rocm-dev:6.4.4-ubuntu-20.04",
        )

        def fake_collect():
            return {"auth": {"http_code": 200, "status": "success"}}

        with mock.patch("ci.rocforge_ci.__main__.collect_diagnostics", side_effect=fake_collect), mock.patch(
            "ci.rocforge_ci.__main__.resolve_image", return_value=resolved
        ), mock.patch("ci.rocforge_ci.__main__.verify_module") as verify_mod:
            verify_mod().cli.return_value = 0
            rc = smart_bootstrap([])

        self.assertEqual(rc, 0)
        record = json.loads(CI_MODE_FILE.read_text())
        self.assertEqual(record["mode"], "local")
        self.assertEqual(record["snapshot"], "build/rocm_snapshot.json")
        self.assertIn("timestamp", record)

    def test_mode_show_and_reset(self):
        CI_MODE_FILE.write_text(json.dumps({"mode": "offline", "timestamp": "2024-01-01T00:00:00Z"}) + "\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mode_command(["show"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["mode"], "offline")

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mode_command(["reset"])
        self.assertEqual(rc, 0)
        reset_payload = json.loads(buf.getvalue().strip())
        self.assertEqual(reset_payload["status"], "reset")
        self.assertFalse(CI_MODE_FILE.exists())


if __name__ == "__main__":
    unittest.main()
