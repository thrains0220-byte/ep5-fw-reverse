#!/usr/bin/env python3
"""Crack the OE footer CRC32 semantics + decode header field semantics."""
import struct
import zlib

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
data = open(P, "rb").read()
PARTS = [(0x00000000, 0x00F00000), (0x00F00000, 0x024E0000),
         (0x024E0000, 0x02740000), (0x02740000, 0x02AC0000)]

print("=" * 84)
print("HEADER FIELD SEMANTICS")
print("=" * 84)
for i, (s, e) in enumerate(PARTS):
    h = data[s:s+0x20]
    pay = data[s+0x20:e-0x20]
    blocks_le = struct.unpack("<H", h[0x0E:0x10])[0]
    resid = len(pay) - blocks_le * 0x10000
    print(f"  part{i}: +0x0E LE16={blocks_le:>6}  payload={len(pay):>9}  "
          f"payload-0x{blocks_le:X}*64K = 0x{resid:X}  {'CONSISTENT' if resid == 0xFFC0 else ''}")
    print(f"          +0x0A LE16={struct.unpack('<H', h[0x0A:0x0C])[0]:>6}  "
          f"BE16={struct.unpack('>H', h[0x0A:0x0C])[0]:>6}  "
          f"+0x10 LE16={struct.unpack('<H', h[0x10:0x12])[0]:>5}  "
          f"+0x14 LE16={struct.unpack('<H', h[0x14:0x16])[0]:>5}")

print("\n" + "=" * 84)
print("FOOTER CRC32 BRUTE FORCE  (which byte range / which field order)")
print("=" * 84)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    want_le = struct.unpack("<I", part[-4:])[0]
    want_be = struct.unpack(">I", part[-4:])[0]
    hits = []
    starts = list(range(0, 0x21))
    ends = set()
    for L in range(0, 0x30):
        ends.add(len(part) - L)
    ends.add(len(part) - 0x20)
    for st in starts:
        for en in sorted(ends):
            if en <= st:
                continue
            c = zlib.crc32(part[st:en]) & 0xFFFFFFFF
            if c == want_le:
                hits.append((f"LE match: part[0x{st:X}:0x{en:X}]", c))
            if c == want_be:
                hits.append((f"BE match: part[0x{st:X}:0x{en:X}]", c))
    print(f"\n  part{i}: want_le=0x{want_le:08X} want_be=0x{want_be:08X}")
    if hits:
        for h in hits:
            print("    ***", h[0])
    else:
        print("    no plain-zlib range match")

print("\n" + "=" * 84)
print("CRC OVER PAYLOAD WITH SEED / XOR VARIANTS")
print("=" * 84)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    want = struct.unpack("<I", part[-4:])[0]
    pay = part[0x20:-0x20]
    found = []
    seeds = [0x00000000, 0xFFFFFFFF, 0x1D, 0x04C11DB7, 0xEDB88320,
             struct.unpack("<I", part[0x18:0x1C])[0],
             struct.unpack("<I", part[0x0A:0x0E])[0]]
    for sd in seeds:
        v = zlib.crc32(pay, sd) & 0xFFFFFFFF
        if v == want:
            found.append(f"seed=0x{sd:08X} over payload")
        if (v ^ 0xFFFFFFFF) == want:
            found.append(f"seed=0x{sd:08X} over payload, final xor 0xFFFFFFFF")
    # reversed payload
    rv = zlib.crc32(pay[::-1]) & 0xFFFFFFFF
    if rv == want:
        found.append("reversed payload")
    # byte-swapped crc
    for lbl, v in [("payload", zlib.crc32(pay) & 0xFFFFFFFF)]:
        if struct.unpack(">I", struct.pack("<I", v))[0] == want:
            found.append(f"{lbl} crc byteswapped")
    print(f"  part{i}: {found if found else 'no match'}")

print("\n" + "=" * 84)
print("ADLER32 / SUM CHECK ALTERNATIVES")
print("=" * 84)
for i, (s, e) in enumerate(PARTS):
    part = data[s:e]
    want = struct.unpack("<I", part[-4:])[0]
    pay = part[0x20:-0x20]
    a = zlib.adler32(pay) & 0xFFFFFFFF
    print(f"  part{i}: adler32(payload)=0x{a:08X}  want=0x{want:08X}  "
          f"{'ADLER MATCH' if a == want else ''}")
    # simple 32-bit additive sum
    sm = sum(pay) & 0xFFFFFFFF
    print(f"          sum32(payload)   =0x{sm:08X}  {'SUM MATCH' if sm == want else ''}")
