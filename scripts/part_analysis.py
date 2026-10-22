#!/usr/bin/env python3
"""Deep-dive the 4 OE partitions of the E-P5 firmware image."""
import hashlib
import lzma
import struct
import sys
import zlib

PATH = "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"
OUT = "/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work"

data = open(PATH, "rb").read()

# partition boundaries discovered from 'OE'+BE(0x1080) markers + 0x20 footers
PARTS = [
    (0x00000000, 0x00F00000),
    (0x00F00000, 0x024E0000),
    (0x024E0000, 0x02740000),
    (0x02740000, 0x02AC0000),
]

def hexdump(b, base, n=64):
    out = []
    for o in range(0, min(n, len(b)), 16):
        c = b[o:o+16]
        h = " ".join(f"{x:02X}" for x in c)
        t = "".join(chr(x) if 32 <= x < 127 else "." for x in c)
        out.append(f"{base+o:08X}  {h:<47}  |{t}|")
    return "\n".join(out)

print("=" * 78)
print("PER-PARTITION HEADER/FOOTER ANALYSIS")
print("=" * 78)

for idx, (s, e) in enumerate(PARTS):
    part = data[s:e]
    print(f"\n### PARTITION {idx}: 0x{s:08X} .. 0x{e:08X}  size={len(part)} (0x{len(part):X})")
    print(f"  sha256(part) = {hashlib.sha256(part).hexdigest()}")
    print(f"\n  -- header (first 0x40) --")
    print(hexdump(part, s, 0x40))
    print(f"\n  -- footer (last 0x40) --")
    print(hexdump(part[-0x40:], e - 0x40, 0x40))
    # trailing 0xFF run
    t = len(part)
    while t > 0 and part[t-1] == 0xFF:
        t -= 1
    print(f"  trailing 0xFF run: {len(part)-t} bytes (data ends at 0x{s+t:08X})")
    # leading header magic
    print(f"  magic: {part[0:2]!r} model=0x{struct.unpack('>H', part[2:4])[0]:04X}")
    # bytes 4..0x0A
    print(f"  hdr[0x04:0x0A] = {' '.join(f'{x:02X}' for x in part[4:10])}")
    print(f"  hdr[0x0A:0x0E] = {' '.join(f'{x:02X}' for x in part[10:14])}")
    print(f"  hdr[0x0E:0x18] = {' '.join(f'{x:02X}' for x in part[14:24])}")

print("\n" + "=" * 78)
print("FOOTER CRC32 CROSS-CHECK")
print("=" * 78)
for idx, (s, e) in enumerate(PARTS):
    part = data[s:e]
    ftr = part[-0x20:]
    crc_le = struct.unpack("<I", ftr[-4:])[0]
    crc_be = struct.unpack(">I", ftr[-4:])[0]
    body = part[:-0x20]
    body2 = part[:-0x18]
    cands = {
        "crc32(body)": zlib.crc32(body) & 0xFFFFFFFF,
        "crc32(body[:-8])": zlib.crc32(body[:-8]) & 0xFFFFFFFF,
        "crc32(body[0x20:])": zlib.crc32(body[0x20:]) & 0xFFFFFFFF,
        "crc32(part[:-4])": zlib.crc32(part[:-4]) & 0xFFFFFFFF,
    }
    print(f"\nPART {idx}: footer LE crc=0x{crc_le:08X} BE crc=0x{crc_be:08X}")
    for k, v in cands.items():
        tag = ""
        if v == crc_le:
            tag = "  <== MATCH (LE)"
        elif v == crc_be:
            tag = "  <== MATCH (BE)"
        print(f"    {k:<22} = 0x{v:08X}{tag}")

print("\n" + "=" * 78)
print("LZMA-ALONE CANDIDATES (decompress probe)")
print("=" * 78)
lzma_magic = b"\x5d\x00\x00"
pos = 0
while True:
    i = data.find(lzma_magic, pos)
    if i < 0:
        break
    pos = i + 1
    for skip in (0, 5, 9, 13):
        start = i + skip
        if start + 13 > len(data):
            continue
        props = data[start]
        dsize = struct.unpack("<I", data[start+1:start+5])[0]
        try:
            dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
            out = dec.decompress(data[start:start+min(len(data)-start, 8<<20)])
            if len(out) > 4096:
                print(f"\n  offset 0x{i:08X} (skip={skip}) props=0x{props:02X} dsize={dsize}")
                print(f"    decompressed {len(out)} bytes")
                print(f"    head: {out[:64].hex()}")
                txt = bytes(b for b in out[:64] if 32 <= b < 127)
                print(f"    ascii: {txt!r}")
                fn = f"{OUT}/lzma_{i:08X}_s{skip}.bin"
                open(fn, "wb").write(out)
                print(f"    saved -> {fn}")
                break
        except Exception:
            continue
