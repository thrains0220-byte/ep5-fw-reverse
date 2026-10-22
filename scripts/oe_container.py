#!/usr/bin/env python3
"""Olympus 'OE' firmware container parser.

Parses the OLY_E_<model>_<ver>_0000_0000.BIN container format:
  header at 0x00, footer at EOF-0x20, 'OE' magic + 0x1080 model code.
Each section payload is located by scanning for 'OE' + model code pairs.
"""
import hashlib
import struct
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/sanyu/Projects/work/E-P5_固件_1.8/OLY_E_108_1800_0000_0000.BIN"

data = open(PATH, "rb").read()
print(f"file      : {PATH}")
print(f"size      : {len(data)} (0x{len(data):X})")
print(f"sha256    : {hashlib.sha256(data).hexdigest()}")

print("\n=== head 0x40 ===")
for off in range(0, 0x40, 16):
    chunk = data[off:off+16]
    hexs = " ".join(f"{b:02X}" for b in chunk)
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{off:08X}  {hexs:<47}  |{txt}|")

print("\n=== tail 0x40 ===")
base = len(data) - 0x40
for off in range(0, 0x40, 16):
    o = base + off
    chunk = data[o:o+16]
    hexs = " ".join(f"{b:02X}" for b in chunk)
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{o:08X}  {hexs:<47}  |{txt}|")

# CRC32 check over body (footer holds a CRC32 of the image)
import zlib
crc_guess = struct.unpack("<I", data[-4:])[0]
print(f"\nfooter crc32 field : 0x{crc_guess:08X}")
for span, label in [
    (data[:-0x20], "all-but-footer32"),
    (data[:-0x20], "hdr->footer"),
]:
    pass
cands = {
    "crc32(data[:-0x20])": zlib.crc32(data[:-0x20]) & 0xFFFFFFFF,
    "crc32(data[:-0x18])": zlib.crc32(data[:-0x18]) & 0xFFFFFFFF,
    "crc32(data[:-0x30])": zlib.crc32(data[:-0x30]) & 0xFFFFFFFF,
    "crc32(data[0:])": zlib.crc32(data) & 0xFFFFFFFF,
}
for k, v in cands.items():
    print(f"  {k:<22} = 0x{v:08X} {'<== MATCH' if v == crc_guess else ''}")

# --- locate every 'OE' magic + model-code pair (model code is BIG-endian) ---
MODEL = 0x1080
print(f"\n=== 'OE' + 0x{MODEL:04X} section markers (big-endian model code) ===")
for label, needle in [
    ("BE", b"OE" + struct.pack(">H", MODEL)),
    ("LE", b"OE" + struct.pack("<H", MODEL)),
]:
    pos = 0
    marks = []
    while True:
        i = data.find(needle, pos)
        if i < 0:
            break
        marks.append(i)
        pos = i + 1
    print(f"  [{label}] count = {len(marks)}")
    for i, m in enumerate(marks):
        end = marks[i+1] if i + 1 < len(marks) else len(data)
        region = data[m:end]
        ff = region.count(0xFF) / max(len(region), 1)
        print(f"      [{i:2d}] 0x{m:08X}  size=0x{end-m:X} ({end-m})  ff_ratio={ff:.1%}")

# --- generic magic scan for embedded payloads ---
print("\n=== embedded magic scan ===")
MAGICS = {
    "gzip":        b"\x1f\x8b\x08",
    "xz":          b"\xfd7zXZ\x00",
    "bzip2":       b"BZh",
    "lzma-alone":  b"\x5d\x00\x00",
    "lz4":         b"\x04\x22\x4d\x18",
    "zstd":        b"\x28\xb5\x2f\xfd",
    "squashfs-le": b"hsqs",
    "squashfs-be": b"sqsh",
    "UBI-EC":      b"UBI#",
    "UBI-VID":     b"UBI!",
    "cramfs-le":   b"\x45\xcd\x21\x28",
    "ext4-super":  b"\x53\xef",
    "ZIP":         b"PK\x03\x04",
    "ELF":         b"\x7fELF",
    "zlib-78-9c":  b"\x78\x9c",
    "zlib-78-da":  b"\x78\xda",
    "zlib-78-01":  b"\x78\x01",
    "zlib-78-5e":  b"\x78\x5e",
    "LZMA-pcma":   b"\x5d\x00\x00\x80",
    "OLY-OE":      b"OE",
}
for name, sig in MAGICS.items():
    hits = []
    pos = 0
    while True:
        i = data.find(sig, pos)
        if i < 0:
            break
        hits.append(i)
        pos = i + 1
        if len(hits) > 200:
            break
    shown = ", ".join(f"0x{h:08X}" for h in hits[:12])
    more = f" (+{len(hits)-12} more)" if len(hits) > 12 else ""
    print(f"  {name:<14} n={len(hits):<5} {shown}{more}")

# --- byte-value census on the whole image ---
print("\n=== byte census (top 12) ===")
counts = [0]*256
for b in data:
    counts[b] += 1
top = sorted(range(256), key=lambda x: -counts[x])[:12]
for b in top:
    print(f"  0x{b:02X}  {counts[b]:>10}  {counts[b]/len(data):>6.2%}")

# --- entropy per 1 MiB slab ---
print("\n=== entropy per 1 MiB slab (first/last differ => region boundaries) ===")
import math
def ent(blob):
    if not blob:
        return 0.0
    c = [0]*256
    for b in blob:
        c[b] += 1
    n = len(blob)
    e = 0.0
    for v in c:
        if v:
            p = v/n
            e -= p * math.log2(p)
    return e
slabs = []
for o in range(0, len(data), 1 << 20):
    slabs.append((o, ent(data[o:o+(1<<20)])))
for o, e in slabs:
    bar = "#" * int(e * 4)
    print(f"  0x{o:08X}  {e:.3f}  {bar}")
