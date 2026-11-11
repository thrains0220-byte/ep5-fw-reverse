import hashlib
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
CLI = ROOT / "tools/build_native_film.py"
BASE = 0x7e101020


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class FilmRecipeTests(unittest.TestCase):
    def test_original_recipe_remains_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "rc1"
            run = subprocess.run([sys.executable, str(CLI), str(STOCK), "--revision", "1",
                                  "--out", str(folder)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            image = (folder / "DCOLYMP/E1089999.BIN").read_bytes()
            self.assertEqual(hashlib.sha256(image).hexdigest(),
                             "2f3eb6cd7d9b0c4bdd29414174e02fe850e26ed9dae482ad55a076559075243f")
            note = (folder / "READ-ME.txt").read_text(encoding="utf-8")
            self.assertIn("Soft Chrome RC1", note)
            self.assertIn("原厂名称", note)
            self.assertIn(hashlib.sha256(image).hexdigest(), note)

    def test_rc2_changes_only_filter_list_text_in_chinese_language_packs(self):
        from external.oly_fw_analysis.tools import oly_container
        from tools.build_native_film import build_film

        source = STOCK.read_bytes()
        factory = oly_container.parse(source)
        update = oly_container.parse(build_film(source))
        self.assertEqual(hashlib.sha256(update[0].payload).hexdigest(),
                         "10fac02b381f8253b039cc0fd297d2947544111cdd48deb67f67458b36f34b01")
        self.assertEqual(update[2:], factory[2:])
        original = factory[1].payload
        language = bytearray(update[1].payload)
        # Look up the strings through the factory language directory and pointer
        # tables, independently of the recipe's fixed offsets.
        for row, old, new in ((2, "针孔相机效果", "针孔/柔彩I"), (3, "針孔相機效果", "針孔/柔彩I")):
            flash, size = struct.unpack_from("<II", original, row * 16)
            start = flash - (factory[1].address + 32)
            base = 0xbff2a200
            table, end = struct.unpack_from("<II", original, start)
            self.assertEqual((end - table) // 4, 2317)
            self.assertLessEqual(end - base, size)
            for entry, prefix in ((69, ""), (602, "@A045@")):
                address, = struct.unpack_from("<I", language, start + table - base + 4 * entry)
                offset = start + address - base
                before = (prefix + old + "\0").encode("utf-16-le")
                after = (prefix + new + "\0").encode("utf-16-le")
                self.assertEqual(original[offset:offset + len(before)], before)
                self.assertEqual(language[offset:offset + len(after)], after)
                language[offset:offset + len(before)] = before
        self.assertEqual(language, original)

    def test_card_artifact_preserves_factory_record_and_movie_curve(self):
        from external.oly_fw_analysis.tools import oly_container

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "card"
            cmd = [sys.executable, str(CLI), str(STOCK), "--out", str(folder)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            target = folder / "DCOLYMP/E1089999.BIN"
            image = target.read_bytes()
            digest = hashlib.sha256(image).hexdigest()
            self.assertEqual(digest, "90a63cd0b191f0d0cfdf344b2129723af07f6969d1d6368b8e2216a2019c1229")
            self.assertEqual((folder / "SHA256SUMS").read_bytes(),
                             (digest + "  DCOLYMP/E1089999.BIN\n").encode("ascii"))
            note = (folder / "READ-ME.txt").read_text(encoding="utf-8")
            self.assertIn("Soft Chrome RC2", note)
            self.assertIn("针孔/柔彩I", note)
            self.assertIn(digest, note)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)

        stock = oly_container.parse(STOCK.read_bytes())[0].payload
        film = oly_container.parse(image)[0].payload
        for address, size in [(0x7e21d0d1, 16), (0x7e21d0e7, 16), (0x7e21d0fd, 17),
                              (0x7e21d113, 16), (0x7e21d129, 16), (0x7e21d13f, 17)]:
            refs = [struct.unpack_from("<I", b, address - BASE)[0] - BASE for b in (stock, film)]
            self.assertEqual(stock[refs[0]:refs[0]+size], film[refs[1]:refs[1]+size])
            self.assertEqual(film[address-BASE-2:address-BASE], b"\xfc\xdc")
        for data in (stock, film):
            self.assertEqual(struct.unpack_from("<I", data, 0x7e478ea0 - BASE)[0], 0x7e22a12f)
        self.assertEqual(struct.unpack_from("<I", film, 0x7e478ec4 - BASE)[0], 0x7e22a01f)

class PublicationTests(unittest.TestCase):
    def test_unreviewed_output_is_not_published_and_failure_allows_retry(self):
        from tools import build_native_film

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "card"
            stock = Path(tmp) / "source.bin"
            stock.write_bytes(b"fixture")
            argv = [str(CLI), str(stock), "--out", str(folder)]
            error = StringIO()
            candidate = b"candidate"
            with patch.object(sys, "argv", argv), patch.object(build_native_film, "build_film",
                                                               return_value=candidate):
                with redirect_stderr(error), self.assertRaises(SystemExit):
                    build_native_film.main()
                self.assertIn("published SHA-256", error.getvalue())
                self.assertFalse(folder.exists())

                with patch.dict(build_native_film.CANDIDATE_SHA256, {2: hashlib.sha256(candidate).hexdigest()}):
                    with patch.object(Path, "replace", side_effect=OSError("publish failed")):
                        with redirect_stderr(error), self.assertRaises(SystemExit):
                            build_native_film.main()
                    self.assertIn("publish failed", error.getvalue())
                    self.assertFalse(folder.exists())
                    build_native_film.main()
                    self.assertEqual((folder / "DCOLYMP/E1089999.BIN").read_bytes(), candidate)

    def test_bad_source_never_creates_a_card_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad, folder = Path(tmp) / "foreign.bin", Path(tmp) / "card"
            bad.write_bytes(b"another camera")
            run = subprocess.run([sys.executable, str(CLI), str(bad), "--out", str(folder)],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("SHA-256", run.stderr)
            self.assertFalse(folder.exists())
