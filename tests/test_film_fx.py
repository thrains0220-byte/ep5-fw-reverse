import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from test_film import Image, PROGRESS


ROOT = Path(__file__).resolve().parents[1]


class Settings(C.Structure):
    _fields_ = [("grain", C.c_uint), ("halation", C.c_uint), ("bloom", C.c_uint),
                ("seed", C.c_uint32), ("halo_tint", C.c_uint), ("clarity", C.c_uint)]


def frame(width, height, stride, luma):
    data = bytearray([0xa5]) * (stride * height)
    for y in range(height):
        for x in range(width):
            pos = y * stride + 2 * x
            data[pos:pos + 2] = (luma(x, y), 128)
    return data


class FilmFxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        module = Path(temp.name) / "film_fx.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", str(ROOT / "firmware/film_fx.c"),
                        str(ROOT / "firmware/film.c"), str(ROOT / "firmware/lut.c"),
                        "-o", str(module)], check=True)
        cls.lib = C.CDLL(str(module))
        cls.lib.ep5_film_fx_scratch_bytes.argtypes = [C.c_uint32, C.POINTER(Settings)]
        cls.lib.ep5_film_fx_scratch_bytes.restype = C.c_size_t
        cls.lib.ep5_film_fx_apply.argtypes = [
            C.POINTER(Image), C.c_uint, C.POINTER(Settings), C.c_void_p,
            C.c_size_t, PROGRESS, C.c_void_p,
        ]
        cls.lib.ep5_film_fx_apply.restype = C.c_int

    def apply(self, data, width, height, stride, settings, *,
              capacity=None, scratch_bytes=None, encoding=1, callback=None):
        pixels = (C.c_uint8 * len(data)).from_buffer(data)
        image = Image(pixels, len(data) if capacity is None else capacity, width, height, stride)
        if scratch_bytes is None:
            scratch_bytes = self.lib.ep5_film_fx_scratch_bytes(width, C.byref(settings))
        scratch = (C.c_uint8 * scratch_bytes)() if scratch_bytes else None
        cb = PROGRESS(callback) if callback else PROGRESS()
        return self.lib.ep5_film_fx_apply(C.byref(image), encoding, C.byref(settings),
                                          scratch, scratch_bytes, cb, None)

    def test_disabled_is_byte_exact(self):
        original = bytes(range(96))
        result = bytearray(original)
        self.assertEqual(self.apply(result, 8, 4, 24, Settings()), 0)
        self.assertEqual(result, original)

    def test_seeded_grain_preserves_chroma_and_extreme_luma(self):
        width, height, stride = 32, 24, 68
        source = frame(width, height, stride, lambda x, y: (0, 255, 112)[y % 3])
        results = [bytearray(source) for _ in range(3)]
        for result, seed in zip(results, (0, 0, 42)):
            settings = Settings(100, 0, 0, seed)
            self.assertEqual(self.lib.ep5_film_fx_scratch_bytes(width, C.byref(settings)), 0)
            self.assertEqual(self.apply(result, width, height, stride, settings), 0)
            self.assertEqual(result[1::2], source[1::2])
            for y in range(height):
                a = y * stride
                if y % 3 != 2:
                    self.assertEqual(result[a:a + stride], source[a:a + stride])
                else:
                    self.assertTrue(all(abs(v - 112) <= 12 for v in result[a:a + 2 * width:2]))
                    self.assertEqual(result[a + 2 * width:a + stride], b"\xa5" * 4)
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0], results[2])
        self.assertNotEqual(results[0], source)

    def test_halation_warms_pixels_near_a_highlight(self):
        width, height, stride = 28, 20, 60
        source = frame(width, height, stride, lambda x, y: 255 if 10 <= x < 18 and 5 <= y < 15 else 80)
        result = bytearray(source)
        self.assertEqual(self.apply(result, width, height, stride, Settings(0, 100, 0, 0)), 0)
        dark_pair = 10 * stride + 2 * 8
        core_pair = 10 * stride + 2 * 14
        self.assertLess(result[dark_pair + 1], 128)
        self.assertGreater(result[dark_pair + 3], 128)
        self.assertGreater(result[dark_pair + 2], 80)
        self.assertEqual(result[core_pair:core_pair + 4], source[core_pair:core_pair + 4])
        self.assertEqual(result[:4], source[:4])
        colors = [result[dark_pair:dark_pair + 4]]
        for tint in (1, 2):
            alternate = bytearray(source)
            self.assertEqual(self.apply(alternate, width, height, stride, Settings(0, 100, 0, 0, tint)), 0)
            colors.append(alternate[dark_pair:dark_pair + 4])
        warm, amber, red = colors
        self.assertLess(amber[1], warm[1])
        self.assertLess(warm[1], red[1])
        self.assertLess(amber[3], warm[3])
        self.assertLess(warm[3], red[3])

    def test_bloom_spreads_from_original_luma_and_preserves_chroma(self):
        width, height, stride = 14, 19, 32
        rand = random.Random(17)
        source = frame(width, height, stride, lambda x, y: rand.randrange(256))
        result = bytearray(source)
        self.assertEqual(self.apply(result, width, height, stride, Settings(0, 0, 100, 0)), 0)
        weights = (1, 2, 3, 4, 5, 4, 3, 2, 1)
        horizontal = {}
        for y in range(height):
            for x in range(width):
                total = sum(w * max(0, source[y * stride + 2 * min(width - 1, max(0, x + k - 4))] - 192) * 4
                            for k, w in enumerate(weights))
                horizontal[x, y] = (total + 12) // 25
        for y in range(height):
            for x in range(width):
                total = sum(w * horizontal[x, min(height - 1, max(0, y + k - 4))]
                            for k, w in enumerate(weights))
                field, pos = (total + 12) // 25, y * stride + 2 * x
                expected = source[pos] + (field * (255 - source[pos]) + 382) // 765
                self.assertLessEqual(abs(result[pos] - expected), 1, (x, y))
                self.assertEqual(result[pos + 1], 128)
            self.assertEqual(result[y * stride + 2 * width:(y + 1) * stride], b"\xa5" * 4)
        self.assertNotEqual(result, source)

    def test_single_row_or_single_pair_respects_edges_and_padding(self):
        for width, height in ((2, 1), (2, 11), (12, 1)):
            with self.subTest(width=width, height=height):
                stride = 2 * width + 6
                source = frame(width, height, stride, lambda x, y: 255 if (x, y) == (0, 0) else 80)
                result = bytearray(source)
                settings = Settings(0, 100, 100, 0)
                self.assertEqual(self.apply(result, width, height, stride, settings,
                                            capacity=(height - 1) * stride + 2 * width), 0)
                self.assertEqual(result[0], 255)
                self.assertGreater(result[2], 80)
                for y in range(height):
                    self.assertEqual(result[y * stride + 2 * width:(y + 1) * stride], b"\xa5" * 6)

    def test_clarity_preserves_constant_regions_chroma_and_padding(self):
        width, height, stride = 384, 96, 776
        settings = Settings(clarity=32)
        self.assertEqual(self.lib.ep5_film_fx_scratch_bytes(width, C.byref(settings)), 1056)
        for level in (0, 128, 255):
            source = frame(width, height, stride, lambda x, y: level)
            result = bytearray(source)
            self.assertEqual(self.apply(result, width, height, stride, settings), 0)
            self.assertEqual(result, source)
        source = frame(width, height, stride, lambda x, y: 80 if (x < 192) == (y < 48) else 160)
        result = bytearray(source)
        self.assertEqual(self.apply(result, width, height, stride, settings), 0)
        for y, x0, x1 in ((10, 187, 196), (70, 196, 187)):
            self.assertLess(result[y * stride + 2 * x0], 80)
            self.assertGreater(result[y * stride + 2 * x1], 160)
        self.assertLess(result[43 * stride + 2 * 100], 80)
        self.assertGreater(result[52 * stride + 2 * 100], 160)
        self.assertEqual(result[1::2], source[1::2])
        for y in range(height):
            self.assertEqual(result[y * stride + 2 * width:(y + 1) * stride], b"\xa5" * 8)
        stopped = bytearray(source)
        self.assertEqual(self.apply(stopped, width, height, stride, settings,
                                    callback=lambda c, done, total: not done), -3)
        self.assertEqual(stopped[:16 * stride], result[:16 * stride])
        self.assertEqual(stopped[16 * stride:], source[16 * stride:])

    def test_invalid_requests_fail_before_writing(self):
        original = bytes(range(32))
        settings = Settings(25, 25, 25, 0)
        cases = (
            (3, 4, 8, settings, {}),
            (4, 0, 8, settings, {}),
            (4, 4, 7, settings, {}),
            (4, 4, 8, settings, {"capacity": 31}),
            (4, 4, 8, settings, {"encoding": 0}),
            (4, 4, 8, settings, {"scratch_bytes": 0}),
            (4, 4, 8, settings, {"scratch_bytes": 35}),
            (4, 4, 8, Settings(101, 0, 0, 0), {}),
            (4, 4, 8, Settings(0, 101, 0, 0), {}),
            (4, 4, 8, Settings(0, 0, 101, 0), {}),
            (4, 4, 8, Settings(0, 100, 0, 0, 3), {}),
            (4, 4, 8, Settings(clarity=101), {}),
        )
        for width, height, stride, chosen, options in cases:
            with self.subTest(width=width, height=height, stride=stride, options=options):
                result = bytearray(original)
                self.assertEqual(self.apply(result, width, height, stride, chosen, **options), -1)
                self.assertEqual(result, original)

    def test_cancel_at_entry_and_after_16_rows(self):
        width, height, stride = 8, 24, 20
        source = frame(width, height, stride, lambda x, y: 100 if x < 4 else 255)
        result = bytearray(source)
        settings = Settings(100, 100, 100, 100)
        self.assertEqual(self.apply(result, width, height, stride, settings,
                                    callback=lambda *_: 0), -2)
        self.assertEqual(result, source)
        calls = []

        def progress(ctx, done, total):
            calls.append((done, total))
            return done == 0

        self.assertEqual(self.apply(result, width, height, stride, settings, callback=progress), -3)
        self.assertEqual(calls, [(0, height), (16, height)])
        self.assertNotEqual(result[:16 * stride], source[:16 * stride])
        self.assertEqual(result[16 * stride:], source[16 * stride:])


if __name__ == "__main__":
    unittest.main()
