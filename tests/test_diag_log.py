import struct
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from read_diag_log import decode  # noqa: E402


class TestDiagLog(unittest.TestCase):
    def test_fixed_record_decode(self):
        p = bytearray(128)
        struct.pack_into("<IIIIHHHHII", p, 0,
                         0x47414944, 7, 0x60001000, 0x12000010,
                         4608, 3456, 4608, 3456, 0x605f455c, 0x11000000)
        p[32] = 0
        p[33:49] = bytes(range(16))
        struct.pack_into("<II", p, 52, 0, 3)
        row = decode(bytes(p))[0]
        self.assertEqual(row["sequence"], 7)
        self.assertEqual(row["width"], 4608)
        self.assertEqual(row["height"], 3456)
        self.assertEqual(row["sample_hex"], bytes(range(16)).hex())
        self.assertEqual(row["flags"], 3)

    def test_rejects_bad_length_and_magic(self):
        with self.assertRaises(ValueError):
            decode(bytes(127))
        p = bytearray(128)
        with self.assertRaises(ValueError):
            decode(bytes(p))


if __name__ == "__main__":
    unittest.main()
