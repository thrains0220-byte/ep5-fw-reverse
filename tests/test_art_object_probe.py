"""Regression test for the bounded execution of stock ART navigation."""
import shutil
import unittest
from pathlib import Path

from tools.validate_art_object_probe import run_probe

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'


@unittest.skipUnless(IMAGE.exists() and shutil.which('cc') and shutil.which('git'),
                     'decoded firmware and native C toolchain required')
class ArtObjectProbeTests(unittest.TestCase):
    def test_stock_navigation_and_return_frames(self):
        report = run_probe()
        self.assertEqual(report['result']['cases'], 14)
        self.assertTrue(report['result']['nonbinary_availability_selectable'])
        self.assertEqual(report['result']['all_unavailable_forward_index'], 13)
        self.assertEqual(report['result']['all_unavailable_backward_index'], 0)
        self.assertTrue(report['result']['stack_and_callee_saved_preserved'])
        self.assertTrue(report['result']['modeled_draw_and_log'])
        self.assertFalse(report['physical_camera_test'])


if __name__ == '__main__':
    unittest.main()
