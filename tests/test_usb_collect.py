from pathlib import Path
import hashlib
import json
import os
import stat
import tempfile
import unittest

from tools.usb_collect import collect_storage


JPEG = b'\xff\xd8\xff\xe0\x00\x04AB\xff\xc0\x00\x0b\x08\x0d\x80\x12\x00\x01\x01\x11\x00'
ORF = b'IIRO\x08\x00\x00\x00' + bytes(range(64))


class USBCollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'mounted-card'
        self.directory = self.source / 'DCIM/100OLYMP'
        self.directory.mkdir(parents=True)
        self.orf = self.directory / 'P1010001.ORF'
        self.jpg = self.directory / 'P1010001.JPG'
        self.orf.write_bytes(ORF)
        self.jpg.write_bytes(JPEG)
        self.out = self.root / 'session'
        self.paths = ['/DCIM/100OLYMP/P1010001.ORF', '/DCIM/100OLYMP/P1010001.JPG']

    def test_copies_explicit_original_pair_with_hashes_and_dimensions(self):
        report = collect_storage(self.source, self.out, self.paths)
        self.assertEqual(report['status'], 'complete')
        self.assertFalse(report['camera_writes'])
        self.assertEqual([x['remote'] for x in report['files']], self.paths)
        self.assertEqual((report['files'][1]['width'], report['files'][1]['height']), (4608, 3456))
        for entry, original in zip(report['files'], (self.orf, self.jpg)):
            saved = self.out / entry['path']
            self.assertEqual(saved.read_bytes(), original.read_bytes())
            self.assertEqual(entry['sha256'], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text()), report)

    def test_existing_destination_and_invalid_paths_leave_originals_untouched(self):
        self.out.mkdir()
        (self.out / 'keep').write_text('keep')
        with self.assertRaises(FileExistsError):
            collect_storage(self.source, self.out, self.paths)
        self.assertEqual((self.out / 'keep').read_text(), 'keep')
        for path in ('/DCIM/../secret.ORF', '/DCIM/100OLYMP/../../secret.ORF', '/exec_pwoff.cgi'):
            with self.assertRaises(ValueError):
                collect_storage(self.source, self.root / ('bad-' + str(len(path))), [path])
        self.assertEqual(self.orf.read_bytes(), ORF)
        self.assertEqual(self.jpg.read_bytes(), JPEG)

    def test_rejects_bad_signature_and_file_limit_without_final_copy(self):
        self.orf.write_bytes(b'not an ORF')
        with self.assertRaisesRegex(ValueError, 'ORF'):
            collect_storage(self.source, self.out, [self.paths[0]])
        self.assertFalse((self.out / self.paths[0].lstrip('/')).exists())
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text())['status'], 'incomplete')
        self.out = self.root / 'small'
        with self.assertRaisesRegex(ValueError, 'limit'):
            collect_storage(self.source, self.out, [self.paths[1]], file_limit=12)
        self.assertFalse((self.out / self.paths[1].lstrip('/')).exists())

    def test_rejects_symlinked_card_entry_and_duplicate_paths(self):
        self.orf.unlink()
        self.orf.symlink_to(self.jpg)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            collect_storage(self.source, self.out, [self.paths[0]])
        self.assertEqual(self.jpg.read_bytes(), JPEG)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            collect_storage(self.source, self.root / 'duplicates', [self.paths[1], self.paths[1]])
        self.assertFalse((self.root / 'duplicates').exists())


if __name__ == '__main__':
    unittest.main()
