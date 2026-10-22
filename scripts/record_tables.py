#!/usr/bin/env python3
"""Parse the 16-byte record tables in E-P5 decoded blocks 1/2/3.

Record layout (per E-M1 III notes, same container lineage):
    (u32 address LE, u32 length LE, u32 zero, u32 zero)
Table region precedes the payload region; payload start = table_end.
"""
import json
import struct
from collections import Counter

BASE = "/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work/decoded"
BLOCKS = {
    1: ("01_0101_427c0020.decoded.bin", 0x427C0000),
    2: ("02_0106_43da0020.decoded.bin", 0x43DA0000),
    3: ("03_0104_44000020.decoded.bin", 0x44000000),
}


def load(idx):
    fn, base = BLOCKS[idx]
    return open(f"{BASE}/{fn}", "rb").read(), base


def parse_records(buf, table_end):
    """Read 16-byte (addr,len,0,0) entries from the head of buf."""
    recs = []
    off = 0
    while off + 16 <= table_end:
        addr, ln, z1, z2 = struct.unpack_from("<IIII", buf, off)
        recs.append((off, addr, ln, z1, z2))
        off += 16
    return recs


for idx in (1, 2, 3):
    buf, base = load(idx)
    print("=" * 92)
    print(f"BLOCK {idx}  size={len(buf)}  load_base=0x{base:08X}")
    print("=" * 92)
    # probe: how far does the (addr,len,0,0) pattern hold?
    table_end = None
    for probe_end in (0x400, 0x3E0, 0x800, 0x1000, 0x2000):
        recs = parse_records(buf, probe_end)
        good = sum(1 for _, a, l, z1, z2 in recs
                   if z1 == 0 and z2 == 0 and l != 0 and base <= a < base + len(buf) + 0x1000000)
        if good == len(recs) and recs:
            print(f"  probe table_end=0x{probe_end:X}: {good}/{len(recs)} records well-formed")
            table_end = probe_end
            break
    if table_end is None:
        # find where the pattern breaks
        off = 0
        while off + 16 <= len(buf):
            a, l, z1, z2 = struct.unpack_from("<IIII", buf, off)
            if not (z1 == 0 and z2 == 0):
                break
            off += 16
        table_end = off
        print(f"  table pattern breaks at 0x{off:X}")
    recs = parse_records(buf, table_end)
    print(f"  table entries = {len(recs)}  (table occupies 0x0..0x{table_end:X})")
    print(f"  payload region starts at block offset 0x{table_end:X}")
    print(f"\n  {'#':>3} {'off':>8} {'addr':>10} {'len':>10}  {'len%64K':>8}  note")
    for i, (off, a, l, z1, z2) in enumerate(recs[:24]):
        note = ""
        if z1 or z2:
            note = f"z1={z1:#x} z2={z2:#x}"
        print(f"  {i:>3} 0x{off:06X} 0x{a:08X} {l:>10}  {l>>16:>8}  {note}")
    if len(recs) > 24:
        print(f"  ... ({len(recs)-24} more)")
    # payload integrity: does sum(records) cover the payload region?
    total = sum(l for _, _, l, _, _ in recs)
    print(f"\n  sum(record lengths) = {total}  (block payload region = {len(buf)-table_end})")
    # ascii check inside each record's payload (addr maps to block offset?)
    print("\n  -- first 3 records: content peek --")
    for i, (off, a, l, _, _) in enumerate(recs[:3]):
        # guess: record data at (a - base) if inside block
        o = a - base
        if 0 <= o < len(buf) and l and o + l <= len(buf):
            seg = buf[o:o + min(l, 48)]
            txt = "".join(chr(b) if 32 <= b < 127 else "." for b in seg)
            print(f"    rec{i} @0x{o:08X} len={l}: {seg[:24].hex(' ')}  |{txt}|")
        else:
            print(f"    rec{i} addr 0x{a:08X} outside block (len={l})")
    print()
