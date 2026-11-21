import struct
import tempfile
import unittest
from pathlib import Path
import zlib

import numpy as np

from ep5studio.project import Binding, Project
from ep5studio.wire import pack_index, pack_lut, unpack_index
from tools.render_sd_photo import build_driver, run_frame


class SDPhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.exe = build_driver(Path(tmp.name))
        cls.pixels = np.random.default_rng(879).integers(0, 256, (48, 64, 2), dtype=np.uint8).tobytes()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.card = Path(tmp.name)
        self.folder = self.card / "EP5LUT"
        self.folder.mkdir()

    def setup_card(self, transform=False):
        axis = np.rint(np.arange(17) * (65535 / 16)).astype("<u2")
        b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
        data = np.stack((b, r, g) if transform else (r, g, b), axis=-1).astype("<u2").tobytes()
        key = "a" * 64
        project = Project("photo-test", (Binding("light-tone-i", key, "Trial", 256),))
        index = pack_index(project, {key: 1}, {key: zlib.crc32(data)})
        (self.folder / "INDEX.EP5").write_bytes(index)
        (self.folder / "L0000001.LUT").write_bytes(pack_lut(1, data))
        return unpack_index(index)[0]

    def render(self, row, **kw):
        return run_frame(self.exe, self.card, row, 64, 48, self.pixels, **kw)

    def test_identity_zero_and_bad_table(self):
        row = self.setup_card()
        result, out = self.render(row)
        self.assertEqual((result["result"], out), (1, self.pixels))
        row = self.setup_card(True)
        zero, out = self.render(row, amount=0, fx=(100, 100, 100))
        self.assertEqual((zero["result"], out), (0, self.pixels))
        path = self.folder / "L0000001.LUT"
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        bad, out = self.render(row, fx=(100, 100, 100))
        self.assertEqual((bad["result"], bad["preload"], out), (0, 4, self.pixels))

    def test_mid_colour_and_mid_fx_cancel_never_publish_partial_frame(self):
        row = self.setup_card(True)
        for stop in (0, 16, 49, 96):
            with self.subTest(stop=stop):
                report, out = self.render(row, stop=stop, fx=(20, 30, 0))
                self.assertEqual((report["result"], out), (-2 if not stop else -3, b""))
                self.assertTrue(report["released"])

    def test_saved_wheel_changes_only_matching_colour_table(self):
        row = self.setup_card()
        axes = bytes([9] + [0] * 35)
        saved = self.card / "edit.bin"

        def set_wheel(crc):
            head = struct.pack("<4sBBHBBHI", b"EP5W", 1, 12, row["picture_mode"], row["variant"], 1, 0, crc)
            saved.write_bytes(head + axes + struct.pack("<I", zlib.crc32(head + axes)))
        set_wheel(row["table_crc32"])
        styled, pixels = self.render(row, wheel=saved)
        self.assertEqual(styled["result"], 1)
        self.assertNotEqual(pixels, self.pixels)
        set_wheel(row["table_crc32"] ^ 1)
        self.assertEqual(self.render(row, wheel=saved)[1], self.pixels)

    def test_card_wheel_automatically_reaches_photo_after_restart(self):
        row = self.setup_card()
        head = struct.pack("<4sBBHBBHI", b"EP5W", 1, 12, row["picture_mode"], row["variant"],
                           row["number"], 0, row["table_crc32"])
        raw = head + bytes([9] + [0] * 35)
        record = raw + struct.pack("<I", zlib.crc32(raw))
        # Light Tone I is the fourth menu slot even on a one-look card.
        saved = self.folder / "W04.EP5"
        saved.write_bytes(record)
        state, edited = self.render(row)
        self.assertTrue(state["wheel"])
        self.assertNotEqual(edited, self.pixels)
        self.assertEqual(self.render(row)[1], edited)
        self.assertEqual(self.render(row, amount=0)[1], self.pixels)
        saved.write_bytes(record + b"x")
        state, fallback = self.render(row)
        self.assertFalse(state["wheel"])
        self.assertEqual(fallback, self.pixels)


if __name__ == "__main__":
    unittest.main()
