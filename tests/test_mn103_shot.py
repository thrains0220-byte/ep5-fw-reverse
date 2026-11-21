"""Run the shutter-to-encoder handoff on compiled MN103 instructions under Linux/WSL."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.check_mn103_lut import ROOT, X, compile_target
from tools.native_probe import build_probe


@unittest.skipUnless((X / "mn10300-elf-gcc").is_file(), "requires MN103 GCC")
class TargetShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.work = Path(temp.name)
        _, _, _, cls.target = compile_target(
            cls.work, ROOT / "tests/fixtures/shot_target.c",
            [ROOT / "firmware" / f"{module}.c" for module in
             ("film_shot", "film_photo", "film", "film_fx", "lut", "lut_preload", "lut_wheel")],
            optimization="-Os",
        )
        cls.runner = build_probe(ROOT / "tools/lut_mn103_probe.c", cls.work)
        (cls.work / "black").write_bytes(bytes(17**3 * 3 * 2))

    def check_shot(self, scenario, *, result, calls, styled):
        # Guard the effective frame on both sides and in between its two rows.
        pixels = bytearray([0xa5] * 48)
        for start in (16, 24):
            pixels[start:start + 4] = bytes((170, 128, 220, 128))
        src, dst, config = (self.work / f"{name}-{scenario}" for name in ("src", "dst", "cfg"))
        src.write_bytes(pixels)
        config.write_bytes(struct.pack("<8I", scenario, 0, 0, 0, 0, 0, 0, 0xdeadbeef))
        proc = subprocess.run([self.runner, self.target, self.work / "black", src, config, dst],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["reached_stop"])
        claims, submits, discards = calls
        expected = (1 << 24) | (claims << 20) | (submits << 16) | (discards << 12) | (result & 255)
        self.assertEqual(report["result_u32"], expected)
        if styled:
            for start in (16, 24):
                pixels[start:start + 4] = bytes((0, 128, 0, 128))
        self.assertEqual(dst.read_bytes(), bytes(pixels))

    def test_card_change_after_shutter_keeps_original_table(self):
        self.check_shot(0, result=1, calls=(1, 1, 0), styled=True)

    def test_cancel_before_frame_ready(self):
        self.check_shot(1, result=-4, calls=(0, 0, 0), styled=False)

    def test_original_owner_retains_frame(self):
        self.check_shot(2, result=2, calls=(1, 0, 0), styled=False)

    def test_encoder_rejects_already_styled_frame(self):
        self.check_shot(3, result=-3, calls=(1, 1, 1), styled=True)
