import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.film_update import build_update


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
MAIN_SIZE = 0xefffc0


class FirmwareInputTests(unittest.TestCase):
    def test_rejects_unknown_stock(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_update(b"unknown firmware", [(0, b"a", b"b")])

    def test_pinned_helper_accepts_git_newlines_but_not_changed_content(self):
        from tools import film_update

        source = b"print('verified source')\n"
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "oly_container.py"
            with patch.object(film_update, "CONTAINER_TOOL", helper), patch.object(
                    film_update, "CONTAINER_SHA256", hashlib.sha256(source).hexdigest()):
                for content in (source, source.replace(b"\n", b"\r\n")):
                    helper.write_bytes(content)
                    film_update._check_helper()
                for content in (source + b" ", source.replace(b"verified", b"tampered"),
                                source.replace(b"\n", b"\r")):
                    helper.write_bytes(content)
                    with self.assertRaisesRegex(ValueError, "helper SHA-256 mismatch"):
                        film_update._check_helper()


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class FilmUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()

    def test_emits_only_declared_main_edits_and_preserves_block_framing(self):
        from external.oly_fw_analysis.tools import oly_container

        edits = [(MAIN_SIZE - 1, b"\xff", b"\x12"), (0, b"\xfa\xfc", b"\x34\x56")]
        candidate = build_update(self.stock, edits)
        self.assertEqual(len(candidate), len(self.stock))
        self.assertEqual(candidate[:32], self.stock[:32])
        self.assertEqual(candidate[0xf00000 - 32:0xf00000 - 4],
                         self.stock[0xf00000 - 32:0xf00000 - 4])
        self.assertEqual(memoryview(candidate)[0xf00000:], memoryview(self.stock)[0xf00000:])

        blocks = oly_container.parse(candidate)
        self.assertEqual([b.kind for b in blocks], [0x100, 0x101, 0x106, 0x104])
        main = bytearray(blocks[0].payload)
        self.assertEqual(main[:2], b"\x34\x56")
        self.assertEqual(main[-1:], b"\x12")
        main[:2], main[-1:] = b"\xfa\xfc", b"\xff"
        self.assertEqual(hashlib.sha256(main).hexdigest(),
                         "dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df")
        self.assertEqual(oly_container.reconstruct(blocks), candidate)

    def test_rejects_invalid_edits(self):
        for name, edits in [
            ("empty list", []),
            ("empty replacement", [(0, b"", b"")]),
            ("unchanged bytes", [(0, b"\xfa", b"\xfa")]),
            ("length change", [(0, b"\xfa", b"ab")]),
            ("wrong original", [(0, b"\x00", b"\x01")]),
            ("negative offset", [(-1, b"\xff", b"x")]),
            ("crosses block end", [(MAIN_SIZE - 1, b"\xff\xff", b"xy")]),
            ("duplicate range", [(0, b"\xfa", b"x"), (0, b"\xfa", b"y")]),
            ("overlap", [(1, b"\xfc", b"z"), (0, b"\xfa\xfc", b"xy")]),
        ]:
            with self.subTest(case=name), self.assertRaises(ValueError):
                build_update(self.stock, edits)


if __name__ == "__main__":
    unittest.main()
