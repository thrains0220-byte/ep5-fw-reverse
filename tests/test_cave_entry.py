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
            self.assertEqual(report['wait_patch']['cpu_address'], '0x7e3ed850')
            self.assertEqual(report['wait_patch']['old'], 'dd 57 a7 00 00 00 14')
            self.assertEqual(binary[report['state_offset']:report['state_offset'] + 8], bytes(8))
            self.assertEqual(report['state_uncached_address'], hex(0x7e128010 + report['state_offset'] + 0x40000000))
            self.assertEqual(report['release_patch']['old'], 'cd 4b b6 00 04')
            self.assertEqual(report['param_patch']['cpu_address'], '0x7e3ed835')
            self.assertEqual(report['param_patch']['old'], 'dd 62 f2 00 00 a0 14')
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
        self.assertTrue({'completion_missing', 'receive_failure', 'short_reply', 'completion_error',
                         'wrong_token', 'wrong_packet', 'wrong_context', 'wrong_buffer', 'receive_timeout',
                         'short_reply_11', 'request_alias_overlap', 'duplicate', 'released_reuse'}.issubset(cases))
        self.assertTrue(cases['warm']['pixels_changed'])
        self.assertFalse(cases['disabled']['pixels_changed'])
        for name, case in cases.items():
            self.assertTrue(case['matches_host'], name)
            self.assertTrue(case['native_arguments_preserved'], name)
            self.assertTrue(case['registers_and_stack_preserved'], name)
            self.assertEqual(case['codec_calls'], 2 if name == 'duplicate' else 1, name)
            self.assertEqual(case['native_result'], 0x1234, name)
            self.assertTrue(case['wait_return_preserved'], name)
            self.assertTrue(case['released_and_cleared'], name)
            self.assertEqual(case['release_calls'], 2 if name == 'released_reuse' else 1, name)
            if name not in ('warm', 'half', 'duplicate'):
                self.assertFalse(case['pixels_changed'], name)
        self.assertTrue(cases['duplicate']['pixels_changed'])
        self.assertTrue(cases['duplicate']['second_image_unchanged'])
        self.assertEqual(cases['disabled']['state_writes'], 0)
        self.assertIn('uncached_code_overlap', cases)

    def test_mode_guarded_contrast_probe_preserves_original_send(self):
        from tools.cave_entry import validate_param_entry
        report = validate_param_entry(MAIN)
        self.assertFalse(report['installable'])
        self.assertFalse(report['physical_camera_test'])
        cases = {case['name']: case for case in report['cases']}
        self.assertEqual(set(cases), {'enabled', 'disabled', 'lut_mode', 'wrong_tag', 'wrong_mode',
                                      'wrong_variant', 'wrong_filter', 'wrong_packet', 'wrong_settings',
                                      'wrong_aspect', 'wrong_size_code', 'wrong_geometry',
                                      'wrong_source', 'wrong_value'})
        for name, case in cases.items():
            self.assertTrue(case['registers_and_stack_preserved'], name)
            self.assertTrue(case['original_send_called_once'], name)
            self.assertEqual(case['native_result'], 0x2345, name)
            self.assertEqual(case['mdr_at_continue'], 0x7e3ed83c, name)
            self.assertEqual(case['packet_writes'], 1 if name == 'enabled' else 0, name)
            self.assertEqual(case['contrast_after'], 1 if name == 'enabled' else case['contrast_before'], name)
            self.assertTrue(case['send_envelope_valid'], name)
            self.assertEqual(case['contrast_at_send'], case['contrast_after'], name)
            self.assertEqual(case['pre_send_geometry'], [3200, 0, 0, 0, 0, 0]
                             if name == 'wrong_geometry' else [0] * 6, name)
        self.assertEqual(report['stock_full_size_geometry_table'], [4608, 3456, 4608, 3456, 0, 0])


if __name__ == '__main__':
    unittest.main()
