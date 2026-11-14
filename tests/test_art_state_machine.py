import unittest
from pathlib import Path

from tools.inspect_art_state_machine import extract


IMAGE = Path(__file__).resolve().parents[1] / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "official decoded E-P5 MAIN not available")
class ArtStateMachineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = extract(IMAGE.read_bytes())

    def test_descriptor_and_matrix_dimensions(self):
        art = self.report["art"]
        self.assertEqual((art["state_columns"], art["event_rows"]), (11, 64))
        self.assertEqual(len(self.report["matrix"]), 64)
        self.assertTrue(all(len(row) == 11 for row in self.report["matrix"]))

    def test_dial_and_control_ring_callbacks(self):
        # The fifth UI state is index 4 in the zero-based matrix.
        self.assertEqual(self.report["key_events"]["0x9031"]["callback_addresses"][4], "0x7eaf1fa3")
        self.assertEqual(self.report["key_events"]["0x9032"]["callback_addresses"][4], "0x7eaf2fb3")

    def test_rejects_modified_main(self):
        data = bytearray(IMAGE.read_bytes())
        data[0] ^= 1
        with self.assertRaises(ValueError):
            extract(bytes(data))


if __name__ == "__main__":
    unittest.main()
