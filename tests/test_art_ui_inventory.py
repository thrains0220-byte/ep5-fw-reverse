import unittest
from pathlib import Path

from tools.inspect_art_ui import inventory


IMAGE = Path(__file__).resolve().parents[1] / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "official decoded E-P5 MAIN not available")
class ArtUIInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE.read_bytes()

    def test_expected_static_pointer_candidates(self):
        leads = inventory(self.image)["leads"]
        self.assertEqual(leads["jog"]["entry_u32_references"], ["0x7edbfd7c"])
        self.assertEqual(leads["control_ring"]["entry_u32_references"], ["0x7edbfd80"])
        self.assertEqual(leads["exit"]["entry_u32_references"], ["0x7edc0268"])

    def test_rejects_modified_input(self):
        changed = bytearray(self.image)
        changed[0] ^= 1
        with self.assertRaises(ValueError):
            inventory(changed)


if __name__ == "__main__":
    unittest.main()
