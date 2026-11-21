from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from tools.native_contracts import run_contracts
from tools.native_probe import build_probe

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'


@unittest.skipUnless(IMAGE.exists(), 'requires exact stock E-P5 main')
class NativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_contracts(IMAGE)

    def test_boot_requests_cover_module_without_new_loader(self):
        boot = self.report['boot']
        self.assertEqual(boot['source'], 0x402cf000)
        self.assertEqual(boot['destination'], 0xbe110000)
        self.assertEqual(boot['bytes'], 0xb1800)
        self.assertTrue(boot['covers_module'])
        self.assertFalse(self.report['physical_camera_test'])

    def test_native_allocation_and_geometry(self):
        cases = self.report['allocation']
        for name in ('allocate', 'existing', 'failed'):
            case = cases[name]
            self.assertEqual(case['geometry_u16'], [4608, 3456, 4608, 3456, 0, 0])
            self.assertEqual(case['allocation_calls'], name != 'existing')
            self.assertTrue(case['registers_and_stack_preserved'])
        self.assertEqual(cases['allocate']['allocation_bytes'], 4608 * 3456 * 2)
        self.assertEqual(cases['allocate']['buffer'], 0x12000000)
        self.assertEqual(cases['failed']['buffer'], 0)
        self.assertEqual(cases['failed']['result'], 1)
        self.assertEqual(cases['existing']['buffer'], 0x12001000)
        self.assertEqual(cases['cropped']['geometry_u16'], [4608, 3456, 4608, 3072, 0, 192])
        self.assertEqual(cases['cropped']['allocation_calls'], 1)
        self.assertEqual(cases['cropped']['allocation_bytes'], 4608 * 3456 * 2)
        self.assertEqual(cases['failed']['errors'], 1)
        for name, case in cases.items():
            self.assertEqual(case['result'], 1 if name == 'failed' else 0)
            self.assertEqual(case['codec_calls'], 0 if name == 'failed' else 1)
            if name != 'failed':
                self.assertEqual(case['jpeg_buffer'], case['buffer'])
                self.assertEqual(case['jpeg_geometry_u16'], case['geometry_u16'][:4])
                self.assertTrue(case['jpeg_frame_preserved'])

    def test_native_neutral_filter_list_retains_development(self):
        neutral = self.report['filters']['neutral']
        self.assertEqual(neutral['functions'], [0x7e40cbb1])
        self.assertEqual(neutral['initializer'], 0x7e40a20b)
        self.assertTrue(neutral['registers_and_stack_preserved'])
        stock = self.report['filters']['pinhole']
        self.assertEqual(stock['functions'], [0x7e40cbb1, 0x7e40115c])
        self.assertTrue(stock['registers_and_stack_preserved'])
        for case in self.report['filters'].values():
            self.assertEqual(case['result'], 0)
            self.assertEqual(case['initializer'], 0x7e40a20b)

    def test_art_worker_replies_only_for_terminal_effect_status(self):
        cases = self.report['art_reply']
        for name, effect, status, token in (
            ('reply-ready', 2, 0, 1),
            ('reply-ready-custom-token', 2, 0, 0x21abc735),
            ('reply-failed', 0xffff, 0x9a04, 1),
        ):
            with self.subTest(name=name):
                self.assertEqual(cases[name], dict(
                    effect_calls=1, effect_status=effect, reply_calls=1, queue=0xb3,
                    reply_u16_status=status, token=token, packet=0x605f4510, task_cleared=True))
        pending = cases['reply-pending']
        self.assertEqual((pending['effect_calls'], pending['effect_status']), (1, 1))
        self.assertEqual(pending['reply_calls'], 0)
        self.assertFalse(pending['task_cleared'])

    def test_cli_fails_when_codec_return_contract_is_corrupted(self):
        source = (ROOT / 'tools/ep5_contract_probe.c').read_text()
        marker = 'cpu->regs[REG_D0] = 0x1234;'
        self.assertEqual(source.count(marker), 1)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
            directory = Path(directory)
            injected = directory / 'corrupt_codec.c'
            injected.write_text(source.replace(marker, 'cpu->regs[REG_D0] = 0x5678;'))
            runner = build_probe(injected, directory / 'runner')
            result = subprocess.run([str(runner), str(IMAGE), 'allocate'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(json.loads(result.stdout)['jpeg_frame_preserved'])

    def test_isp_completion_updates_only_matched_work_and_propagates_failure(self):
        cases = self.report['isp_results']
        matched = cases['isp-matched']
        self.assertEqual((matched['stage_flags'], matched['result_word']), (0x3f, 0))
        unknown = cases['isp-unknown']
        self.assertEqual((unknown['stage_flags'], unknown['result_word']), (0x1f, 0x9a09))
        self.assertEqual((unknown['completion_key_after'], unknown['completion_mask_after']),
                         (0x03453607, 0x20))
        self.assertEqual((unknown['service_calls'], unknown['errors']), (0, 1))
        self.assertEqual(unknown['completion_tail_after'], [0x2d1c, *([0x4f3e2d1c] * 3)])
        self.assertEqual((unknown['pass7_calls'], unknown['record_buffer_after'], unknown['effect_after']),
                         (0, 0, 0x7e40cbb1))
        self.assertEqual((matched['pass7_calls'], matched['record_buffer_after'], matched['effect_after']),
                         (1, 0x12000000, 0))
        for name in ('isp-matched', 'isp-unknown'):
            self.assertEqual(cases[name]['reply_calls'], 0)
            self.assertFalse(cases[name]['task_cleared'])
        failed = cases['isp-failed']
        self.assertEqual(failed, dict(
            input_status=0x9a08, stage_flags=0x7fffffff, result_word=0x9a08,
            allocation_bytes=4608 * 3456 * 2, packet_buffer=0x12000000,
            completion_key_after=0, completion_index_and_padding_after=0xc3b2a100,
            completion_mask_after=0, completion_tail_after=[0] * 4,
            service_calls=1, errors=0, pass7_calls=0, pinhole_finish_calls=0, neutral_finish_calls=0,
            record_buffer_after=0, effect_after=0,
            error_handler_calls=1, error_handler_flags=0x7fffffff,
            reply_calls=1, reply_u16_status=0x9a08, reply_flags=0xffffffff,
            queue=0xb3, token=1, packet=0x605f4510, task_cleared=True,
            rec_sends=0, rec_reads=0, codec_calls=0, jpeg_buffer=0, jpeg_geometry_u16=[0] * 4))
        self.assertEqual((matched['completion_key_after'], matched['completion_mask_after'],
                          matched['service_calls'], matched['errors']), (0, 0, 1, 0))
        self.assertEqual((matched['allocation_bytes'], matched['packet_buffer']),
                         (4608 * 3456 * 2, matched['record_buffer_after']))
        self.assertEqual(matched['completion_tail_after'], [0] * 4)
        self.assertEqual(matched['completion_index_and_padding_after'], 0xc3b2a100)
        self.assertEqual(unknown['completion_index_and_padding_after'], 0xc3b2a100)

    def test_native_pinhole_finish_replies_and_retires_work_record(self):
        stock = self.report['isp_results']['isp-pinhole']
        self.assertEqual((stock['stage_flags'], stock['result_word']), (0x7ffff, 0))
        self.assertEqual((stock['pinhole_finish_calls'], stock['effect_after']), (1, 0))
        self.assertEqual((stock['reply_calls'], stock['reply_u16_status']), (1, 0))
        self.assertEqual((stock['queue'], stock['token'], stock['packet']), (0xb3, 0x21abc735, 0x605f4510))
        self.assertTrue(stock['task_cleared'])
        self.assertEqual(stock['record_buffer_after'], 0)
        self.assertEqual(stock['packet_buffer'], 0x12000000)
        self.assertEqual(stock['codec_calls'], 1)
        self.assertEqual(stock['jpeg_buffer'], stock['packet_buffer'])
        self.assertEqual(stock['jpeg_geometry_u16'], [4608, 3456, 4608, 3456])

    def test_neutral_can_finish_without_pinhole_and_rejects_missing_buffer(self):
        cases = self.report['isp_results']
        for name, status, codec_calls in (('isp-neutral-finish', 0, 1),
                                          ('isp-neutral-empty-buffer', 0x9a06, 0)):
            with self.subTest(name=name):
                case = cases[name]
                self.assertEqual((case['pass7_calls'], case['neutral_finish_calls'], case['pinhole_finish_calls']),
                                 (1, 1, 0))
                self.assertEqual((case['reply_calls'], case['reply_u16_status']), (1, status))
                self.assertEqual((case['queue'], case['token'], case['packet']), (0xb3, 1, 0x605f4510))
                self.assertEqual((case['rec_sends'], case['rec_reads']), (1, 1))
                self.assertTrue(case['task_cleared'])
                self.assertEqual(case['codec_calls'], codec_calls)
                self.assertEqual(case['jpeg_buffer'], 0x12000000 if codec_calls else 0)
                self.assertEqual(case['jpeg_geometry_u16'], [4608, 3456] * 2 if codec_calls else [0] * 4)

    def test_modified_image_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'modified.bin'
            bad.write_bytes(b'not stock')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                run_contracts(bad)
