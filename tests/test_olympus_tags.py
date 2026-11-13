import struct
import unittest

from tools.olympus_tags import parse_camera_settings


def example(art=5, pic=2):
    def entry(tag, typ, n, value):
        return struct.pack("<HHII", tag, typ, n, value)
    return (b"OLYMPUS\0II\x03\0" + struct.pack("<H", 1)
            + entry(0x2020, 13, 1, 30) + bytes(4)
            + struct.pack("<H", 2) + entry(0x520, 3, 2, pic | 2 << 16)
            + entry(0x529, 3, 4, 60) + bytes(4) + struct.pack("<4H", art, 2304, 0, 0))


class OlympusTagsTests(unittest.TestCase):
    def test_ep5_modes_only_label_first_value_preserve_other_words(self):
        for art, label in ((0, "Off"), (5, "Pin Hole I"), (17, "Pin Hole II"), (18, "Pin Hole III"), (391, None)):
            r = parse_camera_settings(example(art))
            self.assertEqual(r["picture_mode"], {"raw": [2, 2], "label": "Natural"})
            self.assertEqual(r["art_filter"], {"raw": [art, 2304, 0, 0], "label": label})
        self.assertIsNone(parse_camera_settings(example(pic=231))["picture_mode"]["label"])

    def test_missing_and_unsupported_are_different_from_off(self):
        for note in [None, b"", b"OLYMP\0", b"OLYMPUS\0II\x08\x00", b"Nikon"]:
            self.assertEqual(parse_camera_settings(note), {"status": "unsupported"})
        r = parse_camera_settings(example()[:12] + bytes(6))
        self.assertEqual(r, dict(status="parsed", picture_mode=None, art_filter=None))

    def test_corrupt_fields_cannot_be_interpreted_as_evidence(self):
        for pos, fmt, value in [
            (12, "H", 0xffff), (16, "H", 4), (18, "I", 2),
            (22, "I", 12), (22, "I", 0xfffffff0),
            (34, "H", 8), (36, "I", 3), (44, "H", 0x520),
            (46, "H", 1), (48, "I", 2), (52, "I", 4), (52, "I", 67)]:
            with self.subTest(pos=pos, value=value):
                note = bytearray(example())
                struct.pack_into("<" + fmt, note, pos, value)
                with self.assertRaises(ValueError):
                    parse_camera_settings(bytes(note))
        for n in [12, 13, 24, 29, 40, 59, 64, 67]:
            with self.subTest(n=n), self.assertRaises(ValueError):
                parse_camera_settings(example()[:n])
