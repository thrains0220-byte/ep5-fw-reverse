import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.compile_lut import warm_negative

ROOT = Path(__file__).resolve().parents[1]
U8 = C.POINTER(C.c_uint8)
U16 = C.POINTER(C.c_uint16)


class Image(C.Structure):
    _fields_ = [("data", U8), ("capacity", C.c_size_t), ("width", C.c_uint32),
                ("height", C.c_uint32), ("stride", C.c_size_t)]


PROGRESS = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_uint32)


def identity():
    return struct.pack("<14739H", *(round(v * 65535 / 16)
                       for b in range(17) for g in range(17) for r in range(17) for v in (r, g, b)))


def table(data):
    return (C.c_uint16 * 14739).from_buffer_copy(data)


def descriptor(address=0x12340000, chroma=0, fmt=0x302, pitch=8, width=4, height=2, x=2, y=1):
    return struct.pack("<II12H", address, chroma, fmt, pitch, width, height,
                       width, height, x, y, width // 2, height // 2, 0, 0)


class FilmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        so = Path(cls.temp.name) / "film.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        str(ROOT / "firmware/lut.c"), str(ROOT / "firmware/film.c"), "-o", str(so)], check=True)
        cls.lib = C.CDLL(str(so))
        cls.lib.ep5_image_from_desc.argtypes = [C.POINTER(Image), U8, C.c_size_t,
                                                C.c_uint32, U8, C.c_size_t]
        cls.lib.ep5_image_from_desc.restype = C.c_int
        cls.lib.ep5_film_apply.argtypes = [C.POINTER(Image), U16, C.c_size_t,
                                          C.c_uint, C.c_uint, PROGRESS, C.c_void_p]
        cls.lib.ep5_film_apply.restype = C.c_int
        cls.lib.ep5_lut_sample16.argtypes = [U16, U16, U16]

    def apply(self, data, width=4, height=2, stride=12, lut=None, amount=256,
              encoding=1, capacity=None, callback=None, values=14739):
        buf = (C.c_uint8 * len(data)).from_buffer(data)
        image = Image(buf, len(data) if capacity is None else capacity, width, height, stride)
        cb = PROGRESS(callback) if callback else PROGRESS()
        return self.lib.ep5_film_apply(C.byref(image), table(identity() if lut is None else lut),
                                       values, encoding, amount, cb, None)

    def test_descriptor_crop_and_exact_mapping(self):
        data = (C.c_uint8 * 64)()
        out = Image()
        desc = (C.c_uint8 * 32).from_buffer_copy(descriptor())
        self.assertEqual(self.lib.ep5_image_from_desc(C.byref(out), desc, 32, 0x12340000, data, 64), 0)
        self.assertEqual(C.cast(out.data, C.c_void_p).value, C.addressof(data) + 20)
        self.assertEqual((out.capacity, out.width, out.height, out.stride), (44, 4, 2, 16))

    def test_descriptor_rejects_bad_fields_without_output_changes(self):
        data = (C.c_uint8 * 64)()
        cases = [dict(fmt=0x107), dict(chroma=0x12340010), dict(width=3), dict(width=0),
                 dict(x=6), dict(x=1), dict(height=0), dict(pitch=0),
                 dict(address=0x1233ffff), dict(address=0xfffffff0)]
        for changes in cases:
            out = Image(None, 99, 100, 101, 102)
            before = bytes(out)
            desc = (C.c_uint8 * 32).from_buffer_copy(descriptor(**changes))
            self.assertEqual(self.lib.ep5_image_from_desc(C.byref(out), desc, 32, 0x12340000, data, 64), -1, changes)
            self.assertEqual(bytes(out), before)
        desc = (C.c_uint8 * 32).from_buffer_copy(descriptor())
        for length, cap in ((31, 64), (32, 43)):
            out = Image()
            self.assertEqual(self.lib.ep5_image_from_desc(C.byref(out), desc, length, 0x12340000, data, cap), -1)

    def test_identity_preserves_every_chroma_pair_and_luma_codes(self):
        data = bytearray(v for cb in range(256) for cr in range(256)
                         for v in ((cb * 17 + cr) % 256, cb, (cr * 73 + cb) % 256, cr))
        before = bytes(data)
        self.assertEqual(self.apply(data, width=512, height=256, stride=1024), 0)
        self.assertEqual(data, before)

    def test_rgb16_retains_sub_byte_detail(self):
        # Constant +100/65535 red shift survives the sampler below RGB8 precision.
        lut = table(struct.pack("<14739H", *(min(65535, round(v * 65535 / 16) + (100 if c == 0 else 0))
                    for b in range(17) for g in range(17) for r in range(17) for c, v in enumerate((r, g, b)))))
        source = (C.c_uint16 * 3)(30000, 20000, 10000)
        out = (C.c_uint16 * 3)()
        self.lib.ep5_lut_sample16(lut, source, out)
        self.assertLessEqual(abs(out[0] - 30100), 1)
        self.assertLessEqual(abs(out[1] - 20000), 1)
        self.assertLessEqual(abs(out[2] - 10000), 1)

    def test_against_independent_float_colour_reference(self):
        # Constant RGB output makes the reference independent of LUT interpolation.
        target = (0.71, 0.32, 0.18)
        lut = struct.pack("<14739H", *(round(v * 65535) for _ in range(4913) for v in target))
        original = bytearray((80, 128, 170, 128, 90, 160, 150, 100))
        result = bytearray(original)
        self.assertEqual(self.apply(result, width=4, height=1, stride=8, lut=lut), 0)
        y = 0.299 * target[0] + 0.587 * target[1] + 0.114 * target[2]
        cb = 128 + 255 * (-0.168736 * target[0] - 0.331264 * target[1] + 0.5 * target[2])
        cr = 128 + 255 * (0.5 * target[0] - 0.418688 * target[1] - 0.081312 * target[2])
        for at in (0, 4):
            for got, expected in zip(result[at:at + 4], (255 * y, cb, 255 * y, cr)):
                self.assertLessEqual(abs(got - expected), 1.5)
        half = bytearray(original)
        self.assertEqual(self.apply(half, width=4, height=1, stride=8, lut=lut, amount=128), 0)
        for a, b, c in zip(original, result, half):
            self.assertLessEqual(abs(c - (a + b) / 2), 1)

    def test_zero_strength_and_invalid_requests_do_not_mutate(self):
        original = bytearray(range(24))
        data = bytearray(original)
        self.assertEqual(self.apply(data, amount=0, lut=warm_negative()), 0)
        self.assertEqual(data, original)
        for changes in (dict(width=3), dict(width=0), dict(height=0), dict(stride=7),
                        dict(capacity=19), dict(amount=257), dict(encoding=0), dict(values=1),
                        dict(width=0xffffffff), dict(height=0xffffffff, stride=0xfffffff0)):
            data = bytearray(original)
            self.assertEqual(self.apply(data, **changes), -1, changes)
            self.assertEqual(data, original)

    def test_cancellation_distinguishes_untouched_and_discard_required(self):
        data = bytearray([100, 128, 160, 128] * 20)
        original = bytes(data)
        self.assertEqual(self.apply(data, width=2, height=20, stride=4,
                                    callback=lambda ctx, done, total: 0), -2)
        self.assertEqual(data, original)
        calls = []

        def progress(ctx, done, total):
            calls.append((done, total))
            return done == 0

        self.assertEqual(self.apply(data, width=2, height=20, stride=4, lut=warm_negative(), callback=progress), -3)
        self.assertEqual(calls, [(0, 20), (16, 20)])
        self.assertNotEqual(data[:64], original[:64])
        self.assertEqual(data[64:], original[64:])

    def test_full_resolution_changes_pixels_and_preserves_row_padding(self):
        width, height, stride = 4608, 3456, 4608 * 2 + 8
        row = bytes((100, 128, 160, 128)) * (width // 2) + bytes([0xa5] * 8)
        data = bytearray(row * height)
        self.assertEqual(self.apply(data, width=width, height=height, stride=stride, lut=warm_negative()), 0)
        self.assertNotEqual(data[:4], row[:4])
        for y in range(height):
            self.assertEqual(data[y * stride + width * 2:(y + 1) * stride], bytes([0xa5] * 8))


if __name__ == "__main__":
    unittest.main()
