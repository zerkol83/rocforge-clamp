import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cli import rocfoundry


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _create_fake_rocm(root: Path) -> None:
    info_dir = root / ".info"
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / "version").write_text("6.0.0\n", encoding="utf-8")
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    hipconfig = bin_dir / "hipconfig"
    hipconfig.write_text("#!/usr/bin/env bash\necho 6.0.0\n", encoding="utf-8")
    _make_executable(hipconfig)
    lib_dir = root / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / "librocblas.so").write_text("", encoding="utf-8")
    (lib_dir / "libhiprtc.so").write_text("", encoding="utf-8")


class ClampCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.fake_rocm = self.root / "rocm"
        self.fake_rocm.mkdir()
        _create_fake_rocm(self.fake_rocm)
        self.output_dir = self.root / "out"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_cli(self, *args: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = rocfoundry.main(list(args))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_cli_clamp_capture(self):
        code, out, _ = self._run_cli(
            "--json",
            "--quiet",
            "clamp",
            "capture",
            str(self.fake_rocm),
            "--output",
            str(self.output_dir),
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        manifest_path = Path(payload["manifest_path"])
        env_path = Path(payload["env_path"])
        self.assertTrue(manifest_path.exists())
        self.assertTrue(env_path.exists())

    def test_cli_clamp_restore_print(self):
        self.test_cli_clamp_capture()
        manifest = self.output_dir / "manifest.json"
        code, out, _ = self._run_cli(
            "--json",
            "--quiet",
            "clamp",
            "restore",
            str(manifest),
            "--print",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        env_pairs = payload.get("env_pairs") or payload.get("applied_env")
        self.assertIsInstance(env_pairs, dict)
        self.assertIn("ROCM_PATH", env_pairs)

    def test_cli_clamp_verify_and_lenient(self):
        self.test_cli_clamp_capture()
        manifest = self.output_dir / "manifest.json"
        code, out, _ = self._run_cli(
            "--json",
            "--quiet",
            "clamp",
            "verify",
            str(manifest),
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "pass")

        # Remove a library to trigger mismatch
        librocblas = self.fake_rocm / "lib" / "librocblas.so"
        librocblas.unlink()
        code, out, _ = self._run_cli(
            "--json",
            "--quiet",
            "clamp",
            "verify",
            str(manifest),
            "--lenient",
        )
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertIn("status", payload)
        self.assertIn("mismatches", payload)


if __name__ == "__main__":
    unittest.main()
