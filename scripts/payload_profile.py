#!/usr/bin/env python3
"""Header field table + payload content profiling for the 4 OE partitions."""
import re
import struct
import zlib
from collections import Counter

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
OUT = "/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work"
data = open(P, "rb").read()
PARTS = [(0x00000000, 0x00F00000), (0x00F00000, 0x024E0000),
         (0x024E0000, 0x02740000), (0x02740000, 0x02AC0000)]

print("=" * 90)
print("HEADER FIELD COMPARISON  (header[0x00:0x20], footer == header[:0x1C] + crc32)")
print("=" * 90)
hdrs = [data[s:s+0x20] for s, e in PARTS]
for off in range(0, 0x1C, 2):
    vals = [h[off:off+2].hex() for h in hdrs]
    le = [struct.unpack("<H", h[off:off+2])[0] for h in hdrs]
    be = [struct.unpack(">H", h[off:off+2])[0] for h in hdrs]
    tag = "CONST" if len(set(vals)) == 1 else "     "
    print(f"  +0x{off:02X} {tag} bytes={vals}  LE={le}  BE={be}")

print("\n" + "=" * 90)
print("PARTITION SIZES")
print("=" * 90)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    pay = part[0x20:-0x20]
    print(f"  part{i}: file 0x{s:08X}-0x{e:08X}  total={len(part):>9}  payload={len(pay):>9}")

print("\n" + "=" * 90)
print("PAYLOAD FIRST 128 BYTES (post-header, pre-footer)")
print("=" * 90)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    pay = part[0x20:-0x20]
    print(f"\n--- part{i} @ 0x{s+0x20:08X} ---")
    for o in range(0, 128, 16):
        c = pay[o:o+16]
        h = " ".join(f"{x:02X}" for x in c)
        t = "".join(chr(x) if 32 <= x < 127 else "." for x in c)
        print(f"  {s+0x20+o:08X}  {h:<47}  |{t}|")

print("\n" + "=" * 90)
print("PAYLOAD: 16-BIT VALUE HISTOGRAM (top 12) + 0xFF run profile")
print("=" * 90)
for i, (s, e) in enumerate(PARTS):
    pay = data[s:e][0x20:-0x20]
    vals = struct.unpack(f"<{len(pay)//2}H", pay[:len(pay)//2*2])
    c = Counter(vals)
    top = c.most_common(12)
    ff = pay.count(0xFF) / len(pay)
    print(f"\n  part{i}: 0xFF ratio={ff:.1%}   distinct 16-bit values={len(c)}")
    print("    top:", ", ".join(f"0x{v:04X}({n})" for v, n in top))

print("\n" + "=" * 90)
print("ASCII STRINGS (len>=8) per partition  -- first 40 unique")
print("=" * 90)
for i, (s, e) in enumerate(PARTS):
    pay = data[s:e][0x20:-0x20]
    strs = re.findall(rb"[\x20-\x7e]{8,}", pay)
    uniq = []
    seen = set()
    for x in strs:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    print(f"\n--- part{i}: total strings={len(strs)} unique={len(uniq)} ---")
    for x in uniq[:40]:
        print(f"    {x.decode('latin-1')}")
