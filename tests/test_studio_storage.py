"""Persistent project identity, colour declarations and corrupt-package checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo

from ep5studio.builtins import default_cubes
from ep5studio.export import export_project, validate_style_archive, unpack_index, unpack_lut, build_firmware, pack_index, pack_lut
from ep5studio.library import Library
from ep5studio.project import Binding, Project, load_project, save_project


class StudioStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = Library(self.root / 'library')
        self.original = next(default_cubes())[1]
        self.look = self.library.import_bytes(self.original, filename='identity.cube')
        self.project = Project('我的测试', (Binding('pin-hole-i', self.look.id, '晴天', 192),))

    def test_original_identity_survives_dedup_and_project_roundtrip(self):
        self.assertEqual(self.look.id, hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.library.source(self.look.id), self.original)
        duplicate = self.library.import_bytes(self.original, filename='other-name.cube')
        self.assertEqual(duplicate, self.look)
        self.assertEqual(len(self.library.list_looks()), 1)
        path = self.root / '项目.json'
        save_project(self.project, path)
        self.assertEqual(load_project(path), self.project)
        bad = self.project.to_dict()
        bad['bindings'] *= 2
        path.write_text(json.dumps(bad), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_project(path)

    def test_unknown_and_log_cannot_be_exported_as_srgb(self):
        target = self.root / 'styles.zip'
        for encoding in ('unknown', 'vlog', 'rec709'):
            self.library.set_encodings(self.look.id, encoding, 'srgb')
            with self.assertRaises(ValueError):
                export_project(self.project, self.library, target)
            self.assertFalse(target.exists())
        with self.assertRaises(RuntimeError):
            build_firmware(self.project, self.library)

    def test_binary_indices_bind_payload_and_reject_mixed_packages(self):
        self.library.set_encodings(self.look.id, 'srgb', 'srgb')
        target = self.root / 'styles.zip'
        report = export_project(self.project, self.library, target)
        self.assertFalse(report['camera_ready'])
        self.assertFalse(report['firmware_file_created'])
        with ZipFile(target) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        self.assertFalse(any(name.lower().endswith('.bin') for name in files))
        rows = unpack_index(files['EP5LUT/INDEX.EP5'])
        self.assertEqual((rows[0]['label'], rows[0]['amount_q8']), ('晴天', 192))
        number, table = unpack_lut(files['EP5LUT/L0000001.LUT'])
        self.assertEqual(number, rows[0]['number'])
        import zlib
        self.assertEqual(rows[0]['table_crc32'], zlib.crc32(table))
        # Mix a valid, internally consistent LUT from another export at the same number.
        other = list(default_cubes())[1][1]
        look = self.library.import_bytes(other, input_encoding='srgb', output_encoding='srgb')
        second = self.root / 'second.zip'
        export_project(Project('第二包', (Binding('pin-hole-i', look.id, '暖调'),)), self.library, second)
        with ZipFile(second) as archive:
            for name in ('EP5LUT/L0000001.LUT', 'SOURCE/L0000001.cube', 'manifest.json'):
                files[name] = archive.read(name)
        mixed = self.root / 'mixed.zip'
        with ZipFile(mixed, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        with self.assertRaises(ValueError):
            validate_style_archive(mixed)
        with self.assertRaises(FileExistsError):
            export_project(self.project, self.library, target)

    def test_corruption_is_listed_and_never_exported(self):
        table = self.library.folder(self.look.id) / 'table.rgb16le'
        damaged = bytearray(table.read_bytes())
        damaged[107] ^= 1
        table.write_bytes(damaged)
        self.assertEqual(self.library.list_looks(), [])
        self.assertTrue(self.library.errors)
        with self.assertRaises(ValueError):
            self.library.table(self.look.id)

    def test_non_object_metadata_does_not_break_library(self):
        (self.library.folder(self.look.id) / 'look.json').write_text('[]', encoding='utf-8')
        self.assertEqual(self.library.list_looks(), [])
        self.assertTrue(self.library.errors)

    def test_changed_warning_special_file_and_false_derivation_are_rejected(self):
        import stat
        import zlib
        self.library.set_encodings(self.look.id, 'srgb', 'srgb')
        target = self.root / 'good.zip'
        export_project(self.project, self.library, target)
        with ZipFile(target) as archive:
            files = {n: archive.read(n) for n in archive.namelist()}
        for variant in ('notice', 'symlink', 'false_table', 'metadata'):
            changed = dict(files)
            if variant == 'notice':
                changed['NOT_A_FIRMWARE.txt'] = b'Please flash this BIN!'
            elif variant == 'false_table':
                # All hashes and CRCs match each other; source/table derivation does not.
                table = bytes(29478)
                changed['EP5LUT/L0000001.LUT'] = pack_lut(1, table)
                changed['EP5LUT/INDEX.EP5'] = pack_index(self.project, {self.look.id: 1}, {self.look.id: zlib.crc32(table)})
                manifest = json.loads(changed['manifest.json'])
                manifest['looks'][0]['table_sha256'] = hashlib.sha256(table).hexdigest()
                changed['manifest.json'] = json.dumps(manifest).encode('utf-8')
            elif variant == 'metadata':
                manifest = json.loads(changed['manifest.json'])
                manifest['looks'][0]['resample'] = {'camera_calibrated': True}
                changed['manifest.json'] = json.dumps(manifest).encode('utf-8')
            out = self.root / (variant + '.zip')
            with ZipFile(out, 'w') as archive:
                for name, data in changed.items():
                    info = ZipInfo(name)
                    if variant == 'symlink' and name.startswith('SOURCE/'):
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, data)
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                validate_style_archive(out)

    def test_extreme_error_metadata_is_an_isolated_bad_entry(self):
        metadata = self.library.folder(self.look.id) / 'look.json'
        value = json.loads(metadata.read_text(encoding='utf-8'))
        value['resample']['max_rgb8_error'] = 10 ** 500
        metadata.write_text(json.dumps(value), encoding='utf-8')
        self.assertEqual(self.library.list_looks(), [])
        self.assertTrue(self.library.errors)


if __name__ == '__main__':
    unittest.main()
