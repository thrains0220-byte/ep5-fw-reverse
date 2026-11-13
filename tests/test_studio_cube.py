import unittest

import numpy as np

from ep5studio.cube import Cube, compile_rgb17, parse_cube, sample_cube
from tools.compile_lut import compile_cube


def cube_text(n, transform):
    lines = ["LUT_3D_SIZE %d" % n]
    for b in range(n):
        for g in range(n):
            for r in range(n):
                output = transform(r/(n-1), g/(n-1), b/(n-1))
                lines.append(" ".join(str(c) for c in output))
    return "\n".join(lines)


class StudioCubeTests(unittest.TestCase):
    def test_legacy_17_binary_is_byte_identical_including_ties(self):
        source = cube_text(17,lambda r,g,b: (b*r, g, 0.5/65535))
        self.assertEqual(compile_rgb17(parse_cube(source)),compile_cube(source))

    def test_two_cube_permutation_endpoints_and_fraction(self):
        source = cube_text(2,lambda r,g,b: (b,1-r,g))
        cube = parse_cube(('\ufeffTITLE "blue # film" # note\nLUT_3D_INPUT_RANGE 0 1e0\n'
                           + source).replace("\n","\r\n").encode("utf-8"))
        self.assertEqual(cube.title, "blue # film")
        np.testing.assert_array_equal(cube.values[0,0,1], [0,0,0])
        with self.assertRaises(ValueError):
            cube.values.setflags(write=True)
        np.testing.assert_array_equal(sample_cube(cube,np.array([.25,.5,.75])), [.75,.75,.5])
        np.testing.assert_array_equal(sample_cube(cube,np.array([1.,1.,1.])), [1,0,1])

    def test_65_grid_compilation_resamples_the_interior_not_first_17_rows(self):
        # At grid node 1/2: a curved red and a cross-channel blue ramp.
        b,g,r = np.indices((65,65,65))/64.
        data = np.stack((r*r,g,b*r),axis=-1)
        table = np.frombuffer(compile_rgb17(Cube("curved",65,data)),dtype="<u2").reshape(17,17,17,3)
        np.testing.assert_array_equal(table[4,12,8],np.rint(np.array([.25,.75,.125])*65535))
        c = parse_cube("LUT_3D_SIZE 65\n"+"0 .25 1\n"*65**3)
        self.assertEqual(c.side,65)
        np.testing.assert_array_equal(c.values[-1,-1,-1],[0,.25,1])

    def test_non_aligned_grid_uses_off_grid_cross_channel_interpolation(self):
        source = parse_cube(cube_text(16,lambda r,g,b: (r*g, g*b, b*r)))
        table = np.frombuffer(compile_rgb17(source),dtype="<u2").reshape(17,17,17,3)
        np.testing.assert_allclose(table[5,7,11],np.array([77,35,55])*65535/256.,atol=.5)

    def test_invalid_domains_rows_ranges_and_shapers_rejected(self):
        valid = cube_text(2,lambda r,g,b:(r,g,b))
        for src in [
            valid.replace("SIZE 2","SIZE 1"),valid.replace("SIZE 2","SIZE 66"),valid + "\n1 0 0",
            valid.rsplit("\n",1)[0],valid+"\nDOMAIN_MIN 0 0 0",
            "LUT_1D_SIZE 2\n"+valid, "DOMAIN_MIN 0 0 0\nLUT_3D_INPUT_RANGE 0 1\n"+valid,
            "DOMAIN_MAX 1 1 2\n"+valid, "LUT_3D_INPUT_RANGE 0 1.2\n"+valid,
            "DOMAIN_MIN NaN 0 0\n"+valid,valid.replace("0.0 0.0 0.0","0 nan 1",1),
            valid.replace("0.0 0.0 0.0","0 1e999 0",1),valid.replace("0.0 0.0 0.0","-1 0 0",1),
            "LUT_3D_SIZE 2\n"+valid, 'TITLE "title" extra\n'+valid,"LUT_3D_SIZE 2\n0 1",
        ]:
            with self.subTest(src=src[:42]), self.assertRaises(ValueError):
                parse_cube(src)

    def test_bad_sample_type_range_or_shape_refused(self):
        c = parse_cube(cube_text(2,lambda r,g,b:(r,g,b)))
        for rgb in [np.zeros(2), np.ones((3,4)), np.ones((2,3),np.uint8),
                    np.full((1,3),np.inf),np.full((1,3),1.01)]:
            with self.assertRaises(ValueError):
                sample_cube(c,rgb)
