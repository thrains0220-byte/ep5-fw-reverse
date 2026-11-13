"""Regression for the native film-look curve fitter and pack builder.

The curve-format and container checks run anywhere (pure Python + numpy). The
native writer probe check is skipped unless the official stock and a host C
compiler are available, mirroring test_native_film_writer.
"""
import hashlib
import struct
import unittest
from pathlib import Path

import numpy as np

from tools.native_film_curves import (
    LOOKS, build_table, axis_knots, pack_axis, eval_curve, chroma_error,
)
from tools.build_native_film_pack import build_look_firmware, look_by_key, _fit_label

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"

# Known factory curves (from test_native_film_writer) to pin the packed format.
IDENTITY_AXIS = [0, 0, 0, 0, 0x800000, 0x804040, 0x808080, 0x80C0C0] + [0xFFFF] * 9
FILM_AXIS = [0, 0x2800, 0x2800, 0x2800, 0x442800, 0x6C4A40, 0x6C8080, 0x43B6C0] + [0xD7FF] * 9


class CurveFormatTests(unittest.TestCase):
    def test_packed_format_matches_factory_identity_and_rc2(self):
        x = bytes([0] * 4 + [64, 128, 192] + [255] * 9)
        identity = x + x + bytes([0] * 4 + [128] * 4 + [0] * 9)
        film_y = bytes([40] * 4 + [74, 128, 182] + [215] * 9)
        film = x + film_y + bytes([0] * 4 + [68, 108, 108, 67] + [0] * 9)
        self.assertEqual(pack_axis(identity), IDENTITY_AXIS)
        self.assertEqual(pack_axis(film), FILM_AXIS)

    def test_identity_look_preserves_chroma(self):
        # scale 1, no shift -> identity curve, every chroma value unchanged.
        t = build_table(axis_knots(1.0, 0))
        vals = np.arange(256)
        out = eval_curve(t, vals)
        self.assertTrue(np.array_equal(out, vals))

    def test_bw_look_flattens_chroma_to_neutral(self):
        t = build_table(axis_knots(0.0, 0))
        out = eval_curve(t, np.arange(256))
        self.assertTrue(np.all(out == 128))

    def test_neutral_knot_pinned_to_shift(self):
        for look in LOOKS:
            knots = axis_knots(look.scale, look.cb_shift)
            self.assertEqual(knots[2], max(0, min(255, 128 + look.cb_shift)))

    def test_chroma_error_bounded(self):
        # Mild looks and B&W are near-exact; strong saturation stays bounded.
        for look in LOOKS:
            e = chroma_error(look)
            self.assertLessEqual(max(e["cb_max"], e["cr_max"]), 16.0)

    def test_tables_are_49_bytes_and_words_17(self):
        for look in LOOKS:
            cb = build_table(axis_knots(look.scale, look.cb_shift))
            self.assertEqual(len(cb), 49)
            self.assertEqual(len(pack_axis(cb)), 17)


class LabelTests(unittest.TestCase):
    def test_label_padded_to_factory_width(self):
        self.assertEqual(len(_fit_label("柯达金200")), 6)
        self.assertEqual(len(_fit_label("经典铬")), 6)
        self.assertEqual(_fit_label("经典铬"), "经典铬\u3000\u3000\u3000")

    def test_overlong_label_rejected(self):
        with self.assertRaises(ValueError):
            _fit_label("超过六个字的名")


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class PackBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()

    def test_each_look_builds_same_size_and_unique_hash(self):
        hashes = {}
        for look in LOOKS:
            fw = build_look_firmware(self.stock, look, label_zh=look.key[:6])
            self.assertEqual(len(fw), 44_826_624)
            hashes[look.key] = hashlib.sha256(fw).hexdigest()
        self.assertEqual(len(set(hashes.values())), len(LOOKS))

    def test_build_is_reproducible(self):
        look = look_by_key("gold200")
        a = build_look_firmware(self.stock, look, label_zh="柯达金200")
        b = build_look_firmware(self.stock, look, label_zh="柯达金200")
        self.assertEqual(a, b)

    def test_rc2_still_reproducible(self):
        from tools.build_native_film import build_film, CANDIDATE_SHA256
        fw = build_film(self.stock, revision=2)
        self.assertEqual(hashlib.sha256(fw).hexdigest(), CANDIDATE_SHA256[2])


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class TrioBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()

    def test_trio_builds_same_size_and_reproducible(self):
        from tools.build_native_film_trio import build_trio_firmware
        looks = {"I": "gold200", "II": "moriyama_bw", "III": "velvia50"}
        a = build_trio_firmware(self.stock, looks)
        b = build_trio_firmware(self.stock, looks)
        self.assertEqual(len(a), 44_826_624)
        self.assertEqual(a, b)

    def test_trio_differs_from_single_and_stock(self):
        from tools.build_native_film_trio import build_trio_firmware
        from tools.build_native_film_pack import build_look_firmware, look_by_key
        trio = build_trio_firmware(self.stock, {"I": "gold200", "II": "moriyama_bw", "III": "velvia50"})
        single = build_look_firmware(self.stock, look_by_key("gold200"), label_zh="柯达金200")
        self.assertNotEqual(trio, single)
        self.assertNotEqual(trio, self.stock)

    def test_trio_partial_slots(self):
        from tools.build_native_film_trio import build_trio_firmware
        # Only slot II assigned; I and III stay stock.
        fw = build_trio_firmware(self.stock, {"I": None, "II": "ektar100", "III": None})
        self.assertEqual(len(fw), 44_826_624)


if __name__ == "__main__":
    unittest.main()
