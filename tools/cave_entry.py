#!/usr/bin/env python3
"""Build/check an E-P5 cave module and CPU-model overlay, never a camera update."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_mn103_lut import Image, X, checked
from tools.compile_lut import warm_negative
from tools.native_probe import MAIN_SHA256, REVISION, build_probe

BASE, CAVE, END, HOOK = 0x7e101020, 0x7e128010, 0x7e130000, 0x7e3ed8d1
WAIT_HOOK = 0x7e3ed850
RELEASE_HOOK = 0x7e3f2476


def build_payload(image, out, lut=None):
    data = Path(image).read_bytes()
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 main SHA-256 mismatch')
    if data[CAVE - BASE:END - BASE] != bytes([255]) * (END - CAVE):
        raise ValueError('code-space candidate is occupied')
    old = bytes.fromhex('cd b3 6f f0 10')
    if data[HOOK - BASE:HOOK - BASE + 5] != old:
        raise ValueError('native ART call bytes differ')
    wait_old = bytes.fromhex('dd 57 a7 00 00 00 14')
    if data[WAIT_HOOK - BASE:WAIT_HOOK - BASE + 7] != wait_old:
        raise ValueError('native ART receive call bytes differ')
    release_old = bytes.fromhex('cd 4b b6 00 04')
    if data[RELEASE_HOOK - BASE:RELEASE_HOOK - BASE + 5] != release_old:
        raise ValueError('native ART release call bytes differ')
    lut = warm_negative() if lut is None else lut
    if len(lut) != 29478:
        raise ValueError('expected a 17-cubed RGB16 LUT')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    table = out / 'table.c'
    words = struct.unpack('<14739H', lut)
    table.write_text('#include "lut.h"\nconst uint16_t ep5_embedded_lut[EP5_LUT_VALUES] '
                     '__attribute__((section(".ep5.lut"),used)) = {' + ','.join(map(str, words)) + '};\n')
    elf, binary = out / 'film.elf', out / 'film.bin'
    flags = ['-std=c99', '-Os', '-mno-am33', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-fno-pic', '-fno-common',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-Wl,--gc-sections']
    sources = [ROOT / 'firmware' / n for n in ('ep5_art_entry.S', 'ep5_art_entry.c', 'film.c', 'lut.c')]
    checked([X / 'mn10300-elf-gcc', *flags, '-I', ROOT / 'firmware', *sources, table,
             '-T', ROOT / 'firmware/ep5_art_entry.ld', '-lgcc', '-o', elf])
    symbols = {line.split()[-1]: int(line.split()[0], 16) for line in
               checked([X / 'mn10300-elf-nm', '-n', elf]).splitlines() if len(line.split()) == 3}
    if symbols.get('_ep5_art_entry') != CAVE:
        raise ValueError('unexpected module entry')
    plain = checked([X / 'mn10300-elf-objdump', '-d', '-m', 'mn10300', elf]).splitlines()[3:]
    extended = checked([X / 'mn10300-elf-objdump', '-d', '-m', 'am33-2', elf]).splitlines()[3:]
    if plain != extended:
        raise ValueError('AM33-dependent instructions in module')
    (out / 'film.s').write_text('\n'.join(plain) + '\n')
    checked([X / 'mn10300-elf-objcopy', '-O', 'binary', elf, binary])
    payload = binary.read_bytes()
    control = symbols['_ep5_control'] - CAVE
    lut_offset = symbols['_ep5_embedded_lut'] - CAVE
    state_offset = symbols['_ep5_ready_storage'] - CAVE
    if len(payload) > END - CAVE or payload[lut_offset:lut_offset + 29478] != lut or \
            struct.unpack_from('<6I', payload, control) != (0x43355045, 0, 0, 0, 0, 0):
        raise ValueError('unexpected payload layout/defaults')
    if payload[state_offset:state_offset + 8] != bytes(8) or symbols['_ep5_ready'] != CAVE + state_offset + 0x40000000:
        raise ValueError('unexpected qualification state/alias')
    patch = b'\xdc' + struct.pack('<I', (CAVE - HOOK) & 0xffffffff)
    paths = [*sources, ROOT / 'firmware/ep5_art_entry.ld', ROOT / 'firmware/film.h',
             ROOT / 'firmware/lut.h', ROOT / 'tools/cave_entry.py']
    report = dict(entry=hex(CAVE), end_exclusive=hex(CAVE + len(payload)),
                  payload_bytes=len(payload), cave_bytes=END - CAVE, spare_bytes=END - CAVE - len(payload),
                  control_offset=control, lut_offset=lut_offset, lut_bytes=len(lut),
                  state_offset=state_offset, state_uncached_address=hex(symbols['_ep5_ready']),
                  wait_entry_offset=symbols['_ep5_wait_entry'] - CAVE,
                  wait_call_offset=symbols['_ep5_wait_call'] - CAVE,
                  release_entry_offset=symbols['_ep5_release_entry'] - CAVE,
                  codec_call_offset=symbols['_ep5_codec_call'] - CAVE,
                  lut_sha256=hashlib.sha256(lut).hexdigest(), payload_sha256=hashlib.sha256(payload).hexdigest(),
                  main_sha256=MAIN_SHA256, compiler=checked([X / 'mn10300-elf-gcc', '--version']).splitlines()[0],
                  flags=flags, installable=False, default_enabled=False, plain_mn103_instruction_set=True,
                  patch=dict(cpu_address=hex(HOOK), image_offset=HOOK - BASE, old=old.hex(' '), new=patch.hex(' ')),
                  wait_patch=dict(cpu_address=hex(WAIT_HOOK), image_offset=WAIT_HOOK - BASE,
                                  old=wait_old.hex(' '), new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_wait_entry'] - WAIT_HOOK) & 0xffffffff) + b'\xcb\xcb').hex(' ')),
                  release_patch=dict(cpu_address=hex(RELEASE_HOOK), image_offset=RELEASE_HOOK - BASE,
                                     old=release_old.hex(' '), new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_release_entry'] - RELEASE_HOOK) & 0xffffffff)).hex(' ')),
                  scope='Model-only cave layout and ABI candidate; no firmware container output.',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def validate_cave_entry(image):
    image = Path(image).resolve()
    build = ROOT / 'build/cave-entry-check'
    runner = build_probe(ROOT / 'tools/ep5_cave_probe.c', build)
    shared = build / 'host-film.so'
    checked(['cc', '-std=c99', '-O2', '-shared', '-fPIC', ROOT / 'firmware/film.c',
             ROOT / 'firmware/lut.c', '-o', shared])
    host = ctypes.CDLL(str(shared)).ep5_film_apply
    bytep, wordp = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint16)
    host.argtypes = [ctypes.POINTER(Image), wordp, ctypes.c_size_t, ctypes.c_uint,
                     ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    identity = struct.pack('<14739H', *(round(c * 65535 / 16)
                           for b in range(17) for g in range(17) for r in range(17) for c in (r, g, b)))
    specs = [('disabled', {'enabled': 0}), ('identity', {}), ('warm', {}), ('half', {'amount': 128}),
             ('capacity', {'size': 159}), ('encoding', {'encoding': 0}), ('amount', {'amount': 257}),
             ('mapping', {'start': 0x12000011}), ('null_mapping', {'start': 0}),
             ('geometry', {'area_w': 2}), ('resize', {'mode': 1}), ('tag', {'tag': 0}),
             ('map_wrap', {'start': 0xfffffff0, 'size': 64, 'address': 0xfffffff0}),
             ('request_overlap', {'start': 0x6000efc0, 'size': 512, 'address': 0x6000efcc}),
             ('request_alias_overlap', {'start': 0xa000efc0, 'size': 512, 'address': 0xa000efcc}),
             ('code_overlap', {'start': CAVE, 'size': END - CAVE, 'address': CAVE}),
             ('uncached_code_overlap', {'start': CAVE + 0x40000000, 'size': END - CAVE,
                                         'address': CAVE + 0x40000000}),
             ('completion_missing', {'received': 0x7fffffff}), ('receive_failure', {'received': 0xffffffff}),
             ('short_reply', {'received': 8}), ('completion_error', {'reply_error': 0x9a04}),
             ('short_reply_11', {'received': 11}), ('receive_timeout', {'received': 0xffffffce}),
             ('wrong_token', {'reply_token': 2}), ('wrong_packet', {'reply_packet': 0x605f469c}),
             ('wrong_context', {'completion_ctx': 0x11000080}), ('duplicate', {'repeats': 2}),
             ('wrong_buffer', {'completion_address': 0x12000100}),
             ('released_reuse', {'repeats': 3})]
    cases = []
    with tempfile.TemporaryDirectory(dir=build) as directory:
        directory = Path(directory)
        warm = build_payload(image, directory / 'warm')
        neutral = build_payload(image, directory / 'identity', identity)
        for name, overrides in specs:
            s = dict(tag=0x43355045, enabled=1, start=0x12000010, size=160,
                     encoding=1, amount=256, width=4, height=20, area_w=4, area_h=20, mode=0, address=0x12000010,
                     received=12, reply_error=0, reply_token=1, reply_packet=0x605f4510,
                     completion_ctx=0x11000000, repeats=1)
            s.update(overrides)
            s.setdefault('completion_address', s['address'])
            manifest, module = (neutral, directory / 'identity') if name == 'identity' else (warm, directory / 'warm')
            original = bytearray([0xa5] * 16 + [100, 128, 160, 128] * 40 + [0xa5] * 16)
            expected = bytearray(original)
            if name in ('identity', 'warm', 'half', 'duplicate'):
                array = (ctypes.c_uint8 * len(expected)).from_buffer(expected)
                pointer = ctypes.cast(ctypes.byref(array, 16), bytep)
                view = Image(pointer, 160, 4, 20, 8)
                lut = identity if name == 'identity' else warm_negative()
                table = (ctypes.c_uint16 * 14739).from_buffer_copy(lut)
                if host(ctypes.byref(view), table, 14739, 1, s['amount'], None, None):
                    raise AssertionError('host reference failed')
            record = struct.pack('<6I4H9I', s['tag'], s['enabled'], s['start'], s['size'],
                                 s['encoding'], s['amount'], s['width'], s['height'],
                                 s['area_w'], s['area_h'], s['mode'], s['address'], s['received'],
                                 s['reply_error'], s['reply_token'], s['reply_packet'], s['completion_ctx'], s['repeats'], s['completion_address'])
            (directory / 'config').write_bytes(record)
            (directory / 'pixels').write_bytes(original)
            native = json.loads(checked([runner, image, module / 'film.bin', directory / 'config',
                                         directory / 'pixels', directory / 'output', manifest['control_offset'],
                                         manifest['codec_call_offset'], manifest['state_offset'],
                                         manifest['wait_entry_offset'], manifest['wait_call_offset'], manifest['release_entry_offset']]))
            output = (directory / 'output').read_bytes()
            if output != expected or output[:16] != original[:16] or output[-16:] != original[-16:]:
                raise AssertionError(f'cave/native pixel or guard mismatch: {name}')
            cases.append(dict(name=name, **native, matches_host=True, pixels_changed=output != original,
                              output_sha256=hashlib.sha256(output).hexdigest()))
    paths = [ROOT / 'tools/ep5_cave_probe.c', ROOT / 'tools/cave_entry.py', ROOT / 'tools/native_probe.py',
             build / 'cpu.c', build / 'isa.inc', runner]
    return dict(module=warm, cases=cases, cpu_source_revision=REVISION, installable=False, physical_camera_test=False,
                scope='Stock ART receive tail, queue wrapper, JPEG caller and release fragments execute three cave veneers and GCC colour engine.',
                models=['local queue route predicate returns zero',
                        'kernel queue receive copies a synthetic complete/partial reply and returns length/error',
                        'queue error/log sinks return with native frames',
                        'JPEG sink records arguments and returns 0x1234; pool free only records its argument',
                        'native receive-tail/JPEG/release fragments are driven separately; no task scheduler or ISP'],
                bypass_reference='Invalid/disabled cases pin byte-exact bypass; positive cases call the host C engine.',
                not_tested=['real boot/cave residency', 'ART buffer production/format/ownership', 'cache',
                            'watchdog/scheduling', 'normal-still routing', 'cross-job delayed-reply freshness/concurrency', 'JPEG encoding',
                            'effect menu', 'installation/recovery'],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='write a CPU-model execution report instead of module files')
    args = parser.parse_args()
    if args.check:
        report = validate_cave_entry(args.image)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x') as f:
            json.dump(report, f, indent=2)
            f.write('\n')
    else:
        report = build_payload(args.image, args.out)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
