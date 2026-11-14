"""Tests for the Caduceus recipe -> E-P5 chroma pair converter.

These verify the data-reuse pipeline is correct and safe:
  * sector geometry is anchored on real BT.601 hues (not uniform guesses)
  * per-sector gains come from the measured PEN-F fixture
  * neutral (gray) stays neutral: knot at 128 == 128 on both axes
  * the 49-byte packed table evaluates identically to the fitted knots
  * a known vivid recipe (Velvia) actually increases chroma gain
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from caduceus_to_ep5 import (  # noqa: E402
    sector_centres, load_gains, load_recipe, fit_recipe, SECTORS, KNOT_X,
)
from native_film_curves_hq import build_hq_table  # noqa: E402


def eval_table(table, xs):
    x = np.frombuffer(table[0:16], dtype=np.uint8).astype(float)
    y = np.frombuffer(table[16:32], dtype=np.uint8).astype(float)
    _, idx = np.unique(x, return_index=True)
    return np.interp(xs, x[idx], y[idx])


class TestCaduceusConverter(unittest.TestCase):
    def test_sector_centres_match_primary_hues(self):
        centres, hues, _ = sector_centres()
        # pinned anchors must land exactly on their measured BT.601 hue
        for name in ("yellow", "red", "magenta", "blue", "cyan", "green"):
            i = SECTORS.index(name)
            d = (centres[i] - hues[name] + 180) % 360 - 180
            self.assertAlmostEqual(d, 0.0, places=4, msg=name)
        self.assertEqual(len(centres), 12)

    def test_gains_are_measured_values(self):
        pos, neg = load_gains()
        # yellow +5 -> 225, -5 -> 360 (from the PEN-F fixture)
        self.assertEqual(pos[0], 225)
        self.assertEqual(neg[0], 360)
        # yellow-green has the largest positive gain (399)
        self.assertEqual(pos[11], 399)
        self.assertTrue((pos > 0).all() and (neg > 0).all())

    def test_neutral_knot_preserved(self):
        for rkey in ("lib2_velvia", "lib2_portra", "lib2_gold", "lib2_cl_chrome"):
            recipe, _ = load_recipe(rkey)
            cb_pts, cr_pts, _ = fit_recipe(recipe, grid_side=17)
            cb_map = dict(cb_pts); cr_map = dict(cr_pts)
            self.assertEqual(cb_map[128], 128, rkey)
            self.assertEqual(cr_map[128], 128, rkey)

    def test_packed_table_roundtrip(self):
        recipe, _ = load_recipe("lib2_velvia")
        cb_pts, cr_pts, _ = fit_recipe(recipe, grid_side=17)
        xs = np.linspace(0, 255, 256)
        for pts in (cb_pts, cr_pts):
            table = build_hq_table(pts)
            self.assertEqual(len(table), 49)
            packed = eval_table(table, xs)
            ideal = np.interp(xs, KNOT_X, [y for _, y in pts])
            self.assertLessEqual(float(np.abs(packed - ideal).max()), 1.0)

    def test_velvia_boosts_chroma(self):
        recipe, _ = load_recipe("lib2_velvia")
        cb_pts, cr_pts, _ = fit_recipe(recipe, grid_side=17)
        # at +64 chroma deviation the output gain must exceed 1.1x
        cb_hi = dict(cb_pts)[192]
        cr_hi = dict(cr_pts)[192]
        self.assertGreater((cb_hi - 128) / 64.0, 1.1)
        self.assertGreater((cr_hi - 128) / 64.0, 1.1)

    def test_portra_reduces_chroma(self):
        recipe, _ = load_recipe("lib2_portra")
        cb_pts, cr_pts, _ = fit_recipe(recipe, grid_side=17)
        cb_hi = dict(cb_pts)[192]
        cr_hi = dict(cr_pts)[192]
        self.assertLess((cb_hi - 128) / 64.0, 1.0)
        self.assertLess((cr_hi - 128) / 64.0, 1.0)


if __name__ == "__main__":
    unittest.main()
