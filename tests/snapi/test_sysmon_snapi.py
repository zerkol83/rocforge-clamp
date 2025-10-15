import io
import contextlib
import unittest
from pathlib import Path

from engine import bootstrap_extensions
from snapi import dispatch, registry
from snapi.errors import ExtensionNotFound


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / "build" / "snapi_test.log"


def ensure_sysmon_registered() -> None:
    try:
        registry().get("sysmon_snapi")
    except ExtensionNotFound:
        bootstrap_extensions()


class SysmonSnapiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_sysmon_registered()

    def test_monitor_produces_metrics_and_logs(self) -> None:
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            result = dispatch("sysmon_snapi.monitor", {})

        stdout_text = stdout_buffer.getvalue()
        stderr_text = stderr_buffer.getvalue()
        metrics = result.get("metrics") or {}
        fingerprint = result.get("fingerprint") or {}

        self.assertEqual(result.get("status"), "ok")
        self.assertTrue(stdout_text.strip(), "monitor should emit terminal output")
        self.assertIn("ROCm Environment", stdout_text)
        self.assertIn("SNAPI Stopped", stderr_text)
        self.assertIn("state", fingerprint)
        self.assertIsInstance(metrics, dict)
        for key in ("cpu", "gpu", "memory", "temperature"):
            self.assertIn(key, metrics)

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write("=== sysmon_snapi monitor ===\n")
            handle.write(stdout_text)
            if not stdout_text.endswith("\n"):
                handle.write("\n")
            handle.write("--- stderr ---\n")
            handle.write(stderr_text)
            if not stderr_text.endswith("\n"):
                handle.write("\n")
            handle.write(f"status={result.get('status')}\n")

    def test_fingerprint_command_returns_state(self) -> None:
        result = dispatch("sysmon_snapi.fingerprint", {})
        fingerprint = result.get("fingerprint") or {}
        self.assertEqual(result.get("status"), "ok")
        self.assertIn("state", fingerprint)
        self.assertIsInstance(fingerprint, dict)


if __name__ == "__main__":
    unittest.main()
