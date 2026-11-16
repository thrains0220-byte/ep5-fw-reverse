import unittest
from pathlib import Path

from tools.inspect_art_object import extract

IMAGE = Path(__file__).resolve().parents[1] / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'


@unittest.skipUnless(IMAGE.exists(), 'official decoded E-P5 MAIN not available')
class ArtObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = IMAGE.read_bytes()

    def test_art_route_and_object(self):
        result = extract(self.data)
        self.assertEqual(result['routes']['0x91']['third'], '0x7eb1e329')
        self.assertEqual(result['art']['factory'], '0x7eb28b4b')
        self.assertEqual(result['art']['vtable_first_five'][3], '0x7eb29265')
        self.assertEqual(result['art']['event_0_handler'], '0x7eb292db')
        self.assertEqual(result['art']['list_count'], 13)
        self.assertEqual(result['art']['record_stride'], 44)
        self.assertFalse(result['physical_camera_test'])

    def test_rejects_changed_image(self):
        changed = bytearray(self.data)
        changed[0] ^= 1
        with self.assertRaises(ValueError):
            extract(changed)

    def test_art_gui_payloads_resolve_to_bounded_copy_slots(self):
        result = extract(self.data)
        self.assertIn('gui_service', result)
        gui = result['gui_service']
        self.assertEqual(gui['table_ram'], '0x602be350')
        self.assertEqual(gui['table_source'], '0x7e5a3810')
        self.assertEqual(gui['entry_count'], 168)
        self.assertEqual(gui['entry_stride'], 16)
        self.assertEqual(gui['art_slots'], [
            {'id': 0, 'read_callback': '0x0', 'update_callback': '0x0',
             'buffer': '0x606eb274', 'bytes': 12},
            {'id': 15, 'read_callback': '0x0', 'update_callback': '0x0',
             'buffer': '0x606eb452', 'bytes': 12},
            {'id': 58, 'read_callback': '0x0', 'update_callback': '0x0',
             'buffer': '0x606f1670', 'bytes': 188},
        ])


if __name__ == '__main__':
    unittest.main()
