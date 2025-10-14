import json
import stat
import tempfile
import unittest
from pathlib import Path

from engine import bootstrap_extensions
from snapi import dispatch


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _create_fake_rocm(root: Path) -> None:
    info_dir = root / ".info"
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / "version").write_text("5.7.1\n", encoding="utf-8")
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    hipconfig = bin_dir / "hipconfig"
    hipconfig.write_text("#!/usr/bin/env bash\necho 5.7.1\n", encoding="utf-8")
    _make_executable(hipconfig)
    lib_dir = root / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / "librocblas.so").write_text("", encoding="utf-8")
    (lib_dir / "libhiprtc.so").write_text("", encoding="utf-8")


class ClampSnapiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bootstrap_extensions()

    def test_capture_restore_verify_cycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake_rocm = tmp / "rocm"
            fake_rocm.mkdir()
            _create_fake_rocm(fake_rocm)
            output_dir = tmp / "out"
            result = dispatch(
                "clamp.capture",
                {"target_path": str(fake_rocm), "output_dir": str(output_dir), "archive": False},
            )

            self.assertEqual(result["status"], "ok")
            manifest_path = Path(result["manifest_path"])
            env_path = Path(result["env_path"])
            self.assertTrue(manifest_path.exists())
            self.assertTrue(env_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["target"]["path"], str(fake_rocm.resolve()))
            self.assertEqual(manifest["target"]["rocm_version"], "5.7.1")
            libs = manifest["target"]["libraries"]
            self.assertIn("librocblas.so", libs)
            self.assertTrue(Path(libs["librocblas.so"]).exists())

            restore = dispatch("clamp.restore", {"manifest_path": str(manifest_path)})
            self.assertEqual(restore["status"], "ok")
            applied_env = restore["applied_env"]
            self.assertEqual(applied_env["ROCM_PATH"], str(fake_rocm.resolve()))
            self.assertTrue(applied_env["PATH"].startswith(str((fake_rocm / "bin").resolve())))

            verify = dispatch("clamp.verify", {"manifest_path": str(manifest_path)})
            self.assertEqual(verify["status"], "pass")
            self.assertFalse(verify["mismatches"])

    def test_verify_detects_missing_library(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake_rocm = tmp / "rocm"
            fake_rocm.mkdir()
            _create_fake_rocm(fake_rocm)
            output_dir = tmp / "out"
            capture = dispatch("clamp.capture", {"target_path": str(fake_rocm), "output_dir": str(output_dir)})
            manifest_path = Path(capture["manifest_path"])
            (fake_rocm / "lib" / "librocblas.so").unlink()
            verify = dispatch("clamp.verify", {"manifest_path": str(manifest_path)})
            self.assertEqual(verify["status"], "fail")
            mismatches = verify["mismatches"]
            self.assertTrue(any(entry.get("field") == "target.libraries.librocblas.so" for entry in mismatches))


if __name__ == "__main__":
    unittest.main()
