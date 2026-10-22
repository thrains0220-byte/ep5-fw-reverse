#!/usr/bin/env python3
"""Semantic search inside the firmware payload: version, lens/AF data, part2 layout."""
import re
import struct

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
data = open(P, "rb").read()
PARTS = [(0x00000000, 0x00F00000), (0x00F00000, 0x024E0000),
         (0x024E0000, 0x02740000), (0x02740000, 0x02AC0000)]
NAMES = ["part0", "part1", "part2", "part3"]


def payload(i):
    s, e = PARTS[i]
    return data[s+0x20:e-0x20]


def hd(b, base, n=96, w=16):
    for o in range(0, min(n, len(b)), w):
        c = b[o:o+w]
        h = " ".join(f"{x:02X}" for x in c)
        t = "".join(chr(x) if 32 <= x < 127 else "." for x in c)
        print(f"  {base+o:08X}  {h:<{w*3}}  |{t}|")


print("=" * 88)
print("VERSION / MODEL STRING SEARCH in whole image")
print("=" * 88)
pats = [rb"1\.8", rb"1080", rb"E-P5", rb"EP5", rb"Ver\.?1", rb"FW_?1\.8",
        rb"OLY_E_", rb"Firmware", rb"firmware", rb"OMD", rb"OM SYSTEM"]
for p in pats:
    hits = [m.start() for m in re.finditer(re.escape(p), data)]
    hits = [h for h in hits if 32 <= h < len(data) - 1]
    shown = ", ".join(f"0x{h:08X}(p{[i for i,(s,e) in enumerate(PARTS) if s<=h<e]})" for h in hits[:10])
    print(f"  {p.decode('latin-1'):<12} n={len(hits):<4} {shown}")

print("\n" + "=" * 88)
print("PART2 sparse block layout (payload +0x3E0 onward)")
print("=" * 88)
p2 = payload(2)
hd(p2[0x3E0:0x3E0+0x100], PARTS[2][0]+0x20+0x3E0, 0x100)
print("\n  -- stride analysis: compare bytes at +0x3E0 and +0x3E0+stride --")
for stride in (8, 12, 16, 20, 24, 32, 64, 128, 256):
    a = p2[0x3E0:0x3E0+8]
    b = p2[0x3E0+stride:0x3E0+stride+8]
    print(f"    stride={stride:<4} first8={a.hex(' ')}  next8={b.hex(' ')}")

print("\n" + "=" * 88)
print("PART3 record decode attempt (16B records, 8B data + 8B 0xFF pad)")
print("=" * 88)
p3 = payload(3)
for r in range(6):
    rec = p3[r*16:(r+1)*16]
    print(f"  rec{r}: {rec.hex(' ')}")
    # try interpreting as 4 LE16
    v = struct.unpack("<4H", rec[:8])
    print(f"        LE16: {' '.join(f'{x:04X}' for x in v)}")

print("\n" + "=" * 88)
print("PART1 first records: LE16 decode")
print("=" * 88)
p1 = payload(1)
for r in range(8):
    rec = p1[r*16:(r+1)*16]
    v = struct.unpack("<4H", rec[:8])
    print(f"  rec{r}: {rec.hex(' ')}   LE16: {' '.join(f'{x:04X}' for x in v)}")

print("\n" + "=" * 88)
print("PART0: look for an index/offset table at head")
print("=" * 88)
p0 = payload(0)
hd(p0[0:0x100], PARTS[0][0]+0x20, 0x100)
