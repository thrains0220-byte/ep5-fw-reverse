from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools.camera_collect import collect, validate_host, validate_file


class CameraCollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "session"
        self.calls = []
        self.slow_paths = set()
        self.responses = {
            "/get_caminfo.cgi": (200, b'<caminfo><model>E-P5</model><serial>PRIVATE</serial></caminfo>', {}),
            "/get_commandlist.cgi": (200, b'<oishare><version>2.20</version></oishare>', {}),
            "/get_connectmode.cgi": (200, b'<connectmode>play</connectmode>', {}),
            "/get_imglist.cgi?DIR=/DCIM": (200, b'/DCIM/100OLYMP', {}),
            "/DCIM/100OLYMP/P1010001.ORF": (200, b'IIRO\x08\x00\x00\x00' + bytes(range(128)), {}),
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.calls.append((self.command, self.path, self.headers.get("User-Agent")))
                code, body, headers = owner.responses.get(self.path, (404, b'', {}))
                self.send_response(code)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    if self.path in owner.slow_paths:
                        for value in body:
                            self.wfile.write(bytes([value]))
                            self.wfile.flush()
                            time.sleep(0.025)
                    else:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.host = f'127.0.0.1:{server.server_port}'
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.shutdown)

    def test_collects_only_allowlisted_gets_and_private_files_without_proxy(self):
        with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1',
                                    'NO_PROXY': '', 'no_proxy': ''}):
            report = collect(self.host, self.out, files=['/DCIM/100OLYMP/P1010001.ORF'])
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['model'], 'E-P5')
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertEqual([x[1] for x in self.calls], list(self.responses))
        self.assertTrue(all(x[0] == 'GET' and x[2] == 'OlympusCameraKit' for x in self.calls))
        for entry in report['files']:
            p = self.out / entry['path']
            self.assertEqual(p.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), entry['sha256'])
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text()), report)

    def test_wrong_model_stops_before_other_requests(self):
        self.responses['/get_caminfo.cgi'] = (200, b'<caminfo><model>E-M10</model></caminfo>', {})
        with self.assertRaisesRegex(ValueError, 'E-P5'):
            collect(self.host, self.out)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text())['status'], 'incomplete')

    def test_redirect_is_never_followed(self):
        self.responses['/get_caminfo.cgi'] = (302, b'', {'Location': '/switch_cammode.cgi?mode=rec'})
        with self.assertRaises(Exception):
            collect(self.host, self.out)
        self.assertEqual(len(self.calls), 1)

    def test_xml_entities_and_malformed_identity_are_rejected(self):
        for content in (b'<!DOCTYPE caminfo [<!ENTITY x "E-P5">]><caminfo><model>&x;</model></caminfo>',
                        '<!DOCTYPE caminfo [<!ENTITY x "E-P5">]><caminfo><model>&x;</model></caminfo>'.encode('utf-16'),
                        '<!DOCTYPE caminfo [<!ENTITY x "E-P5">]><caminfo><model>&x;</model></caminfo>'.encode('utf-16-le'),
                        '<!DOCTYPE caminfo [<!ENTITY x "E-P5">]><caminfo><model>&x;</model></caminfo>'.encode('utf-16-be'),
                        b'<caminfo><model>E-P5', b'<notcamera><model>E-P5</model></notcamera>'):
            with self.subTest(content=content):
                self.responses['/get_caminfo.cgi'] = (200, content, {})
                destination = self.out / str(len(self.calls))
                with self.assertRaises(ValueError):
                    collect(self.host, destination)

    def test_metadata_size_limit_stops_request(self):
        self.responses['/get_caminfo.cgi'] = (200, b'X' * 200, {})
        with self.assertRaisesRegex(ValueError, 'limit'):
            collect(self.host, self.out, metadata_limit=128)
        self.assertEqual(len(self.calls), 1)

    def test_slow_drip_is_cut_off_by_total_deadline(self):
        self.slow_paths.add('/get_caminfo.cgi')
        started = time.monotonic()
        with patch('tools.camera_collect.TOTAL_SECONDS', 0.15, create=True):
            with self.assertRaises(TimeoutError):
                collect(self.host, self.out, timeout=1)
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text())['status'], 'incomplete')

    def test_existing_destination_is_untouched_and_makes_no_request(self):
        self.out.mkdir()
        (self.out / 'keep').write_text('keep')
        with self.assertRaises(FileExistsError):
            collect(self.host, self.out)
        self.assertEqual(self.calls, [])
        self.assertEqual((self.out / 'keep').read_text(), 'keep')

    def test_bad_original_magic_leaves_no_final_file(self):
        path = '/DCIM/100OLYMP/P1010001.ORF'
        self.responses[path] = (200, b'not an ORF', {})
        with self.assertRaisesRegex(ValueError, 'ORF'):
            collect(self.host, self.out, files=[path])
        self.assertFalse((self.out / path.lstrip('/')).exists())

    def test_original_download_limit_and_invalid_paths_before_network(self):
        path = '/DCIM/100OLYMP/P1010001.ORF'
        with self.assertRaisesRegex(ValueError, 'limit'):
            collect(self.host, self.out, files=[path], file_limit=16)
        self.assertFalse((self.out / path.lstrip('/')).exists())
        self.calls.clear()
        with self.assertRaises(ValueError):
            collect(self.host, self.out / 'invalid', files=['/exec_pwoff.cgi'])
        self.assertEqual(self.calls, [])

    def test_jpeg_dimensions_are_read_from_original_not_resize_endpoint(self):
        path = '/DCIM/100OLYMP/P1010001.JPG'
        # A header fixture, not a decodable photograph.
        frame = b'\xff\xd8\xff\xe0\x00\x04AB\xff\xc0\x00\x0b\x08\x0d\x80\x12\x00\x01\x01\x11\x00'
        self.responses[path] = (200, frame, {})
        report = collect(self.host, self.out, files=[path])
        self.assertEqual((report['files'][-1]['width'], report['files'][-1]['height']), (4608, 3456))
        self.assertEqual(self.calls[-1][1], path)
        self.assertFalse(any('resize' in x[1] for x in self.calls))

    def test_host_and_download_paths_cannot_select_control_endpoints(self):
        for host in ('example.com', '8.8.8.8', '0.0.0.0', '224.0.0.1', 'http://192.168.0.10',
                     '192.168.0.10/path', 'user@192.168.0.10', '192.168.0.10#fragment'):
            with self.assertRaises(ValueError, msg=host):
                validate_host(host)
        self.assertEqual(validate_host('192.168.0.10'), '192.168.0.10')
        for path in ('/exec_pwoff.cgi', '/DCIM/../get_caminfo.cgi', '//host/file.ORF',
                     '/DCIM/100OLYMP/P1010001.ORF?x=1', '/DCIM/100OLYMP/%2e%2e.ORF',
                     '/DCIM/100OLYMP/test.BIN'):
            with self.assertRaises(ValueError, msg=path):
                validate_file(path)


if __name__ == '__main__':
    unittest.main()
