import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools import mtp_collect
from tools import prepare_trial_card as prep


class CardTrialTests(unittest.TestCase):
    def setUp(self):
        # AppContainer virtual Temp cannot rename; simulate both media on local project volume.
        self.tmp = tempfile.TemporaryDirectory(dir=prep.ROOT / "build")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.card, self.host = self.root / "card", self.root / "host"
        self.fw = b"reviewed candidate"
        self.hash = hashlib.sha256(self.fw).hexdigest()
        mark = self.card / prep.MARKER
        mark.parent.mkdir(parents=True)
        mark.write_bytes(b"original photo")
        baseline = self.host / prep.BASELINE
        baseline.parent.mkdir(parents=True)
        baseline.write_text(json.dumps({"files": [{"path": mark.name, "bytes": 14,
                            "sha256": hashlib.sha256(b"original photo").hexdigest()}]}), encoding="utf-8")
        self.arc = self.host / "build/ep5-trial" / prep.CANDIDATE_ZIP
        self.arc.parent.mkdir(parents=True)
        self.zip(self.fw)
        for obj, key, val in [(prep, "ROOT", self.host), (mtp_collect, "ROOT", self.host),
                              (prep, "SIZE", len(self.fw)), (prep, "CANDIDATE_SHA256", {2: self.hash})]:
            p = patch.object(obj, key, val)
            p.start()
            self.addCleanup(p.stop)
        self.dest = self.card / prep.CARD_FILE
        self.part = self.dest.parent / prep.PART
        self.session = self.host / "sessions/result"

    def zip(self, fw):
        with ZipFile(self.arc, "w") as z:
            z.writestr(prep.CARD_FILE, fw)

    def prepare(self, kind="rc2"):
        with patch.object(prep, "drive_root", return_value=self.card), patch.object(prep, "volume", return_value="uuid"):
            return prep.prepare("E:/", "result", kind)

    def stock_zip(self, content):
        with ZipFile(self.arc.with_name(prep.STOCK_ZIP), "w") as z:
            z.writestr(prep.CARD_FILE, content)

    def test_stock_recovery_is_pinned_and_keeps_previous_candidate(self):
        self.old()
        self.dest.write_bytes(self.fw)
        stock = bytes(range(len(self.fw)))
        self.stock_zip(stock)
        expected = hashlib.sha256(stock).hexdigest()
        with patch.object(prep, "STOCK_SHA256", expected):
            self.prepare("stock")
        self.assertEqual(self.dest.read_bytes(), stock)
        self.assertEqual((self.session / prep.CARD_FILE).read_bytes(), self.fw)
        self.assertEqual(self.state()["firmware_kind"], "stock")
        self.assertEqual(self.state()["expected_firmware_sha256"], expected)
        self.assertEqual(self.state()["status"], "verified_card")
        self.assertFalse((self.dest.parent / "E1089999.STOCK.part").exists())

    def test_stock_rejects_wrong_image_before_any_card_write(self):
        self.stock_zip(self.fw)
        with self.assertRaisesRegex(ValueError, "official E-P5 1.8"):
            self.prepare("stock")
        self.assertFalse(self.dest.parent.exists())

    def test_unknown_firmware_kind_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "kind"):
            self.prepare("other")
        self.assertFalse(self.dest.parent.exists())

    def old(self):
        self.dest.parent.mkdir()
        self.dest.write_bytes(b"old update")

    def state(self):
        return json.loads((self.session / "report.json").read_text(encoding="utf-8"))

    def test_refuses_unsafe_card_arguments(self):
        for card in ["E:", "C:/", "D:/", "E:/camera", "//server/share", "//?/E:/", "."]:
            with self.subTest(card=card), self.assertRaises(ValueError):
                prep.drive_root(card)

    @unittest.skipUnless(sys.platform == "win32", "uses on-Windows WinAPI mock")
    def test_refuses_fixed_network_absent_before_volume_lookup(self):
        from unittest.mock import MagicMock
        api = MagicMock()
        with patch.object(prep.ctypes, "WinDLL", return_value=api):
            for kind in (0, 1, 3, 4, 5):
                api.GetDriveTypeW.return_value = kind
                with self.assertRaisesRegex(ValueError, "not a removable"):
                    prep.volume(Path("E:/"))
        api.GetVolumeNameForVolumeMountPointW.assert_not_called()

    def test_rejects_wrong_photo_before_any_card_write(self):
        (self.card / prep.MARKER).write_bytes(b"not that photo")
        with self.assertRaisesRegex(ValueError, "not the selected card"):
            self.prepare()
        self.assertFalse(self.dest.parent.exists())

    def test_rejects_wrong_candidate_before_any_card_write(self):
        self.zip(b"x" * len(self.fw))
        with self.assertRaisesRegex(ValueError, "reviewed RC2"):
            self.prepare()
        self.assertFalse(self.dest.parent.exists())

    def test_backs_up_and_readback_verifies_before_and_after_replacement(self):
        self.old()
        misc = self.dest.parent / "sub/notes.txt"
        misc.parent.mkdir()
        misc.write_bytes(b"notes")
        (self.dest.parent / "empty").mkdir()
        self.prepare()
        self.assertEqual((self.session / prep.CARD_FILE).read_bytes(), b"old update")
        self.assertEqual((self.session / "DCOLYMP/sub/notes.txt").read_bytes(), b"notes")
        self.assertTrue((self.session / "DCOLYMP/empty").is_dir())
        self.assertEqual(misc.read_bytes(), b"notes")
        self.assertFalse(self.part.exists())
        self.assertEqual(self.dest.read_bytes(), self.fw)
        state = self.state()
        self.assertEqual(state["status"], "verified_card")
        self.assertEqual(state["backup"]["e1089999.bin"]["sha256"], hashlib.sha256(b"old update").hexdigest())

    def test_absent_update_directory_recorded(self):
        self.prepare()
        self.assertEqual(self.dest.read_bytes(), self.fw)
        self.assertIs(self.state()["previous_folder"], False)
        self.assertFalse((self.session / "DCOLYMP").exists())

    def test_preserves_preexisting_part(self):
        self.old()
        self.part.write_bytes(b"someone else's part")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(self.part.read_bytes(), b"someone else's part")
        self.assertEqual(self.dest.read_bytes(), b"old update")

    def test_failed_staging_keeps_old_bin_and_removes_own_part(self):
        self.old()
        fsync = os.fsync
        def fail_during_stage(fd):
            if self.part.exists() and os.path.samestat(os.fstat(fd), self.part.stat()):
                raise OSError("writeback failed")
            fsync(fd)
        with patch.object(prep.os, "fsync", fail_during_stage), self.assertRaisesRegex(OSError, "writeback failed"):
            self.prepare()
        self.assertEqual(self.dest.read_bytes(), b"old update")
        self.assertFalse(self.part.exists())
        self.assertFalse(self.state()["bin_published"])

    def test_refuses_reparse_point_in_backup_tree(self):
        self.old()
        lstat = Path.lstat
        def flagged(path):
            info = lstat(path)
            if path == self.dest:
                from types import SimpleNamespace
                return SimpleNamespace(st_file_attributes=1024, st_mode=info.st_mode)
            return info
        with patch.object(Path, "lstat", flagged), self.assertRaisesRegex(ValueError, "junction"):
            self.prepare()
        self.assertEqual(self.dest.read_bytes(), b"old update")
        self.assertFalse(self.part.exists())

    def test_postpublish_corruption_is_not_reported_verified(self):
        self.old()
        digest = prep.digest
        def fail_after(path, size):
            if path == self.dest and size == len(self.fw):
                return "0" * 64
            return digest(path, size)
        with patch.object(prep, "digest", fail_after), self.assertRaisesRegex(ValueError, "do not install"):
            self.prepare()
        self.assertEqual(self.state()["status"], "published_unverified_do_not_install")
        self.assertEqual((self.session / prep.CARD_FILE).read_bytes(), b"old update")
