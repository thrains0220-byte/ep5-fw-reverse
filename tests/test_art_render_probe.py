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
    @classmethod
    def setUpClass(cls):
        cls.report = run_probe()

    def test_page_assembly_and_resource_rows(self):
        result = self.report
        self.assertEqual(result['result']['cases'], 19)
        self.assertTrue(result['result']['resource_rows_and_paging_verified'])
        self.assertEqual(result['result']['updates_per_case'], 3)
        self.assertTrue(result['result']['stack_and_callee_saved_preserved'])
        self.assertTrue(result['result']['modeled_services'])
        self.assertFalse(result['physical_camera_test'])

    def test_stock_gui_copies_page_payloads_before_notifying(self):
        result = self.report['result']
        self.assertTrue(result.get('stock_gui_transfer_executed'))
        self.assertTrue(result['copied_payloads_verified'])
        self.assertTrue(result['stock_listener_bits_verified'])
        self.assertTrue(result['lock_copy_notify_order_verified'])
        self.assertTrue(result['stock_notification_queue_verified'])
        self.assertTrue(result['stock_notification_dispatch_verified'])
        self.assertTrue(result['stock_observer_snapshot_verified'])
        self.assertTrue(result['stock_base_refresh_verified'])
        self.assertTrue(result['stock_observer_lifecycle_verified'])
        self.assertEqual(result['refresh_cases'], ['children_and_view', 'empty_children'])
        self.assertEqual(result['notification_code'], 0x1900)

    def test_service_rejects_invalid_requests_and_bounds_copy(self):
        self.assertIn('service_contract_cases', self.report['result'])
        self.assertEqual(self.report['result']['service_contract_cases'], [
            'exact', 'oversized', 'short', 'zero_length', 'null_payload',
            'invalid_id', 'lock_failure', 'no_manager', 'no_notify',
        ])

    def test_stock_read_copies_existing_payload_and_preserves_tail(self):
        self.assertIn('read_contract_cases', self.report['result'])
        self.assertEqual(self.report['result']['read_contract_cases'], [
            'exact', 'oversized', 'short', 'zero_length', 'null_payload',
            'invalid_id', 'lock_failure', 'no_manager',
        ])
