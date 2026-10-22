#!/usr/bin/env python3
"""Per-partition structural reverse engineering.

part0: high-entropy bytecode / compressed code block
part1: 16-bit record table with 0xFF delimiter runs  -> looks like a font/lookup/param table
part2: sparse data block (mostly 0x00) -> configuration/calibration table
part3: structured 0xFF-delimited records
"""
import re
import struct
from collections import Counter

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
data = open(P, "rb").read()
PARTS = [(0x00000000, 0x00F00000), (0x00F00000, 0x024E0000),
         (0x024E0000, 0x02740000), (0x02740000, 0x02AC0000)]


def payload(i):
    s, e = PARTS[i]
    return data[s+0x20:e-0x20]


def hd(b, base, n=64, w=16):
    for o in range(0, min(n, len(b)), w):
        c = b[o:o+w]
        h = " ".join(f"{x:02X}" for x in c)
        t = "".join(chr(x) if 32 <= x < 127 else "." for x in c)
        print(f"  {base+o:08X}  {h:<{w*3}}  |{t}|")


# ============ part1: record table ============
print("=" * 88)
print("PART1 record-structure analysis")
print("=" * 88)
p1 = payload(1)
# find record boundaries: runs of >=4 0xFF bytes
runs = []
i = 0
while i < len(p1):
    if p1[i] == 0xFF:
        j = i
        while j < len(p1) and p1[j] == 0xFF:
            j += 1
        if j - i >= 3:
            runs.append((i, j - i))
        i = j
    else:
        i += 1
print(f"  0xFF runs >=3: count={len(runs)}")
print("  first 12 runs:", [(f"0x{a:X}", n) for a, n in runs[:12]])
# Show a region with several records
print("\n  -- record region 0xF00020..0xF00200 --")
hd(p1[0:0x200], PARTS[1][0]+0x20, 0x200)

print("\n  -- record region 0x1000000 area --")
off = 0x100000 - PARTS[1][0]
hd(p1[off:off+0x100], PARTS[1][0]+0x20+off, 0x100)

# ============ part3: record structure ============
print("\n" + "=" * 88)
print("PART3 record-structure analysis")
print("=" * 88)
p3 = payload(3)
runs = []
i = 0
while i < len(p3):
    if p3[i] == 0xFF:
        j = i
        while j < len(p3) and p3[j] == 0xFF:
            j += 1
        if j - i >= 3:
            runs.append((i, j - i))
        i = j
    else:
        i += 1
print(f"  0xFF runs >=3: count={len(runs)}")
print("  first 12 runs:", [(f"0x{a:X}", n) for a, n in runs[:12]])
print("\n  -- head 0x200 --")
hd(p3[0:0x200], PARTS[3][0]+0x20, 0x200)

# ============ part2: sparse data ============
print("\n" + "=" * 88)
print("PART2 sparse-data analysis")
print("=" * 88)
p2 = payload(2)
# locate non-zero regions
nz = []
i = 0
while i < len(p2):
    if p2[i] != 0x00:
        j = i
        while j < len(p2) and p2[j] != 0x00:
            j += 1
        nz.append((i, j - i))
        i = j
    else:
        i += 1
print(f"  non-zero runs: count={len(nz)}  total bytes={sum(n for _, n in nz)}")
for a, n in nz[:25]:
    print(f"    off=0x{a:06X} len={n}  (file 0x{PARTS[2][0]+0x20+a:08X})")
print("\n  -- first 0x200 --")
hd(p2[0:0x200], PARTS[2][0]+0x20, 0x200)

# ============ part0: byte-code? ============
print("\n" + "=" * 88)
print("PART0 structure analysis")
print("=" * 88)
p0 = payload(0)
print(f"  size={len(p0)}")
# Look for repeated opcode-ish patterns
c = Counter(p0)
print("  top byte values:", ", ".join(f"0x{v:02X}({n})" for v, n in c.most_common(14)))
# check for a length/terminator preamble
for guess in (4, 8, 12, 16):
    v = struct.unpack("<I", p0[:4])[0]
print(f"  first u32 LE = 0x{struct.unpack('<I', p0[:4])[0]:08X} = {struct.unpack('<I', p0[:4])[0]}")
print(f"  first u32 BE = 0x{struct.unpack('>I', p0[:4])[0]:08X}")
print(f"  bytes[0x00:0x10] = {p0[:16].hex(' ')}")
print(f"  bytes[0x10:0x20] = {p0[0x10:0x20].hex(' ')}")
