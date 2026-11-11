import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import check_trial_photos as trial


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("PIL", "simplejpeg", "rawpy")),
                     "photo inspection needs Pillow, simplejpeg and rawpy")
class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.when = "2017:02:08 14:49:09"
        from PIL import Image
        self.tags = Image.Exif()
        self.tags[271], self.tags[272] = "OLYMPUS IMAGING CORP.", "E-P5"
        self.tags[34665] = {36867: self.when, 34855: 200}

    def jpeg(self, name="P1010001.JPG", color=(160, 55, 38), size=trial.FRAME):
        from PIL import Image
        with Image.new("RGB", size, color) as im:
            im.save(self.root / name, exif=self.tags)
        return self.root / name

    def metadata_only_orf(self):
        data = bytearray(self.tags.tobytes()[6:])
        data[2:4] = b"OR" if data[:2] == b"MM" else b"RO"
        return data

    def test_truncated_full_size_and_preview_are_rejected(self):
        small = self.jpeg("small.JPG", size=(320, 240))
        with self.assertRaisesRegex(ValueError, "full-size"):
            trial.read_jpeg(small, [])
        full = self.jpeg()
        compressed = full.read_bytes()
        for damaged in (compressed[:-150], compressed[:len(compressed)//2] + b"\xff\xd9"):
            full.write_bytes(damaged)
            with self.assertRaises(ValueError):
                trial.read_jpeg(full, [])

    def test_metadata_is_not_a_raw_mosaic(self):
        raw = self.root / "P1010001.ORF"
        raw.write_bytes(self.metadata_only_orf())
        self.assertEqual(trial.orf_tags(io.BytesIO(raw.read_bytes()))["model"], "E-P5")
        import rawpy
        with self.assertRaises(rawpy.LibRawError):
            trial.read_orf(raw)
        self.tags[272] = "E-M10"
        with self.assertRaisesRegex(ValueError, "E-P5"):
            trial.orf_tags(io.BytesIO(self.metadata_only_orf()))

    def test_pair_must_exist_and_capture_times_must_match(self):
        jpg = self.jpeg()
        with self.assertRaisesRegex(ValueError, "same-stem ORF"):
            trial.check_pair(jpg, [])
        jpg.with_suffix(".orf").touch()
        with patch.object(trial, "read_orf", return_value=dict(
                file="P1010001.orf", date_time_original="2020:01:01 00:00:00")):
            with self.assertRaisesRegex(ValueError, "different capture times"):
                trial.check_pair(jpg, [])

    def test_spread_delta_and_duplicate_inputs_do_not_establish_an_effect(self):
        first = self.jpeg()
        second = self.jpeg("P1010002.JPG", color=(125, 65, 55))
        for jpg in (first, second):
            jpg.with_suffix(".ORF").touch()
        with patch.object(trial, "read_orf", side_effect=lambda p: dict(
                file=p.name, date_time_original=self.when, sha256=p.stem)):
            result = trial.inspect(first, second, [(0, 0, 100, 100)])
            self.assertLess(result["comparison"]["mean_rgb_spread_delta"][0], -40)
            self.assertEqual(result["status"], "two_original_pairs_decoded")
            self.assertEqual(result["firmware_installation"], "unverified")
            self.assertIn("requires", result["film_effect"])
            self.assertIn("white_balance_mode", result["comparison"]["missing_settings"])
            with self.assertRaisesRegex(ValueError, "duplicate input"):
                trial.inspect(first, first, [(0, 0, 1, 1)])

    @unittest.skipUnless(os.environ.get("EP5_CC0_ORF"), "set EP5_CC0_ORF to the documented CC0 fixture")
    def test_decodes_public_ep5_sensor_samples(self):
        rec = trial.read_orf(Path(os.environ["EP5_CC0_ORF"]))
        self.assertEqual(rec["sha256"], "a1345ebe8d8722e791cbd52778e73257c5ff457ee13988fd78eac61eec841c21")
        self.assertEqual([rec["visible_width"], rec["visible_height"]], [4640, 3472])
        self.assertEqual(rec["sample_range"], [252, 4094])


if __name__ == "__main__":
    unittest.main()
