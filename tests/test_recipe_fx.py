import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from ep5studio.recipe_fx import HEADER, ROW, fx_sidecars, fx_sidecars_v2, strengths
from ep5studio.wire import pack_index
from ep5studio.project import Binding, Project
from test_film_fx import Settings


ROOT = Path(__file__).resolve().parents[1]
OPEN = C.CFUNCTYPE(C.c_void_p, C.c_void_p, C.c_char_p)
READ = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint32)
CLOSE = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)


class Choice(C.Structure):
    _fields_ = [("mode", C.c_uint16), ("variant", C.c_uint8),
                ("amount", C.c_uint16), ("number", C.c_uint16), ("crc", C.c_uint32)]


class LookIO(C.Structure):
    _fields_ = [("context", C.c_void_p), ("open", OPEN), ("read", READ), ("close", CLOSE)]


def sample():
    identifiers = ("a" * 64, "b" * 64)
    project = Project("Textures", (Binding("pin-hole-i", identifiers[0], "Gold", 256),
                                   Binding("pin-hole-ii", identifiers[1], "B", 128)))
    index = pack_index(project, dict(zip(identifiers, (1, 2))),
                       dict(zip(identifiers, (0xfedcba98, 0x12345678))))
    catalog = {"looks": [
        {"mode": 105, "variant": 1, "label": "Gold",
         "spatial_omitted": {"grain": "low", "effect": {"type": "bloom", "strength": 1, "tint": "amber"}}},
        {"mode": 105, "variant": 2, "label": "B"},
    ]}
    return index, catalog


