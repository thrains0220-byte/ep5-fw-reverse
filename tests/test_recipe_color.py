import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from ep5studio.cube import compile_rgb17, parse_cube, sample_cube
from ep5studio.filmlooks import cube_text
from ep5studio.recipe_color import RECIPES, RecipeReference


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "build/research/caduceus-color-78dbbc4"
PATCHES = np.array([[0, 0, 0], [64, 64, 64], [128, 128, 128], [192, 192, 192],
                    [194, 142, 113], [75, 101, 163], [72, 133, 72], [231, 184, 64]], dtype=np.uint8)
# Observed using the original Caduceus display renderer and RGBA8 destination.
EXPECTED = {
    "Gold": [[0, 0, 0], [72, 71, 70], [138, 136, 134], [197, 193, 191],
             [211, 145, 114], [90, 110, 158], [87, 140, 78], [255, 180, 48]],
    "Portra400": [[1, 1, 1], [85, 84, 84], [135, 135, 134], [185, 184, 183],
                  [191, 143, 116], [97, 114, 162], [99, 136, 93], [221, 176, 82]],
    "Velvia": [[0, 0, 0], [40, 40, 40], [129, 129, 129], [206, 206, 206],
               [216, 145, 106], [56, 89, 187], [51, 140, 41], [255, 196, 21]],
}


class ReferenceTests(unittest.TestCase):
    def test_modified_renderer_rejected_before_execution(self):
        with TemporaryDirectory() as tmp:
            changed = Path(tmp, "webapp/src/preview.ts")
            changed.parent.mkdir(parents=True)
            changed.write_bytes(b"throw new Error('wrong renderer')")
            with self.assertRaisesRegex(ValueError, "Reference differs"):
                RecipeReference(tmp)

    @unittest.skipUnless((REFERENCE / "sim/recipes/library_v2.json").is_file() and shutil.which("node"),
                         "fetch the pinned reference and install Node 24 to compare the independent renderer")
    def test_canvas_and_compiled_lut_match_reference_patches(self):
        reference = RecipeReference(REFERENCE)
        random = np.random.default_rng(21745).integers(0, 256, (8192, 3), dtype=np.uint8)
        for name in RECIPES:
            with self.subTest(name=name):
                np.testing.assert_array_equal(np.rint(reference.render8(name, PATCHES, canvas=True) * 255),
                                              EXPECTED[name])
                cube = parse_cube(cube_text(reference.cube(name), "test"))
                raw = compile_rgb17(cube)
                self.assertEqual(len(raw), 17**3 * 6)
                values = np.frombuffer(raw, dtype="<u2").reshape((17, 17, 17, 3)) / 65535
                compiled = type(cube)(cube.title, cube.side, values)
                for patches, bound in ((PATCHES, 3), (random, 7)):
                    err = np.abs(sample_cube(compiled, patches / 255) - reference.render8(name, patches)) * 255
                    self.assertLess(err.max(), bound)
                    if patches is random:
                        self.assertLess(err.mean(), 0.35)


if __name__ == "__main__":
    unittest.main()
