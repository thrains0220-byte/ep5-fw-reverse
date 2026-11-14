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
PARAM_HOOK = 0x7e3ed835


def build_payload(image, out):
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
    param_old = bytes.fromhex('dd 62 f2 00 00 a0 14')
    if data[PARAM_HOOK - BASE:PARAM_HOOK - BASE + 7] != param_old:
        raise ValueError('native ART send call bytes differ')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    elf, binary = out / 'film.elf', out / 'film.bin'
    flags = ['-std=c99', '-Os', '-mno-am33', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-fno-pic', '-fno-common',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-Wl,--gc-sections']
    sources = [ROOT / 'firmware' / n for n in
               ('ep5_art_entry.S', 'ep5_art_entry.c', 'film.c', 'lut.c', 'look_store.c',
                'lut_menu.c', 'lut_menu_index.c')]
    checked([X / 'mn10300-elf-gcc', *flags, '-I', ROOT / 'firmware', *sources,
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
    state_offset = symbols['_ep5_ready_storage'] - CAVE
    look_state_offset = symbols['_ep5_look_state_storage'] - CAVE
    if len(payload) > END - CAVE or \
            struct.unpack_from('<7I', payload, control) != (0x43355045, 0, 0, 0, 0, 0, 0):
        raise ValueError('unexpected payload layout/defaults')
    if payload[state_offset:state_offset + 24] != bytes(24) or \
            symbols['_ep5_ready'] != CAVE + state_offset + 0x40000000 or \
            symbols['_ep5_look_state'] != CAVE + look_state_offset + 0x40000000:
        raise ValueError('unexpected qualification state/alias')
    patch = b'\xdc' + struct.pack('<I', (CAVE - HOOK) & 0xffffffff)
    paths = [*sources, ROOT / 'firmware/ep5_art_entry.ld', ROOT / 'firmware/film.h',
             ROOT / 'firmware/lut.h', ROOT / 'firmware/lut_menu.h',
             ROOT / 'firmware/lut_menu_index.h', ROOT / 'tools/cave_entry.py']
    report = dict(entry=hex(CAVE), end_exclusive=hex(CAVE + len(payload)),
                  payload_bytes=len(payload), cave_bytes=END - CAVE, spare_bytes=END - CAVE - len(payload),
                  control_offset=control, control_words=7,
                  state_offset=state_offset, state_uncached_address=hex(symbols['_ep5_ready']),
                  look_state_offset=look_state_offset,
                  look_state_uncached_address=hex(symbols['_ep5_look_state']),
                  lut_menu_offset=symbols['_ep5_lut_menu_storage'] - CAVE,
                  lut_menu_uncached_address=hex(symbols['_ep5_lut_menu']),
                  wait_entry_offset=symbols['_ep5_wait_entry'] - CAVE,
                  wait_call_offset=symbols['_ep5_wait_call'] - CAVE,
                  release_entry_offset=symbols['_ep5_release_entry'] - CAVE,
                  param_entry_offset=symbols['_ep5_param_entry'] - CAVE,
                  param_call_offset=symbols['_ep5_param_call'] - CAVE,
                  codec_call_offset=symbols['_ep5_codec_call'] - CAVE,
                  file_open_offset=symbols['_ep5_file_open'] - CAVE,
                  file_read_offset=symbols['_ep5_file_read'] - CAVE,
                  file_close_offset=symbols['_ep5_file_close'] - CAVE,
                  pool_alloc_offset=symbols['_ep5_pool_alloc'] - CAVE,
                  pool_free_offset=symbols['_ep5_pool_free'] - CAVE,
                  payload_sha256=hashlib.sha256(payload).hexdigest(),
                  main_sha256=MAIN_SHA256, compiler=checked([X / 'mn10300-elf-gcc', '--version']).splitlines()[0],
                  flags=flags, installable=False, default_enabled=False, plain_mn103_instruction_set=True,
                  patch=dict(cpu_address=hex(HOOK), image_offset=HOOK - BASE, old=old.hex(' '), new=patch.hex(' ')),
                  wait_patch=dict(cpu_address=hex(WAIT_HOOK), image_offset=WAIT_HOOK - BASE,
                                  old=wait_old.hex(' '), new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_wait_entry'] - WAIT_HOOK) & 0xffffffff) + b'\xcb\xcb').hex(' ')),
                  release_patch=dict(cpu_address=hex(RELEASE_HOOK), image_offset=RELEASE_HOOK - BASE,
                                     old=release_old.hex(' '), new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_release_entry'] - RELEASE_HOOK) & 0xffffffff)).hex(' ')),
                  param_patch=dict(cpu_address=hex(PARAM_HOOK), image_offset=PARAM_HOOK - BASE,
                                   old=param_old.hex(' '), new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_param_entry'] - PARAM_HOOK) & 0xffffffff) + b'\xcb\xcb').hex(' ')),
                  scope='Model-only cave layout and ABI candidate; no firmware container output.',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def build_diag_payload(image, out):
    """D diagnostic branch: observe-only module, compile-time pixel exclusion.

    Same cave/hooks as build_payload, but sources add diag.c with -DEP5_DIAG
    and the ep5_diag.ld script (bounded .bss for observation records). The
    control default is enabled=4 (diagnostic). This is a hardware-diagnostic
    candidate; it must never be labelled a functional LUT candidate.
    """
    data = Path(image).read_bytes()
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 main SHA-256 mismatch')
    if data[CAVE - BASE:END - BASE] != bytes([255]) * (END - CAVE):
        raise ValueError('code-space candidate is occupied')
    for addr, old in ((HOOK, bytes.fromhex('cd b3 6f f0 10')),
                      (WAIT_HOOK, bytes.fromhex('dd 57 a7 00 00 00 14')),
                      (RELEASE_HOOK, bytes.fromhex('cd 4b b6 00 04')),
                      (PARAM_HOOK, bytes.fromhex('dd 62 f2 00 00 a0 14'))):
        if data[addr - BASE:addr - BASE + len(old)] != old:
            raise ValueError(f'native hook bytes differ at {addr:#x}')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    elf, binary = out / 'diag.elf', out / 'diag.bin'
    flags = ['-std=c99', '-Os', '-mno-am33', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-fno-pic', '-fno-common',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-Wl,--gc-sections', '-DEP5_DIAG']
    sources = [ROOT / 'firmware' / n for n in
               ('ep5_art_entry.S', 'ep5_art_entry.c', 'diag.c')]
    checked([X / 'mn10300-elf-gcc', *flags, '-I', ROOT / 'firmware', *sources,
             '-T', ROOT / 'firmware/ep5_diag.ld', '-lgcc', '-o', elf])
    symbols = {line.split()[-1]: int(line.split()[0], 16) for line in
               checked([X / 'mn10300-elf-nm', '-n', elf]).splitlines() if len(line.split()) == 3}
    if symbols.get('_ep5_art_entry') != CAVE:
        raise ValueError('unexpected module entry')
    plain = checked([X / 'mn10300-elf-objdump', '-d', '-m', 'mn10300', elf]).splitlines()[3:]
    extended = checked([X / 'mn10300-elf-objdump', '-d', '-m', 'am33-2', elf]).splitlines()[3:]
    if plain != extended:
        raise ValueError('AM33-dependent instructions in module')
    (out / 'diag.s').write_text('\n'.join(plain) + '\n')
    # Compile-time exclusion proof: the pixel engine and look loader must be
    # absent from the diagnostic ELF, not merely unreachable.
    for banned in ('_ep5_film_apply', '_ep5_look_load', '_ep5_lut_sample16'):
        if banned in symbols:
            raise ValueError(f'diagnostic module must not contain {banned}')
    checked([X / 'mn10300-elf-objcopy', '-O', 'binary', elf, binary])
    payload = binary.read_bytes()
    control = symbols['_ep5_control'] - CAVE
    state_offset = symbols['_ep5_ready_storage'] - CAVE
    look_state_offset = symbols['_ep5_look_state_storage'] - CAVE
    if len(payload) > END - CAVE or \
            struct.unpack_from('<7I', payload, control) != (0x43355045, 0, 0, 0, 0, 0, 0):
        raise ValueError('unexpected payload layout/defaults')
    if payload[state_offset:state_offset + 24] != bytes(24):
        raise ValueError('unexpected qualification state')
    bss_start = symbols['_ep5_diag_bss_start'] - CAVE
    bss_end = symbols['_ep5_diag_bss_end'] - CAVE
    if not (0 < bss_end - bss_start <= 2048):
        raise ValueError('diagnostic bss out of bounds')
    # objcopy drops NOBITS .bss; append the 0xFF erase-pattern filler so the
    # flat boot image covers the record area. ep5_diag_init clears it on the
    # first param send (magic check), so the filler content is never trusted.
    if bss_start < len(payload):
        raise ValueError('bss overlaps loaded payload')
    payload += b'\xff' * (bss_end - len(payload))
    binary.write_bytes(payload)
    patch = b'\xdc' + struct.pack('<I', (CAVE - HOOK) & 0xffffffff)
    paths = [*sources, ROOT / 'firmware/ep5_diag.ld', ROOT / 'firmware/diag.h',
             ROOT / 'tools/cave_entry.py']
    report = dict(entry=hex(CAVE), end_exclusive=hex(CAVE + len(payload)),
                  payload_bytes=len(payload), cave_bytes=END - CAVE,
                  spare_bytes=END - CAVE - len(payload),
                  control_offset=control, control_words=7,
                  state_offset=state_offset,
                  look_state_offset=look_state_offset,
                  bss_offset=bss_start, bss_bytes=bss_end - bss_start,
                  wait_entry_offset=symbols['_ep5_wait_entry'] - CAVE,
                  wait_call_offset=symbols['_ep5_wait_call'] - CAVE,
                  release_entry_offset=symbols['_ep5_release_entry'] - CAVE,
                  param_entry_offset=symbols['_ep5_param_entry'] - CAVE,
                  param_call_offset=symbols['_ep5_param_call'] - CAVE,
                  codec_call_offset=symbols['_ep5_codec_call'] - CAVE,
                  file_write_offset=symbols['_ep5_file_write'] - CAVE,
                  diag_observe_offset=symbols['_ep5_diag_observe'] - CAVE,
                  diag_flush_offset=symbols['_ep5_diag_flush'] - CAVE,
                  payload_sha256=hashlib.sha256(payload).hexdigest(),
                  main_sha256=MAIN_SHA256,
                  compiler=checked([X / 'mn10300-elf-gcc', '--version']).splitlines()[0],
                  flags=flags, installable=False, default_enabled=False,
                  diagnostic=True, pixel_write_compiled_out=True,
                  plain_mn103_instruction_set=True,
                  patch=dict(cpu_address=hex(HOOK), image_offset=HOOK - BASE,
                             old='cd b3 6f f0 10', new=patch.hex(' ')),
                  wait_patch=dict(cpu_address=hex(WAIT_HOOK), image_offset=WAIT_HOOK - BASE,
                                  old='dd 57 a7 00 00 00 14',
                                  new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_wait_entry'] - WAIT_HOOK) & 0xffffffff) + b'\xcb\xcb').hex(' ')),
                  release_patch=dict(cpu_address=hex(RELEASE_HOOK), image_offset=RELEASE_HOOK - BASE,
                                     old='cd 4b b6 00 04',
                                     new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_release_entry'] - RELEASE_HOOK) & 0xffffffff)).hex(' ')),
                  param_patch=dict(cpu_address=hex(PARAM_HOOK), image_offset=PARAM_HOOK - BASE,
                                   old='dd 62 f2 00 00 a0 14',
                                   new=(b'\xdc' + struct.pack('<I', (symbols['_ep5_param_entry'] - PARAM_HOOK) & 0xffffffff) + b'\xcb\xcb').hex(' ')),
                  scope='D diagnostic branch: observe-only JPEG contract logging; '
                        'no pixel writes, no packet neutralization, stock imaging untouched.',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in paths})
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
        for name, overrides in specs:
            s = dict(tag=0x43355045, enabled=1, start=0x12000010, size=160,
                     encoding=1, amount=256, width=4, height=20, area_w=4, area_h=20, mode=0, address=0x12000010,
                     received=12, reply_error=0, reply_token=1, reply_packet=0x605f4510,
                     completion_ctx=0x11000000, repeats=1)
            s.update(overrides)
            s.setdefault('completion_address', s['address'])
            manifest, module = warm, directory / 'warm'
            lut = identity if name == 'identity' else warm_negative()
            original = bytearray([0xa5] * 16 + [100, 128, 160, 128] * 40 + [0xa5] * 16)
            expected = bytearray(original)
            if name in ('identity', 'warm', 'half', 'duplicate'):
                array = (ctypes.c_uint8 * len(expected)).from_buffer(expected)
                pointer = ctypes.cast(ctypes.byref(array, 16), bytep)
                view = Image(pointer, 160, 4, 20, 8)
                table = (ctypes.c_uint16 * 14739).from_buffer_copy(lut)
                if host(ctypes.byref(view), table, 14739, 1, s['amount'], None, None):
                    raise AssertionError('host reference failed')
            # control[6] points at the synthetic LUT region mapped by the probe.
            lut_address = 0x12000000 + 65536
            record = struct.pack('<7I4H9I', s['tag'], s['enabled'], s['start'], s['size'],
                                 s['encoding'], s['amount'], lut_address, s['width'], s['height'],
                                 s['area_w'], s['area_h'], s['mode'], s['address'], s['received'],
                                 s['reply_error'], s['reply_token'], s['reply_packet'], s['completion_ctx'], s['repeats'], s['completion_address'])
            (directory / 'config').write_bytes(record)
            (directory / 'pixels').write_bytes(original)
            (directory / 'lut').write_bytes(lut)
            native = json.loads(checked([runner, image, module / 'film.bin', directory / 'config',
                                         directory / 'pixels', directory / 'output', manifest['control_offset'],
                                         manifest['codec_call_offset'], manifest['state_offset'],
                                         manifest['wait_entry_offset'], manifest['wait_call_offset'], manifest['release_entry_offset'],
                                         directory / 'lut']))
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


def validate_param_entry(image):
    build = ROOT / 'build/param-probe'
    runner = build_probe(ROOT / 'tools/ep5_param_probe.c', build)
    table = struct.unpack_from('<6H', Path(image).read_bytes(), 0x7e559f8c - BASE)
    if table != (4608, 3456, 4608, 3456, 0, 0):
        raise ValueError('stock full-size geometry table differs')
    with tempfile.TemporaryDirectory(dir=build) as directory:
        payload = Path(directory) / 'payload'
        manifest = build_payload(image, payload)
        cases = []
        for name in ('enabled', 'disabled', 'lut_mode', 'wrong_tag', 'wrong_mode',
                     'wrong_variant', 'wrong_filter', 'wrong_packet', 'wrong_settings',
                     'wrong_aspect', 'wrong_size_code', 'wrong_geometry',
                     'wrong_source', 'wrong_value'):
            cases.append(json.loads(checked([runner, image, payload / 'film.bin',
                                             manifest['control_offset'], manifest['param_entry_offset'],
                                             manifest['param_call_offset'], name])))
    return dict(module=manifest, cases=cases, installable=False, physical_camera_test=False,
                stock_full_size_geometry_table=list(table),
                scope='One stock send call and cave veneer with synthetic settings and stock pre-send packet geometry; queue send is modeled.',
                not_tested=['menu selection on E-P5', 'shared packet ownership', 'ISP color effect',
                            'camera boot/cache/task scheduling', 'JPEG/ORF file output', 'installation/recovery'],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in (ROOT / 'tools/ep5_param_probe.c', build / 'cpu.c',
                                               build / 'isa.inc', runner)})


def validate_look_runtime(image):
    """Mode 3 full chain: stock send/receive/JPEG/release execute the cave
    veneers and SD look loader against a synthetic card and ART pool backend."""
    import zlib
    from ep5studio.wire import pack_index, pack_lut
    from ep5studio.project import Binding, Project
    build = ROOT / 'build/look-runtime'
    runner = build_probe(ROOT / 'tools/ep5_look_runtime_probe.c', build)
    shared = build / 'host-film.so'
    checked(['cc', '-std=c99', '-O2', '-shared', '-fPIC', ROOT / 'firmware/film.c',
             ROOT / 'firmware/lut.c', '-o', shared])
    host = ctypes.CDLL(str(shared)).ep5_film_apply
    bytep, wordp = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint16)
    host.argtypes = [ctypes.POINTER(Image), wordp, ctypes.c_size_t, ctypes.c_uint,
                     ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    table = warm_negative()
    look_id = 'a' * 64
    crc = zlib.crc32(table)
    lut_file = pack_lut(1, table)

    def card(amount=256, slot='pin-hole-i', lut_bytes=None, index_bytes=None):
        project = Project('runtime', (Binding(slot, look_id, '试验', amount),))
        index = pack_index(project, {look_id: 1}, {look_id: crc})
        return index_bytes if index_bytes is not None else index, \
            lut_bytes if lut_bytes is not None else lut_file

    def corrupt_crc(data):
        b = bytearray(data)
        b[-1] ^= 0xff
        return bytes(b)

    specs = [
        ('apply', dict(amount=256), True, True, 1),
        ('half', dict(amount=128), True, True, 1),
        ('missing_card', dict(amount=256), False, False, 1),
        ('missing_lut', dict(amount=256), True, False, 1),
        ('bad_index_crc', dict(amount=256, index_bytes=corrupt_crc(card()[0])), True, True, 1),
        ('bad_lut_crc', dict(amount=256, lut_bytes=corrupt_crc(lut_file)), True, True, 1),
        ('zero_amount', dict(amount=0), True, True, 1),
        ('pool_fail', dict(amount=256), True, True, 1),
        ('wrong_slot', dict(amount=256, slot='pin-hole-ii'), True, True, 1),
    ]
    cases = []
    with tempfile.TemporaryDirectory(dir=build) as directory:
        directory = Path(directory)
        manifest = build_payload(image, directory / 'module')
        module = directory / 'module'
        for name, kw, has_index, has_lut, direct in specs:
            amount = kw.get('amount', 256)
            index_bytes, lut_bytes = card(**kw)
            cdir = directory / name
            cdir.mkdir()
            if has_index:
                (cdir / 'INDEX.EP5').write_bytes(index_bytes)
            if has_lut:
                (cdir / 'L0000001.LUT').write_bytes(lut_bytes)
            s = dict(tag=0x43355045, enabled=3, start=0x12000010, size=160,
                     encoding=1, amount=256, width=4, height=20, area_w=4, area_h=20,
                     mode=0, address=0x12000010, received=12, reply_error=0, reply_token=1,
                     reply_packet=0x605f4510, completion_ctx=0x11000000, repeats=1,
                     picture_mode=105, variant=1, completion_address=0x12000010)
            record = struct.pack('<7I4H9I', s['tag'], s['enabled'], s['start'], s['size'],
                                 s['encoding'], s['amount'], 0, s['width'], s['height'],
                                 s['area_w'], s['area_h'], s['mode'], s['address'], s['received'],
                                 s['reply_error'], s['reply_token'], s['reply_packet'],
                                 s['completion_ctx'], s['repeats'], s['completion_address'])
            # config+28/+32 carry PictureMode/variant for the synthetic settings.
            record = record[:28] + struct.pack('<II', s['picture_mode'], s['variant']) + record[36:]
            (directory / 'config').write_bytes(record)
            original = bytearray([0xa5] * 16 + [100, 128, 160, 128] * 40 + [0xa5] * 16)
            (directory / 'pixels').write_bytes(original)
            expect_apply = name in ('apply', 'half')
            expected = bytearray(original)
            if expect_apply:
                array = (ctypes.c_uint8 * len(expected)).from_buffer(expected)
                pointer = ctypes.cast(ctypes.byref(array, 16), bytep)
                view = Image(pointer, 160, 4, 20, 8)
                tbl = (ctypes.c_uint16 * 14739).from_buffer_copy(table)
                if host(ctypes.byref(view), tbl, 14739, 1, amount, None, None):
                    raise AssertionError('host reference failed')
            native = json.loads(checked([runner, image, module / 'film.bin', directory / 'config',
                                         directory / 'pixels', directory / 'output',
                                         manifest['control_offset'], manifest['codec_call_offset'],
                                         manifest['state_offset'], manifest['wait_entry_offset'],
                                         manifest['wait_call_offset'], manifest['release_entry_offset'],
                                         manifest['param_entry_offset'], manifest['param_call_offset'],
                                         manifest['look_state_offset'], name, direct, cdir]))
            output = (directory / 'output').read_bytes()
            if output != expected or output[:16] != original[:16] or output[-16:] != original[-16:]:
                raise AssertionError(f'look runtime pixel/guard mismatch: {name}')
            # A failed allocation never frees, so strict alloc/free counting is
            # only meaningful when the block was actually taken. The invariant
            # that matters for every case is that no pool block is left live.
            if native.get('pool_leaked', not native['pool_balanced']):
                raise AssertionError(f'pool block leaked: {name}')
            if name != 'pool_fail' and not native['pool_balanced']:
                raise AssertionError(f'pool not balanced: {name}')
            if native['neutralized'] != (1 if expect_apply else 0):
                raise AssertionError(f'packet neutralization mismatch: {name}')
            cases.append(dict(**native, matches_host=True,
                              pixels_changed=output != original,
                              output_sha256=hashlib.sha256(output).hexdigest()))
    paths = [ROOT / 'tools/ep5_look_runtime_probe.c', ROOT / 'tools/cave_entry.py',
             ROOT / 'firmware/look_store.c', build / 'cpu.c', build / 'isa.inc', runner]
    return dict(module=manifest, cases=cases, cpu_source_revision=REVISION,
                installable=False, physical_camera_test=False,
                scope='Stock ART send/receive/JPEG/release fragments execute four cave veneers and the SD look loader; file service and ART pool are modeled backends fed with real desktop pack bytes.',
                models=['file selector picks direct or message backend',
                        'direct open/read/close and service 0x22 messages serve a synthetic two-file card',
                        'ART pool alloc/free backends hand out one contiguous 117912-byte block',
                        'stock send internals are modeled sinks returning the success path',
                        'JPEG sink records arguments and returns 0x1234; no ISP or encoder'],
                not_tested=['real SD mount/FAT', 'real boot/cave residency', 'cache/DMA visibility',
                            'watchdog/scheduling', 'full-size 15.9MP timing', 'JPEG/ORF file output',
                            'menu renaming', 'installation/recovery'],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='write a CPU-model execution report instead of module files')
    parser.add_argument('--diag', action='store_true', help='build the D diagnostic (observe-only) module')
    args = parser.parse_args()
    if args.check:
        report = validate_cave_entry(args.image)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x') as f:
            json.dump(report, f, indent=2)
            f.write('\n')
    elif args.diag:
        report = build_diag_payload(args.image, args.out)
    else:
        report = build_payload(args.image, args.out)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
