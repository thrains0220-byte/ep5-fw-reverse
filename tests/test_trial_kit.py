import hashlib
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools import build_trial_kit as kit

STOCK = kit.ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"


class TrialKitTests(unittest.TestCase):
    def test_unknown_input_does_not_leave_a_partial_kit(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock, out = Path(tmp) / "other.bin", Path(tmp) / "kit"
            stock.write_bytes(b"another model")
            with self.assertRaisesRegex(ValueError, "stock SHA-256"):
                kit.build_kit(stock, out)
            self.assertFalse(out.exists())

    @unittest.skipUnless(STOCK.is_file(), "requires original E-P5 1.8 image")
    def test_each_archive_prepares_only_its_intended_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "kit"
            kit.build_kit(STOCK, out)
            self.assertEqual({p.name for p in out.iterdir()}, {kit.CANDIDATE_ZIP, kit.STOCK_ZIP})
            for name, digest in ((kit.CANDIDATE_ZIP, kit.CANDIDATE_SHA256[2]),
                                 (kit.STOCK_ZIP, kit.STOCK_SHA256)):
                with self.subTest(name=name), ZipFile(out / name) as archive:
                    card = Path(tmp) / name.removesuffix(".zip")
                    archive.extractall(card)
                    payloads = [p for p in card.rglob("*.BIN")]
                    self.assertEqual(payloads, [card / "DCOLYMP/E1089999.BIN"])
                    self.assertEqual(hashlib.sha256(payloads[0].read_bytes()).hexdigest(), digest)
                    if name == kit.STOCK_ZIP:
                        self.assertEqual(payloads[0].read_bytes(), STOCK.read_bytes())
                    self.assertEqual((card / "SHA256SUMS").read_text().split(),
                                     [digest, "DCOLYMP/E1089999.BIN"])
            with self.assertRaises(FileExistsError):
                kit.build_kit(STOCK, out)
