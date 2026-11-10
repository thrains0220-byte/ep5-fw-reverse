#!/usr/bin/env python3
"""Collect E-P5 native read-only HTTP evidence; never change networks or camera state."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

TOTAL_SECONDS = 30


def validate_host(host):
    try:
        parsed = urllib.parse.urlsplit('http://' + host)
        address = ipaddress.IPv4Address(parsed.hostname)
        allowed = any(address in ipaddress.IPv4Network(net) for net in
                      ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8'))
        if not allowed or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        if host != str(address) + (f':{parsed.port}' if parsed.port is not None else ''):
            raise ValueError
    except (ValueError, TypeError) as error:
        raise ValueError('host must be a numeric private/local IPv4 address, optionally :port') from error
    return host


def validate_file(path):
    if not re.fullmatch(r'/DCIM/[A-Za-z0-9_]{1,32}/[A-Za-z0-9_]{1,32}\.(?:ORF|JPG)', path, re.I):
        raise ValueError('file must be a direct /DCIM/directory/name.ORF or .JPG path')
    return path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeadlineSocket(socket.socket):
    def remaining_timeout(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('HTTP request exceeded total deadline')
        self.settimeout(min(self.idle_timeout, remaining))

    def recv_into(self, *args):
        # HTTPResponse.read(n) may call recv repeatedly; bound each to the same deadline.
        self.remaining_timeout()
        return super().recv_into(*args)

    def sendall(self, *args):
        self.remaining_timeout()
        return super().sendall(*args)


class DeadlineConnection(http.client.HTTPConnection):
    def connect(self):
        deadline = time.monotonic() + TOTAL_SECONDS
        self.timeout = min(self.timeout, TOTAL_SECONDS)
        super().connect()
        original = self.sock
        self.sock = DeadlineSocket(original.family, original.type, original.proto, fileno=original.detach())
        self.sock.deadline, self.sock.idle_timeout = deadline, self.timeout
        self.sock.remaining_timeout()


class DeadlineHTTP(urllib.request.HTTPHandler):
    def http_open(self, request):
        return self.do_open(DeadlineConnection, request)


def jpeg_dimensions(path):
    with path.open('rb') as f:
        if f.read(2) != b'\xff\xd8':
            raise ValueError('invalid JPEG signature')
        while True:
            if f.read(1) != b'\xff':
                raise ValueError('missing JPEG frame header')
            marker = f.read(1)
            while marker == b'\xff':
                marker = f.read(1)
            if not marker or marker[0] in (0xda, 0xd9, 0):
                raise ValueError('missing JPEG dimensions')
            if marker[0] in (*range(0xd0, 0xd9), 0x01):
                continue
            length_bytes = f.read(2)
            if len(length_bytes) != 2:
                raise ValueError('truncated JPEG segment')
            length = int.from_bytes(length_bytes, 'big')
            if length < 2:
                raise ValueError('invalid JPEG segment length')
            if marker[0] in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                frame = f.read(length - 2)
                if len(frame) != length - 2 or length < 8:
                    raise ValueError('truncated JPEG frame')
                height, width = int.from_bytes(frame[1:3], 'big'), int.from_bytes(frame[3:5], 'big')
                if not width or not height:
                    raise ValueError('invalid JPEG dimensions')
                return width, height
            f.seek(length - 2, 1)


def collect(host, out, files=(), metadata_limit=512 * 1024, file_limit=128 * 1024 * 1024, timeout=8):
    host = validate_host(host)
    files = [validate_file(path) for path in files]
    if len(set(files)) != len(files):
        raise ValueError('duplicate download path')
    if metadata_limit <= 0 or file_limit <= 0 or not 0 < timeout <= 30:
        raise ValueError('invalid response limit or timeout')
    out = Path(out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), DeadlineHTTP())
    report = dict(status='incomplete', host=host, camera_writes=False, files=[])

    def fetch(remote, relative, limit, original=False):
        destination = out / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        part = destination.with_name(destination.name + '.part')
        request = urllib.request.Request(f'http://{host}{remote}', headers={'User-Agent': 'OlympusCameraKit'}, method='GET')
        sha = hashlib.sha256()
        size = 0
        deadline = time.monotonic() + TOTAL_SECONDS
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError(f'unexpected HTTP status: {response.status}')
            declared = response.headers.get('Content-Length')
            if declared is not None:
                declared = int(declared)
                if not 0 <= declared <= limit:
                    raise ValueError('response exceeds byte limit')
            with os.fdopen(os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
                while True:
                    if time.monotonic() > deadline:
                        raise TimeoutError('response exceeded total deadline')
                    block = response.read(min(256 * 1024, limit + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    if size > limit:
                        raise ValueError('response exceeds byte limit')
                    sha.update(block)
                    f.write(block)
            if declared is not None and size != declared:
                raise ValueError('truncated HTTP response')
        entry = dict(path=str(relative), remote=remote, bytes=size, sha256=sha.hexdigest())
        if original:
            if remote.upper().endswith('.JPG'):
                entry['width'], entry['height'] = jpeg_dimensions(part)
            else:
                with part.open('rb') as f:
                    signature = f.read(8)
                if len(signature) < 8 or signature[:4] not in (b'IIRO', b'IIRS', b'MMOR'):
                    raise ValueError('invalid ORF signature')
            entry['signature_checked'] = True
        os.link(part, destination)
        part.unlink()
        report['files'].append(entry)
        return destination

    try:
        info = fetch('/get_caminfo.cgi', Path('caminfo.xml'), metadata_limit).read_bytes().decode('utf-8-sig')
        if '\x00' in info or '<!DOCTYPE' in info.upper() or '<!ENTITY' in info.upper():
            raise ValueError('XML declarations/entities are not accepted')
        try:
            root = ET.fromstring(info)
        except ET.ParseError as error:
            raise ValueError('malformed E-P5 caminfo XML') from error
        models = root.findall('model')
        model = (models[0].text or '').strip() if len(models) == 1 else ''
        if root.tag != 'caminfo' or model.upper() not in ('E-P5', 'OLYMPUS E-P5'):
            raise ValueError('camera identity is not an E-P5; collection stopped')
        report['model'] = model
        for remote, local in (('/get_commandlist.cgi', 'commands.xml'),
                              ('/get_connectmode.cgi', 'connectmode.xml'),
                              ('/get_imglist.cgi?DIR=/DCIM', 'dcim-list.txt')):
            fetch(remote, Path(local), metadata_limit)
        for path in files:
            fetch(path, Path(path.lstrip('/')), file_limit, original=True)
        report['status'] = 'complete'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        with os.fdopen(os.open(out / 'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.0.10')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--file', action='append', default=[], help='explicit original /DCIM/...ORF or .JPG path')
    args = parser.parse_args()
    try:
        report = collect(args.host, args.out, args.file)
    except Exception as error:
        parser.exit(1, f'Collection stopped: {error}\n')
    print(f"Collected {len(report['files'])} files from {report['model']} into {args.out}")


if __name__ == '__main__':
    main()
