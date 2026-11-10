from pathlib import Path
import json
import struct
import subprocess
import tempfile
import unittest

from tools.check_mn103_lut import validate_target, validate_film_target
from tools.native_probe import build_probe

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "toolchains/mn103/bin/mn10300-elf-as").exists(), "requires MN103 binutils")
class RunnerMemoryTests(unittest.TestCase):
    def test_runner_prefetch_readonly_regions_and_alignment(self):
        build = ROOT / "build/lut-runner-check"
        runner = build_probe(ROOT / "tools/lut_mn103_probe.c", build)
        xbin = ROOT / "toolchains/mn103/bin"
        cases = [("valid", "mov -1,d0\nmov 0x1100001c,a0\nmov d0,(a0)", None),
                 ("readonly", "mov 0x13000000,a0\nmov 0,d0\nmov d0,(a0)", "write outside"),
                 ("alignment", "mov 0x12000011,a0\nmov 0,d0\nmov d0,(a0)", "misaligned")]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "lut").write_bytes(bytes(29478))
            (directory / "pixels").write_bytes(bytes(64))
            (directory / "request").write_bytes(struct.pack("<8I", 0x12000010, 48, 1, 1, 3, 0x13000000, 14739, 0xabababab))
            for name, body, error in cases:
                with self.subTest(name=name):
                    source = directory / "code.s"
                    source.write_text(f".text\n.global _ep5_probe\n_ep5_probe:\n{body}\njmp _ep5_probe_done\n")
                    subprocess.run([str(xbin / "mn10300-elf-as"), str(source), "-o", str(directory / "code.o")], check=True)
                    subprocess.run([str(xbin / "mn10300-elf-ld"), "-T", str(ROOT / "tests/fixtures/lut_target.ld"),
                                    str(directory / "code.o"), "-o", str(directory / "code.elf")], check=True)
                    subprocess.run([str(xbin / "mn10300-elf-objcopy"), "-O", "binary", "-j", ".text",
                                    str(directory / "code.elf"), str(directory / "code.bin")], check=True)
                    result = subprocess.run([str(runner), str(directory / "code.bin"), str(directory / "lut"),
                                             str(directory / "pixels"), str(directory / "request"),
                                             str(directory / "output")], capture_output=True, text=True, timeout=10)
                    if error:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(error, result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(json.loads(result.stdout)["result_u32"], 0xffffffff)
                        self.assertEqual((directory / "output").read_bytes(), bytes(64))


@unittest.skipUnless((ROOT / "toolchains/mn103/bin/mn10300-elf-gcc").exists(),
                     "requires locally built MN103 GCC")
class TargetKernelTests(unittest.TestCase):
    def test_film_engine_descriptor_and_cancellation_match_host(self):
        report = validate_film_target()
        self.assertFalse(report["physical_camera_test"])
        self.assertTrue(report["plain_mn103_instruction_set"])
        cases = {case["name"]: case for case in report["cases"]}
        self.assertEqual(cases["identity"]["result"], 0)
        self.assertEqual(cases["cancel_before"]["result"], -2)
        self.assertEqual(cases["cancel_partial"]["result"], -3)
        self.assertEqual(cases["descriptor_crop"]["result"], 0)
        self.assertEqual(cases["bad_descriptor"]["result"], -1)
        self.assertEqual(cases["extent_overflow"]["result"], -1)
        self.assertGreaterEqual(len(cases), 12)
        for case in cases.values():
            self.assertTrue(case["matches_host"])
            self.assertTrue(case["guard_bytes_preserved"])

    def test_target_matches_host_and_rejects_invalid_extents(self):
        report = validate_target()
        self.assertFalse(report["physical_camera_test"])
        self.assertTrue(report["plain_mn103_instruction_set"])
        cases = {case["name"]: case for case in report["cases"]}
        self.assertTrue({"identity", "warm_negative", "capacity", "stride", "width_overflow",
                         "extent_overflow", "lut_count"}.issubset(cases))
        for name, case in cases.items():
            self.assertTrue(case["matches_host"], name)
            self.assertTrue(case["guard_bytes_preserved"], name)
            self.assertGreater(case["instructions"], 0, name)
            self.assertEqual(case["result"], 0 if name in ("identity", "warm_negative") else -1)


if __name__ == "__main__":
    unittest.main()
