import unittest
from pathlib import Path

from tools.inspect_art_callbacks import inventory


IMAGE = Path(__file__).resolve().parents[1] / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


@unittest.skipUnless(IMAGE.exists(), "official decoded E-P5 MAIN not available")
class ArtCallbackInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = IMAGE.read_bytes()

    def test_enter_callbacks_share_object_and_have_distinct_event_ids(self):
        callbacks = inventory(self.image)["callbacks"]
        state5 = callbacks["art_enter_state_5"]
        state6 = callbacks["art_enter_state_6"]
        self.assertEqual(state5["object_global"], "0x602c0d1c")
        self.assertEqual(state6["object_global"], "0x602c0d1c")
        self.assertEqual(state5["event_id"], "0x91")
        self.assertEqual(state6["event_id"], "0x9d")

    def test_indirect_vtable_edges_are_not_flattened(self):
        callbacks = inventory(self.image)["callbacks"]
        for name in ("art_enter_state_5", "art_enter_state_6"):
            kinds = {edge["kind"] for edge in callbacks[name]["indirect_calls"]}
            self.assertEqual(kinds, {"object_vtable_slot_0", "object_vtable_slot_8"})

    def test_scope_is_static_and_hash_guarded(self):
        result = inventory(self.image)
        self.assertFalse(result["camera_accessed"])
        self.assertFalse(result["firmware_created"])
        changed = bytearray(self.image)
        changed[0] ^= 1
        with self.assertRaises(ValueError):
            inventory(changed)


if __name__ == "__main__":
    unittest.main()
