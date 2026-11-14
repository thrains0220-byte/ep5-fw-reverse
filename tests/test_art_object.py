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


if __name__ == '__main__':
    unittest.main()
