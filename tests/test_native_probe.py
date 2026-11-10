from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.native_probe import run_probes

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "requires exact locally downloaded E-P5 stock input")
class NativeProbeTests(unittest.TestCase):
    def test_stock_debug_gate_zero_and_one(self):
        report = run_probes(IMAGE)
        self.assertEqual([case["wifi_requests"] for case in report["cases"]], [0, 1])
        for case in report["cases"]:
            self.assertTrue(case["reached_stop"])
            self.assertEqual(case["parameter_id"], 0xF971)
            self.assertEqual(case["delay_argument"], 5000)
            self.assertLess(case["instructions"], 100)
        self.assertFalse(report["physical_camera_test"])

    def test_native_csv_overlay_install_get_and_clear(self):
        report = run_probes(IMAGE)
        self.assertEqual([case["parsed_value"] for case in report["csv_cases"]], [0, 1])
        for case in report["csv_cases"]:
            self.assertEqual(case["after_clear"], 0)
            self.assertTrue(case["reached_stop"])
            self.assertEqual(case["wifi_requests"], case["parsed_value"])

    def test_ignored_upstream_decoder_cannot_override_generated_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            upstream = sandbox / "external/em10-fw"
            subprocess.run(["git", "clone", "--shared", "--quiet",
                            str(ROOT / "external/em10-fw"), str(upstream)], check=True)
            (upstream / "emu/isa.inc").write_text('#error "stale upstream decoder selected"\n')
            (sandbox / "tools").mkdir()
            for name in ("ep5_gate_probe.c", "native_probe.py"):
                shutil.copyfile(ROOT / "tools" / name, sandbox / "tools" / name)
            with patch("tools.native_probe.ROOT", sandbox), patch("tools.native_probe.UPSTREAM", upstream):
                report = run_probes(IMAGE)
            self.assertEqual(report["csv_cases"][1]["parsed_value"], 1)
            self.assertIn("build/native-probe/isa.inc", report["dependencies_sha256"])


if __name__ == "__main__":
    unittest.main()
