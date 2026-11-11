from pathlib import Path
import struct
import tempfile
import unittest

from tools.cave_entry import build_payload, validate_cave_entry

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'


@unittest.skipUnless(MAIN.exists() and (ROOT / 'toolchains/mn103/bin/mn10300-elf-gcc').exists(),
                     'requires exact local E-P5 baseline and MN103 compiler')
class CaveEntryTests(unittest.TestCase):
    def test_linked_cave_module_is_disabled_bounded_and_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'payload'
            report = build_payload(MAIN, out)
            binary = (out / 'film.bin').read_bytes()
            self.assertLessEqual(len(binary), 32752)
            self.assertFalse(report['installable'])
            self.assertEqual(report['entry'], '0x7e128010')
            self.assertTrue(report['plain_mn103_instruction_set'])
            self.assertEqual(report['patch']['old'], 'cd b3 6f f0 10')
            self.assertEqual(struct.unpack_from('<6I', binary, report['control_offset']),
                             (0x43355045, 0, 0, 0, 0, 0))
            self.assertEqual(report['lut_bytes'], 29478)
            before = binary
            with self.assertRaises(FileExistsError):
                build_payload(MAIN, out)
            self.assertEqual((out / 'film.bin').read_bytes(), before)

    def test_modified_image_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'modified.bin'
            data = bytearray(MAIN.read_bytes())
            data[0x26ff0] = 0
            source.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                build_payload(source, directory / 'output')
            self.assertFalse((directory / 'output').exists())

    def test_native_art_caller_executes_cave_colour_code_then_original_codec_frame(self):
        report = validate_cave_entry(MAIN)
        self.assertFalse(report['physical_camera_test'])
        self.assertFalse(report['installable'])
        cases = {x['name']: x for x in report['cases']}
        self.assertTrue({'disabled', 'identity', 'warm', 'half', 'capacity', 'encoding', 'amount',
                         'mapping', 'geometry', 'resize', 'map_wrap', 'request_overlap', 'code_overlap'}.issubset(cases))
        self.assertTrue(cases['warm']['pixels_changed'])
        self.assertFalse(cases['disabled']['pixels_changed'])
        for name, case in cases.items():
            self.assertTrue(case['matches_host'], name)
            self.assertTrue(case['native_arguments_preserved'], name)
            self.assertTrue(case['registers_and_stack_preserved'], name)
            self.assertEqual(case['codec_calls'], 1, name)
            self.assertEqual(case['native_result'], 0x1234, name)
            if name not in ('warm', 'half'):
                self.assertFalse(case['pixels_changed'], name)


if __name__ == '__main__':
    unittest.main()
