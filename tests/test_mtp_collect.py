import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import mtp_collect as mtp


class FakeCamera:
    def __init__(self, data=b"\xff\xd8\xff" + b"data" * 10):
        self.data = data
        self.row = dict(id="o76", parent="o2", type=mtp.IMAGE, filename="PA310067.JPG", size=len(data))
        self.opened = 0

    def object(self, oid):
        return dict(self.row, id=oid)

    def stream(self, oid):
        self.opened += 1
        fp = io.BytesIO(self.data)
        return lambda n: fp.read(min(n, 3)), 8


class MTPTests(unittest.TestCase):
    def setUp(self):
        # Use the same filesystem as sessions/ (a Windows AppContainer's
        # virtual %TEMP% can prohibit rename even for files it created).
        self.tmp = tempfile.TemporaryDirectory(dir=mtp.ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cam = FakeCamera()

    def transfer(self):
        result = []
        mtp.pull(self.cam, ["o76:PA310067.JPG"], self.root, result)
        return result[0]

    def test_requires_single_exact_usb_and_model_without_exposing_pnp_serial(self):
        pnp = r"\\?\usb#vid_07b4&pid_012f#private-serial#{guid}"
        self.assertEqual(mtp.only_device([pnp]), pnp)
        for ids in [[], [pnp, pnp], [pnp.replace("012f", "012f0")], [pnp.replace("usb#", "other#")]]:
            with self.assertRaises(ValueError) as e:
                mtp.only_device(ids)
            self.assertNotIn("private-serial", str(e.exception))
        mtp.check_model({"model": "E-P5"})
        for model in ["E-P5 II", "E-P7", None]:
            with self.assertRaises(ValueError):
                mtp.check_model({"model": model})

    def test_session_is_new_child_of_local_sessions(self):
        with patch.object(mtp, "ROOT", self.root):
            for name in ["../escape", r"C:\camera", "NUL", "con", "foo:bar", "foo.", "a/b"]:
                with self.assertRaises(ValueError):
                    mtp.new_session(name)
            dest = mtp.new_session("test-01")
            self.assertEqual(dest, self.root / "sessions" / "test-01")
            with self.assertRaises(FileExistsError):
                mtp.new_session("test-01")

    def test_reparse_sessions_root_is_not_accepted(self):
        with patch.object(mtp, "ROOT", self.root), patch.object(Path, "lstat") as info:
            info.return_value.st_file_attributes = 1024
            with self.assertRaisesRegex(ValueError, "junction"):
                mtp.new_session("test-bad")

    def test_partial_reads_reassembled_and_hashed(self):
        result = self.transfer()
        self.assertEqual(result["sha256"], hashlib.sha256(self.cam.data).hexdigest())
        self.assertEqual((self.root / result["path"]).read_bytes(), self.cam.data)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_refuse_unsafe_camera_filename_and_oversize_before_getstream(self):
        for bad in ["../A.JPG", "A.BIN", "NUL.JPG", "Con.ORF", "x:ads.JPG", "abc.JPG."]:
            with self.subTest(bad=bad):
                self.cam.row["filename"] = bad
                with self.assertRaises(ValueError):
                    self.transfer()
        self.cam.row.update(filename="A.ORF", size=mtp.MAX_FILE + 1)
        with self.assertRaisesRegex(ValueError, "64 MiB"):
            self.transfer()
        self.assertEqual(self.cam.opened, 0)

    def test_stream_mismatch_or_failure_removes_unfinished_files(self):
        for data in [self.cam.data[:-1], self.cam.data+b"!", b"not a JPEG".ljust(self.cam.row["size"], b" ")]:
            self.cam.data = data
            with self.assertRaises(ValueError):
                self.transfer()
            self.assertFalse(list(self.root.iterdir()))
        def disconnected(n):
            raise OSError("disconnected")
        with patch.object(self.cam, "stream", return_value=(disconnected, 4096)):
            with self.assertRaises(OSError):
                self.transfer()
            self.assertFalse(list(self.root.iterdir()))

    def test_changed_metadata_duplicate_names_and_existing_output_refused(self):
        with patch.object(self.cam, "object", side_effect=[dict(self.cam.row), dict(self.cam.row, parent="o9")]):
            with self.assertRaisesRegex(ValueError, "metadata changed"):
                self.transfer()
        self.assertFalse(list(self.root.iterdir()))
        with self.assertRaisesRegex(ValueError, "different filename"):
            mtp.pull(self.cam, ["o1:PA310067.JPG", "o2:PA310068.JPG"], self.root, [])
        self.assertEqual(self.cam.opened, 1)  # only the previous metadata-drift test opened a stream
        with self.assertRaisesRegex(ValueError, "same local filename"):
            mtp.pull(self.cam, ["o1:PA310067.JPG", "o2:PA310067.JPG"], self.root, [])
        dest = self.root / self.cam.row["filename"]
        dest.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            self.transfer()
        self.assertEqual(dest.read_bytes(), b"keep")

    def test_inspect_stops_at_limit_without_reading_photo_bytes(self):
        self.cam.children = lambda parent, n: ["o1", "o2", "o3"][:n]
        report = mtp.inspect(self.cam, 2)
        self.assertTrue(report["inventory_limited"])
        self.assertEqual([r["id"] for r in report["objects"]], ["o1", "o2"])
        self.assertEqual(self.cam.opened, 0)
