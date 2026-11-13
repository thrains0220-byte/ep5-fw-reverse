"""Original built-in film-genre looks: determinism, range, neutrality, distinctness."""
import unittest

import numpy as np

from ep5studio.builtins import default_cubes
from ep5studio.cube import parse_cube, compile_rgb17
from ep5studio.filmlooks import LOOK_SPECS, build_cube, cube_text, look_names


class FilmLooksTests(unittest.TestCase):
    def test_catalog_has_famous_genres_and_unique_names(self):
        names = look_names()
        self.assertEqual(len(names), len(set(names)))
        for required in ("MoriyamaHighContrastBW", "Gold200", "Portra400", "Velvia50",
                         "ClassicChrome", "Acros100", "TriX400", "CineTone", "Identity"):
            self.assertIn(required, names)

    def test_every_look_is_bounded_deterministic_and_roundtrips(self):
        for name in look_names():
            with self.subTest(name=name):
                cube, note = build_cube(name)
                again, _ = build_cube(name)
                self.assertTrue(np.array_equal(cube.values, again.values))
                self.assertTrue(np.isfinite(cube.values).all())
                self.assertGreaterEqual(cube.values.min(), 0.0)
                self.assertLessEqual(cube.values.max(), 1.0)
                text = cube_text(cube, note)
                parsed = parse_cube(text)
                self.assertEqual(parsed.title, cube.title)
                self.assertEqual(parsed.side, 17)
                self.assertTrue(np.allclose(parsed.values, cube.values, atol=1e-9))
                self.assertEqual(len(compile_rgb17(parsed)), 17**3 * 6)

    def test_identity_is_exact_and_monochrome_looks_are_neutral(self):
        identity, _ = build_cube("Identity")
        axis = np.linspace(0, 1, 17)
        for value in axis:
            idx = int(round(value * 16))
            self.assertTrue(np.allclose(identity.values[idx, idx, idx], value, atol=1e-12))
        for name in ("MoriyamaHighContrastBW", "Acros100", "TriX400"):
            cube, _ = build_cube(name)
            spread = cube.values.max(axis=-1) - cube.values.min(axis=-1)
            self.assertLess(float(spread.max()), 1e-12, name)

    def test_looks_are_visibly_distinct_on_midtone_colors(self):
        probe = np.array([[[0.7, 0.45, 0.3], [0.2, 0.5, 0.8], [0.5, 0.5, 0.5]]])
        outputs = {}
        for name in look_names():
            cube, _ = build_cube(name)
            from ep5studio.cube import sample_cube
            outputs[name] = sample_cube(cube, probe)
        names = [n for n in look_names() if n != "Identity"]
        for i, a in enumerate(names):
            for b in names[i+1:]:
                delta = float(np.abs(outputs[a] - outputs[b]).max())
                self.assertGreater(delta, 0.01, f"{a} vs {b}")

    def test_default_cubes_cover_catalog_plus_legacy_warm(self):
        files = dict(default_cubes())
        self.assertIn("WarmNegative.cube", files)
        self.assertIn("Identity.cube", files)
        for name in look_names():
            if name != "Identity":
                self.assertIn(name + ".cube", files)
        for filename, data in files.items():
            with self.subTest(filename=filename):
                parse_cube(data)


if __name__ == "__main__":
    unittest.main()
