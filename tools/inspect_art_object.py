#!/usr/bin/env python3
"""Verify static E-P5 ART object construction and event dispatch evidence.

This inventories the exact E-P5 1.8 MAIN only. It executes no camera code and
does not establish GUI task safety, drawing ABI, or a firmware patch point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256

BASE = 0x7E101020
FIRST_TABLE = 0x7EDF658C
SECOND_TABLE = 0x7EDF63CC
THIRD_TABLE = 0x7EDF6024
ART_VTABLE = 0x7EDF7C88
ART_EVENT_TABLE = 0x7EDF7C14
ART_LIST = 0x7EDF7BDC


def u32(data: bytes, address: int) -> int:
    return struct.unpack_from('<I', data, address - BASE)[0]


def extract(data: bytes) -> dict:
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('requires exact decoded E-P5 1.8 MAIN')
    routes = {}
    for ident, expected in ((0x91, 0x7EB1E329), (0x9D, 0x7EB1E31F)):
        # First level: hash lookup on identifier-2; stop at empty entry.
        key = ident - 2
        index = key & 31
        for _ in range(32):
            found = u32(data, FIRST_TABLE + 8 * index)
            if found in (0, key):
                break
            index = (index + 1) & 31
        if found:
            raise ValueError(f'identifier {ident:#x} unexpectedly matched first table')
        second = u32(data, SECOND_TABLE + 4 * (ident - 141))
        third = u32(data, THIRD_TABLE + 4 * (ident - 12))
        if second != 0x7EB1E2F9 or third != expected:
            raise ValueError(f'unexpected dispatch route for {ident:#x}')
        routes[f'0x{ident:02x}'] = {'second': hex(second), 'third': hex(third)}

    methods = [u32(data, ART_VTABLE + 4 * i) for i in range(5)]
    expected = [0x7EB28BAC, 0x7EB1E76A, 0x7EB28BDF, 0x7EB29265, 0x7EB2942E]
    if methods != expected:
        raise ValueError('unexpected ART object vtable')
    events = [u32(data, ART_EVENT_TABLE + 4 * i) for i in range(29)]
    if events[:7] != [0x7EB2928F, 0x7EB29297, 0x7EB292CA,
                      0x7EB2929F, 0x7EB292B3, 0x7EB292C2, 0x7EB292A9]:
        raise ValueError('unexpected ART object event jump table')
    records, setting_id, record_count = struct.unpack_from('<IHH', data, ART_LIST - BASE)
    if (records, setting_id, record_count) != (0x7EDF7908, 0x119, 13):
        raise ValueError('unexpected ART list descriptor')
    # Check key instruction bytes as well as pointers. These signatures are
    # necessary evidence, not an executable model of constructor semantics.
    signatures = {
        0x7EB1E329: bytes.fromhex('dd 22 a8 00 00 00 04'),
        0x7EB28B55: bytes.fromhex('2c b0 01'),
        0x7EB28B81: bytes.fromhex('fc cc 88 7c df 7e'),
        0x7EB2928F: bytes.fromhex('98 cd 4b 00 30 0c'),
        0x7EB29297: bytes.fromhex('98 cd 6d 00 30 0c'),
        0x7EB28C08: bytes.fromhex('fc cc dc 7b df 7e'),
        0x7EB28C5B: bytes.fromhex('f9 00 2c'),
        # Startup loads this initialized-data segment through its uncached alias.
        0x7E101198: bytes.fromhex('fc cc e4 b3 5a 7e'),
        0x7E1011EA: bytes.fromhex('fc dc 00 e0 74 40'),
        0x7E1011F0: bytes.fromhex('fc dd 40 9b 2a a0'),
        0x7E1011F6: bytes.fromhex('fc c1 00 10 a7 81'),
        0x7EAB79D7: bytes.fromhex('fc dc 50 e3 2b 60 2c a8 00'),
        0x7EAB79E0: bytes.fromhex('dd 20 c1 f5 ff a0 0c'),
    }
    for address, expected_bytes in signatures.items():
        if data[address - BASE:address - BASE + len(expected_bytes)] != expected_bytes:
            raise ValueError(f'unexpected instruction bytes at {address:#x}')
    table_ram = u32(data, 0x7EAB79D9)
    flash_source = u32(data, 0x7E1011EC)
    source = BASE + flash_source - 0x402C0020
    destination = u32(data, 0x7E1011F2) ^ 0xC0000000
    length = u32(data, 0x7E10119A) - source
    table_source = source + table_ram - destination
    count = struct.unpack_from('<H', data, 0x7EAB79DE - BASE)[0]
    if not (destination <= table_ram and table_ram + count * 16 <= destination + length):
        raise ValueError('GUI table outside startup initialized data')
    slots = []
    for ident, expected_buffer, expected_size in (
            (0, 0x606EB274, 12), (15, 0x606EB452, 12), (58, 0x606F1670, 188)):
        read, update, buffer, size = struct.unpack_from('<IIII', data, table_source + 16 * ident - BASE)
        if (read, update, buffer, size) != (0, 0, expected_buffer, expected_size):
            raise ValueError(f'unexpected ART GUI slot {ident}')
        slots.append({'id': ident, 'read_callback': hex(read), 'update_callback': hex(update),
                      'buffer': hex(buffer), 'bytes': size})
    return {
        'main_sha256': MAIN_SHA256,
        'scope': 'static tables and instruction bytes; no execution, drawing ABI or camera access',
        'physical_camera_test': False,
        'routes': routes,
        'gui_service': {
            'manager_global': '0x602b75b4', 'register': '0x7ea13b00',
            'read': '0x7ea13b47', 'update': '0x7ea13b5f',
            'table_ram': hex(table_ram), 'table_source': hex(table_source),
            'entry_count': count, 'entry_stride': 16, 'art_slots': slots,
            'initializer': {'flash_source': hex(flash_source), 'main_source': hex(source),
                            'ram_destination': hex(destination), 'bytes': length},
            'runtime_table_mutations_tested': False,
        },
        'art': {
            'identifier': '0x91', 'factory': '0x7eb28b4b',
            'allocation_bytes': 432, 'instance_global': '0x602c132c',
            'constructor': '0x7eb28b7a', 'vtable': hex(ART_VTABLE),
            'vtable_first_five': [hex(value) for value in methods],
            'event_jump_targets': [hex(value) for value in events],
            'event_0_handler': '0x7eb292db', 'event_1_handler': '0x7eb29305',
            'selection_offset': 416, 'list_pointer_offset': 412,
            'availability_pointer_offset': 420,
            'list_descriptor': hex(ART_LIST), 'list_records': hex(records),
            'list_setting_id': setting_id, 'list_count': record_count,
            'record_stride': 44,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin')
    args = parser.parse_args()
    print(json.dumps(extract(args.image.read_bytes()), indent=2))


if __name__ == '__main__':
    main()
