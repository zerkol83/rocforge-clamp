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
        def fake_collect():
            return {"auth": {"http_code": 200, "status": "success"}}

        def fake_update_cli(args):
            self.assertEqual(args, [])
            return 0

        def fake_resolve_cli(args):
            self.assertIn("--output", args)
            output_path = Path(args[args.index("--output") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(
                    {
                        "mode": "online",
                        "timestamp": "2024-01-01T00:00:00Z",
                        "resolved_at": "2024-01-01T00:00:00Z",
                        "image": "ghcr.io/rocm/dev:6.4.4-ubuntu-20.04@sha256:deadbeef",
                        "repository": "ghcr.io/rocm/dev",
                        "tag": "6.4.4-ubuntu-20.04",
                        "digest": "sha256:deadbeef",
                        "version": "6.4.4",
                        "os": "ubuntu-22.04",
                        "policy_mode": "strict",
                    }
                )
            )
            return 0

        with mock.patch("ci.rocforge_ci.__main__.collect_diagnostics", side_effect=fake_collect), mock.patch(
            "ci.rocforge_ci.__main__.update_module", return_value=DummyModule(fake_update_cli)
        ), mock.patch("ci.rocforge_ci.__main__.resolve_module", return_value=DummyModule(fake_resolve_cli)):
            rc = smart_bootstrap([])

        self.assertEqual(rc, 0)
        record = json.loads(CI_MODE_FILE.read_text())
        self.assertEqual(record["mode"], "online")
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
