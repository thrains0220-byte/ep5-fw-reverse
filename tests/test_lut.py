import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from tools.compile_lut import compile_cube, warm_negative

ROOT = Path(__file__).resolve().parents[1]
COUNT = 17 ** 3 * 3


def cube_text(transform=lambda r, g, b: (r, g, b)):
    lines = ["TITLE \"test\"", "LUT_3D_SIZE 17"]
    for b in range(17):
        for g in range(17):
            for r in range(17):
                lines.append(" ".join(str(v) for v in transform(r / 16, g / 16, b / 16)))
    return "\n".join(lines)


class CubeTests(unittest.TestCase):
    def test_axis_order_and_little_endian_endpoints(self):
        raw = compile_cube(cube_text())
        self.assertEqual(len(raw), COUNT * 2)
        self.assertEqual(raw[:6], b"\0" * 6)
        self.assertEqual(raw[-6:], b"\xff" * 6)
        self.assertEqual(int.from_bytes(raw[6:8], "little"), 4096)

    def test_bad_or_incomplete_luts_are_rejected(self):
        valid = cube_text()
        bad = [valid.replace("LUT_3D_SIZE 17", "LUT_3D_SIZE 33"),
               valid.rsplit("\n", 1)[0], valid + "\n0 0 0",
               valid.replace("0.0 0.0 0.0", "nan 0 0", 1),
               valid.replace("0.0 0.0 0.0", "-0.1 0 0", 1),
               valid.replace("LUT_3D_SIZE 17", "DOMAIN_MAX 2 2 2\nLUT_3D_SIZE 17"),
               valid.replace("LUT_3D_SIZE 17", "LUT_3D_SIZE 17\nLUT_3D_SIZE 17")]
        for text in bad:
            with self.subTest(header=text[:50]):
                with self.assertRaises(ValueError):
                    compile_cube(text)

    def test_experimental_look_is_bounded_and_changes_colour(self):
        raw = warm_negative()
        self.assertEqual(len(raw), COUNT * 2)
        self.assertNotEqual(raw, compile_cube(cube_text()))


class KernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        lib = Path(cls.directory.name) / "lut.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", str(ROOT / "firmware/lut.c"), "-o", str(lib)], check=True)
        cls.function = ctypes.CDLL(str(lib)).ep5_lut_rgb8
        cls.function.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
                                 ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t,
                                 ctypes.POINTER(ctypes.c_uint16), ctypes.c_size_t]
        cls.function.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def apply(self, pixels, width, height=1, stride=None, lut=None, capacity=None):
        image = (ctypes.c_uint8 * len(pixels))(*pixels)
        raw = compile_cube(cube_text()) if lut is None else lut
        table = (ctypes.c_uint16 * (len(raw) // 2)).from_buffer_copy(raw)
        result = self.function(image, len(pixels) if capacity is None else capacity,
                               width, height, width * 3 if stride is None else stride,
                               table, len(table))
        return result, bytes(image)

    def test_identity_preserves_all_codes_and_independent_channels(self):
        pixels = bytes(v for i in range(256) for v in (i, 255 - i, (i * 73) % 256))
        result, output = self.apply(pixels, 256)
        self.assertEqual(result, 0)
        self.assertEqual(output, pixels)

    def test_interpolation_and_endpoints(self):
        raw = compile_cube(cube_text(lambda r, g, b: (b, 1 - r, g)))
        result, output = self.apply(bytes([64, 128, 192, 0, 255, 0, 255, 0, 255]), 3, lut=raw)
        self.assertEqual(result, 0)
        self.assertEqual(output, bytes([192, 191, 128, 0, 255, 255, 255, 0, 0]))

    def test_cross_channel_interpolation(self):
        raw = compile_cube(cube_text(lambda r, g, b: (r * g, g * b, r * b)))
        result, output = self.apply(bytes([64, 128, 192]), 1, lut=raw)
        self.assertEqual(result, 0)
        for got, expected in zip(output, (64 * 128 / 255, 128 * 192 / 255, 64 * 192 / 255)):
            self.assertLessEqual(abs(got - expected), 1)

    def test_full_resolution_identity_and_experimental_look(self):
        width, height = 4608, 3456
        pixels = bytearray(bytes(range(256)) * (width * height * 3 // 256))
        original_hash = hashlib.sha256(pixels).hexdigest()
        image = (ctypes.c_uint8 * len(pixels)).from_buffer(pixels)
        timings = {}
        for name, raw in [("identity", compile_cube(cube_text())), ("warm_negative", warm_negative())]:
            table = (ctypes.c_uint16 * COUNT).from_buffer_copy(raw)
            start = time.perf_counter()
            self.assertEqual(self.function(image, len(pixels), width, height, width * 3,
                                            table, COUNT), 0)
            timings[name] = time.perf_counter() - start
            digest = hashlib.sha256(pixels).hexdigest()
            if name == "identity":
                self.assertEqual(digest, original_hash)
            else:
                self.assertNotEqual(digest, original_hash)
        report = {"width": width, "height": height, "bytes": len(pixels),
                  "lut_bytes": COUNT * 2, "kernel_dynamic_allocations": 0,
                  "identity_sha256": original_hash, "warm_negative_sha256": digest,
                  "host_seconds": timings, "camera_tested": False,
                  "input": "synthetic RGB8 pattern; no ORF or camera colour-space calibration"}
        path = ROOT / "generated/full-resolution.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")

    def test_row_padding_untouched_and_capacity_exact(self):
        pixels = bytes([1, 2, 3, 99, 98, 4, 5, 6])
        self.assertEqual(self.apply(pixels, 1, height=2, stride=5), (0, pixels))

    def test_invalid_extents_and_lut_do_not_mutate_image(self):
        pixels = bytes(range(12))
        for kwargs in [dict(width=0), dict(width=1, height=0),
                       dict(width=4, capacity=11), dict(width=4, stride=11),
                       dict(width=0xFFFFFFFF), dict(width=1, height=0xFFFFFFFF, stride=2**63),
                       dict(width=1, lut=b"\0" * 10)]:
            with self.subTest(kwargs=kwargs):
                result, output = self.apply(pixels, **kwargs)
                self.assertNotEqual(result, 0)
                self.assertEqual(output, pixels)


if __name__ == "__main__":
    unittest.main()
