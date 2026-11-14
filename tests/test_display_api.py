import unittest
from pathlib import Path

from tools.inspect_display_api import inventory


DISASM = Path(__file__).resolve().parents[1] / "build/display-full.txt"


@unittest.skipUnless(DISASM.exists(), "display disassembly not available")
class DisplayApiInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = inventory(DISASM.read_text(encoding="utf-8", errors="replace"))

    def test_expected_entries_and_anchors(self):
        functions = self.result["functions"]
        self.assertEqual(functions["update_screen"]["candidate_start"], "0x7e34deac")
        self.assertEqual(functions["layer_custom"]["anchor"], "0x7e34e5f2")
        self.assertEqual(functions["osd_palette"]["anchor"], "0x7e34efac")
        self.assertEqual(functions["image_update"]["anchor"], "0x7e34f0d3")
        self.assertEqual(functions["image_update_async"]["anchor"], "0x7e34f223")

    def test_epilogues_and_direct_calls_are_present(self):
        for function in self.result["functions"].values():
            self.assertTrue(function["end_inclusive"].startswith("0x7e34"))
            self.assertTrue(function["epilogue"].lower().find("ret") >= 0)
            self.assertTrue(function["calls"])

    def test_static_scope(self):
        self.assertFalse(self.result["camera_accessed"])
        self.assertFalse(self.result["firmware_created"])

    def test_rejects_modified_disassembly(self):
        with self.assertRaises(ValueError):
            inventory(DISASM.read_text(encoding="utf-8", errors="replace") + "\n")


if __name__ == "__main__":
    unittest.main()
