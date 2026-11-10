from pathlib import Path
import unittest

from tools.image_probe import run_image_probe, run_art_handoff

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "requires exact stock E-P5 main")
class ImageProbeTests(unittest.TestCase):
    def test_original_art_to_jpeg_handoff_and_frames(self):
        report = run_art_handoff(IMAGE)
        self.assertFalse(report['physical_camera_test'])
        cases = report['cases']
        self.assertEqual(len(cases), 2)
        for case, geometry in zip(cases, ([4608, 3456, 4608, 3456], [640, 480, 640, 480])):
            self.assertEqual(case['geometry_u16'], geometry)
            self.assertEqual(case['buffer_address'], 0x12000000)
            self.assertEqual(case['request_words'][7], 0x20000000)
            self.assertEqual(case['request_words'][9] & 2, 2 if case['picture_mode'] else 0)
            self.assertTrue(case['registers_and_stack_preserved'])
            self.assertEqual(case['codec_calls'], 1)
            self.assertEqual(case['native_result'], 0x1234)
        self.assertIn('actual image production', report['not_tested'])

    def test_original_descriptor_reader_and_vendor_frame(self):
        report = run_image_probe(IMAGE)
        self.assertFalse(report["physical_camera_test"])
        self.assertEqual(report["entry"], "0x7e40fba4")
        self.assertEqual(report["frame"], {"register_mask": 32, "bytes": 8})
        self.assertTrue(report["registers_and_stack_preserved"])
        labels = [entry["label"] for entry in report["fields"]]
        self.assertEqual(labels[:6], ["pAddress", "pAddressC", "usDataFormat", "usMemHw", "usUseHw", "usUseVw"])
        self.assertEqual([e["offset"] for e in report["fields"]], [0, 4, *range(8, 28, 2), 28])
        self.assertEqual([e["value"] for e in report["fields"]],
                         [0x12345678, 0x87654321, *range(0x310, 0x31a), 0xabcdef01])


if __name__ == "__main__":
    unittest.main()