def encode(body):
    return HEADER.pack(b"EP5FXP01", 1, len(body) // ROW.size, len(body), zlib.crc32(body)) + body


def result(settings):
    return settings.grain, settings.halation, settings.bloom, settings.seed, settings.halo_tint


class RecipeFxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        library = Path(temp.name) / "preset.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", str(ROOT / "firmware/film_fx_preset.c"),
                        "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.ep5_film_fx_preset.argtypes = [
            C.c_char_p, C.c_size_t, C.POINTER(Choice), C.c_uint32, C.POINTER(Settings),
        ]
        cls.lib.ep5_film_fx_preset.restype = C.c_int
        cls.lib.ep5_film_fx_preset_load.argtypes = [
            C.POINTER(LookIO), C.POINTER(Choice), C.c_uint32, C.POINTER(Settings),
        ]
        cls.lib.ep5_film_fx_preset_load.restype = C.c_int

    def read(self, data, mode=105, variant=1, amount=256, number=1, crc=0xfedcba98, *, with_clarity=False):
        choice = Choice(mode, variant, amount, number, crc)
        out = Settings(89, 90, 91, 92, 2)
        status = self.lib.ep5_film_fx_preset(data, 0 if data is None else len(data),
                                           C.byref(choice), 31, C.byref(out))
        return status, result(out) + ((out.clarity,) if with_clarity else ())

    def test_manifest_approximations_keep_tints_distinct(self):
        self.assertEqual(strengths({}), (0, 0, 0, 0))
        self.assertEqual(strengths({"grain": "high", "effect": {"type": "clarity", "strength": 3}}),
                         (75, 0, 0, 0))
        for tint, level, expected in (
            ("warm", 1, (25, 25, 0, 0)), ("amber", 1, (25, 25, 0, 1)),
            ("red", 4, (25, 50, 0, 2)), (None, 3, (25, 0, 60, 0)),
        ):
            with self.subTest(tint=tint):
                self.assertEqual(strengths({"grain": "low", "effect": {
                    "type": "bloom", "strength": level, "tint": tint}}), expected)

    def test_python_export_interoperates_with_c_and_binds_exact_table(self):
        index, catalog = sample()
        card_file = fx_sidecars(1, catalog, index)
        self.assertEqual(self.read(card_file), (1, (25, 25, 0, 31, 1)))
        self.assertEqual(self.read(card_file, amount=128), (1, (25, 25, 0, 31, 1)))
        self.assertEqual(self.read(card_file, variant=2, number=2, crc=0x12345678),
                         (1, (0, 0, 0, 31, 0)))
        disabled = (0, (0, 0, 0, 31, 0))
        self.assertEqual(self.read(None), disabled)
        self.assertEqual(self.read(card_file, crc=0x12345678), disabled)
        self.assertEqual(self.read(card_file, variant=2), disabled)
        self.assertEqual(self.read(card_file, number=2), disabled)
        self.assertEqual(self.read(card_file, mode=100), disabled)
        catalog["looks"].reverse()
        with self.assertRaises(ValueError):
            fx_sidecars(1, catalog, index)

    def test_v1_still_reads_and_v2_enables_atrophy_clarity(self):
        index, catalog = sample()
        catalog["looks"][1]["spatial_omitted"] = {
            "grain": "low", "effect": {"type": "clarity", "strength": 3},
        }
        old = fx_sidecars(1, catalog, index)
        new = fx_sidecars_v2(1, catalog, index)
        self.assertEqual(old[:8], b"EP5FXP01")
        self.assertEqual(new[:8], b"EP5FXP02")
        chosen = {"variant": 2, "number": 2, "crc": 0x12345678, "with_clarity": True}
        self.assertEqual(self.read(old, **chosen), (1, (25, 0, 0, 31, 0, 0)))
        self.assertEqual(self.read(new, **chosen), (1, (25, 0, 0, 31, 0, 32)))
        self.assertEqual(self.read(new, with_clarity=True), (1, (25, 25, 0, 31, 1, 0)))
        self.assertEqual(self.read(encode(new[HEADER.size:]), **chosen), (-1, (0, 0, 0, 31, 0, 0)))

    def test_bad_footer_overrides_an_earlier_matching_row(self):
        index, catalog = sample()
        valid = fx_sidecars(1, catalog, index)
        first = valid[HEADER.size:HEADER.size + ROW.size]
        second = valid[HEADER.size + ROW.size:]
        different_crc = second[:4] + struct.pack("<H", 1) + second[6:]
        invalid_tint = second[:-1] + b"\x03"
        invalid_strength = second[:12] + b"\x65" + second[13:]
        broken = (b"", valid[:-1], valid + b"\0", valid[:-1] + b"\x02",
                  encode(first * 2), encode(first + different_crc),
                  encode(first + invalid_tint), encode(first + invalid_strength))
        for data in broken:
            with self.subTest(data=data):
                self.assertEqual(self.read(data), (-1, (0, 0, 0, 31, 0)))

    def test_worker_closes_before_use_with_missing_bad_or_partial_reads(self):
        index, catalog = sample()
        valid = fx_sidecars(1, catalog, index)
        choice = Choice(105, 1, 256, 1, 0xfedcba98)
        for content, fail, bad_close, expected in (
            (valid, False, False, (1, (25, 25, 0, 11, 1))),
            (None, False, False, (0, (0, 0, 0, 11, 0))),
            (valid * 6, False, False, (-1, (0, 0, 0, 11, 0))),
            (valid, True, False, (-1, (0, 0, 0, 11, 0))),
            (valid, False, True, (-1, (0, 0, 0, 11, 0))),
        ):
            with self.subTest(size=len(content) if content else None, fail=fail, bad_close=bad_close):
                calls = []
                pos = 0

                def open_file(_, path):
                    calls.append(path)
                    return None if content is None else 1

                def read_file(_, file, dst, capacity):
                    nonlocal pos
                    calls.append(file)
                    if pos and fail:
                        return -1
                    chunk = content[pos:pos + min(capacity, 7)]
                    C.memmove(dst, chunk, len(chunk))
                    pos += len(chunk)
                    return len(chunk)

                def close_file(_, file):
                    calls.append("close")
                    return int(bad_close)

                io = LookIO(None, OPEN(open_file), READ(read_file), CLOSE(close_file))
                out = Settings(89, 90, 91, 92, 2)
                status = self.lib.ep5_film_fx_preset_load(C.byref(io), C.byref(choice), 11, C.byref(out))
                self.assertEqual((status, result(out)), expected)
                self.assertEqual(calls[0], b"EP5LUT/FX.EP5")
                self.assertEqual(calls.count("close"), int(content is not None))
                if content is not None:
                    self.assertEqual(calls[-1], "close")


if __name__ == "__main__":
    unittest.main()
