#!/usr/bin/env python3
"""Copy explicitly selected E-P5 originals from a mounted USB Storage card, read only."""
import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.camera_collect import jpeg_dimensions, validate_file


def collect_storage(source, out, files, file_limit=128 * 1024 * 1024):
    if Path(out).is_symlink():
        raise ValueError('output must be a new directory, not a symlink')
    source, out = Path(source).resolve(), Path(out).resolve()
    files = [validate_file(path) for path in files]
    if not files or len({path.lower() for path in files}) != len(files):
        raise ValueError('at least one unique original file is required; duplicate paths are not allowed')
    if file_limit <= 0:
        raise ValueError('invalid file limit')
    if not source.is_dir():
        raise ValueError('source must be a mounted Storage directory')
    if out.is_relative_to(source):
        raise ValueError('output must be outside the camera Storage directory')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = dict(status='incomplete', source=str(source), camera_writes=False, files=[])
    try:
        for path in files:
            relative = Path(path.lstrip('/'))
            destination = out / relative
            part = destination.with_name(destination.name + '.part')
            digest = hashlib.sha256()
            size = 0
            try:
                with ExitStack() as opened:
                    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                    directory_fd = os.open(source, directory_flags)
                    opened.callback(os.close, directory_fd)
                    for component in relative.parts[:-1]:
                        directory_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                        opened.callback(os.close, directory_fd)
                    src = opened.enter_context(os.fdopen(os.open(
                        relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=directory_fd), 'rb'))
                    info = os.fstat(src.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError(f'not a regular original file: {path}')
                    if info.st_size > file_limit:
                        raise ValueError('original exceeds byte limit')
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    dst = opened.enter_context(os.fdopen(os.open(
                        part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb'))
                    while block := src.read(min(256 * 1024, file_limit + 1 - size)):
                        size += len(block)
                        if size > file_limit:
                            raise ValueError('original exceeds byte limit')
                        digest.update(block)
                        dst.write(block)
                entry = dict(path=str(relative), remote=path, bytes=size, sha256=digest.hexdigest())
                if path.upper().endswith('.JPG'):
                    entry['width'], entry['height'] = jpeg_dimensions(part)
                else:
                    with part.open('rb') as src:
                        signature = src.read(8)
                    if len(signature) < 8 or signature[:4] not in (b'IIRO', b'IIRS', b'MMOR'):
                        raise ValueError('invalid ORF signature')
                entry['signature_checked'] = True
                part.rename(destination)
                report['files'].append(entry)
            except OSError as error:
                part.unlink(missing_ok=True)
                if error.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise ValueError(f'symlink or invalid camera path: {path}') from error
                raise
            except Exception:
                part.unlink(missing_ok=True)
                raise
        report['status'] = 'complete'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        with os.fdopen(os.open(out / 'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as dst:
            json.dump(report, dst, indent=2, ensure_ascii=False)
            dst.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='mounted camera Storage root containing DCIM')
    parser.add_argument('--out', type=Path, required=True, help='new private session directory outside the camera')
    parser.add_argument('--file', action='append', required=True,
                        help='explicit /DCIM/directory/name.ORF or .JPG path; repeat for each file')
    args = parser.parse_args()
    try:
        report = collect_storage(args.source, args.out, args.file)
    except Exception as error:
        parser.exit(1, f'Collection stopped: {error}\n')
    print(f"Copied {len(report['files'])} originals into {args.out}")


if __name__ == '__main__':
    main()
