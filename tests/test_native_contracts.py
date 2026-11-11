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

    def test_modified_image_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'modified.bin'
            bad.write_bytes(b'not stock')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                run_contracts(bad)
