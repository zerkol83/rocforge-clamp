import unittest

from extensions.sysmon_snapi import rocm_verifier


class RocmVerifierTests(unittest.TestCase):
    def test_summarize_returns_expected_keys(self):
        info = rocm_verifier.summarize()
        self.assertIn("state", info)
        self.assertIn("components", info)
        self.assertIn("hash", info)
        # ensure hash appears stable for same call
        info2 = rocm_verifier.summarize()
        self.assertEqual(info["hash"], info2["hash"])


if __name__ == "__main__":
    unittest.main()
