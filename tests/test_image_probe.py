from pathlib import Path
import unittest

from tools.image_probe import run_image_probe

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "requires exact stock E-P5 main")
class ImageProbeTests(unittest.TestCase):
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
