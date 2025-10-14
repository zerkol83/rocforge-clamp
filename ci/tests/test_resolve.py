import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.rocforge_ci import resolve  # noqa: E402


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cwd = Path.cwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        (Path("ci")).mkdir(exist_ok=True)
        for name in ("rocm_matrix.yml", "rocm_matrix_fallback.yml"):
            src = ROOT / "ci" / name
            if src.exists():
                (Path("ci") / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        Path("images").mkdir(exist_ok=True)
        for item in (ROOT / "images").glob("*.tar.gz"):
            (Path("images") / item.name).write_bytes(item.read_bytes())

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_resolve_prefers_local_tarball(self):
        matrix_path = Path("ci/rocm_matrix.yml")
        expected_hash = "dc6c257646e1ed09f4eacff5594b12b8adb4c31f6917d337ca09925d536e629a"

        with mock.patch("ci.rocforge_ci.resolve.docker_load_tarball") as mocked_load, \
             mock.patch("ci.rocforge_ci.resolve.docker_pull_image") as mocked_pull, \
             mock.patch("ci.rocforge_ci.resolve.docker_tag_image") as mocked_tag, \
             mock.patch("ci.rocforge_ci.resolve.compute_file_sha256", return_value=expected_hash):
            resolved = resolve.resolve_image(matrix_path=matrix_path, offline=False, prefer_local=True)

        mocked_load.assert_called_once()
        mocked_pull.assert_not_called()
        mocked_tag.assert_called()
        self.assertEqual(resolved.mode, "local")
        self.assertEqual(resolved.sha256, expected_hash)


if __name__ == "__main__":
    unittest.main()
