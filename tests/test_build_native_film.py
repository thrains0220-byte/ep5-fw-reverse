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
    def test_failed_publication_allows_retry(self):
        from tools import build_native_film

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "card"
            argv = [str(CLI), str(STOCK), "--out", str(folder)]
            error = StringIO()
            with patch.object(sys, "argv", argv), patch.object(build_native_film, "build_film",
                                                               return_value=b"candidate"):
                with patch.object(Path, "replace", side_effect=OSError("publish failed")):
                    with redirect_stderr(error), self.assertRaises(SystemExit):
                        build_native_film.main()
                self.assertIn("publish failed", error.getvalue())
                self.assertFalse(folder.exists())
                build_native_film.main()
                self.assertEqual((folder / "DCOLYMP/E1089999.BIN").read_bytes(), b"candidate")

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
            self.assertIn(digest + "  DCOLYMP/E1089999.BIN", (folder / "SHA256SUMS").read_text())
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

    def test_bad_source_never_creates_a_card_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad, folder = Path(tmp) / "foreign.bin", Path(tmp) / "card"
            bad.write_bytes(b"another camera")
            run = subprocess.run([sys.executable, str(CLI), str(bad), "--out", str(folder)],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("SHA-256", run.stderr)
            self.assertFalse(folder.exists())
