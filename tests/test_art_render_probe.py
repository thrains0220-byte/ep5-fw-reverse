"""Bounded execution of the stock E-P5 ART page assembly."""
import shutil
import unittest
from pathlib import Path

from tools.validate_art_render_probe import run_probe

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'


@unittest.skipUnless(IMAGE.exists() and shutil.which('cc') and shutil.which('git'),
                     'decoded firmware and native C toolchain required')
class ArtRenderProbeTests(unittest.TestCase):
    def test_page_assembly_and_resource_rows(self):
        result = run_probe()
        self.assertEqual(result['result']['cases'], 19)
        self.assertTrue(result['result']['resource_rows_and_paging_verified'])
        self.assertEqual(result['result']['updates_per_case'], 3)
        self.assertTrue(result['result']['stack_and_callee_saved_preserved'])
        self.assertTrue(result['result']['modeled_services'])
        self.assertFalse(result['physical_camera_test'])
