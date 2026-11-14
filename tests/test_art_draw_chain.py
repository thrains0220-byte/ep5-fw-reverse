import unittest
from pathlib import Path

from tools.inspect_art_draw_chain import inventory


IMAGE = Path(__file__).resolve().parents[1] / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "official decoded E-P5 MAIN not available")
class ArtDrawChainInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE.read_bytes()

    def test_expected_draw_anchors(self):
        anchors = inventory(self.image)["anchors"]
        self.assertEqual(anchors["art_jog"]["instruction_address"], "0x7eaf1fde")
        self.assertEqual(anchors["draw_disp_update"]["instruction_address"], "0x7e34deb5")
        self.assertEqual(anchors["draw_layer_custom"]["instruction_address"], "0x7e34e5f2")
        self.assertEqual(anchors["draw_osd_palette"]["instruction_address"], "0x7e34efac")
        self.assertEqual(anchors["draw_image_update_async"]["instruction_address"], "0x7e34f223")

    def test_scope_is_static_only(self):
        result = inventory(self.image)
        self.assertFalse(result["camera_accessed"])
        self.assertFalse(result["firmware_created"])

    def test_rejects_modified_input(self):
        changed = bytearray(self.image)
        changed[0] ^= 1
        with self.assertRaises(ValueError):
            inventory(changed)


if __name__ == "__main__":
    unittest.main()
