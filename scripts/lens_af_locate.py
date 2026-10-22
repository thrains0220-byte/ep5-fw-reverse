#!/usr/bin/env python3
"""Locate the AF tuning arrays and LENS_INFO handling in E-P5 decoded block 0.

Strategy: the debug-print strings give us a window into the lens-info code.
We locate the string offsets, then look for the data tables referenced near
them, and dump the LENS_INFO field enum in order.
"""
import re
import struct

P = "/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work/decoded/00_0100_402c0020.decoded.bin"
d = open(P, "rb").read()
BASE = 0x402C0000


def sfind(s):
    return [m.start() for m in re.finditer(re.escape(s.encode()), d)]


print("=" * 90)
print("LENS_INFO field enum (from debug print labels)")
print("=" * 90)
pat = re.compile(rb"\s*:\s*(\d{3})\s*:\s*(LENS_INFO_[A-Z0-9_]+)")
fields = []
for m in pat.finditer(d):
    fields.append((int(m.group(1)), m.group(2).decode(), m.start()))
# keep the first contiguous run
fields.sort()
run = []
for f in fields:
    if run and f[0] != run[-1][0] + 1:
        break
    run.append(f)
for n, name, off in run:
    print(f"  {n:>3}  {name:<30} str@0x{BASE+off:08X}")
print(f"  -> {len(run)} consecutive fields")

print("\n" + "=" * 90)
print("AF tuning array labels (vh/vl/vv/hk x af_c/af_u_d/af_l_r)")
print("=" * 90)
afpat = re.compile(rb"([a-z]{2})\.af_([a-z_]+)\s+\[%d\]")
af = sorted(set(m.group(0).decode() for m in afpat.finditer(d)))
print(f"  {len(af)} distinct labels: {af}")

print("\n" + "=" * 90)
print("All 'af_*' / lens tuning related string labels in a window")
print("=" * 90)
afpat2 = re.compile(rb"[ \t]*([a-z]{2,3}\.af_[a-z_]+|af_[a-z_]+|AF_[A-Z_]+|[a-z_]*af[a-z_]*)\s*(%[a-z0-9]*)?")
seen = {}
for m in afpat2.finditer(d):
    s = m.group(1).decode()
    if len(s) >= 3 and s not in seen:
        seen[s] = m.start()
print(f"  {len(seen)} distinct af-ish tokens; sample:")
for s, off in sorted(seen.items(), key=lambda kv: kv[1])[:60]:
    print(f"    0x{BASE+off:08X}  {s}")

print("\n" + "=" * 90)
print("Strings referencing makernote / maker id / SET_MAKER_ID")
print("=" * 90)
for pat in [rb"SET_MAKER_ID", rb"MAKERNOTE", rb"maker", rb"maker_id", rb"MAKER"]:
    hits = sfind(pat.decode())
    print(f"  {pat.decode()}: n={len(hits)}")
    for h in hits[:10]:
        s = d[max(0, h-40):h+60]
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in s)
        print(f"     0x{BASE+h:08X}: ...{txt}...")

print("\n" + "=" * 90)
print("Af_Data / af_data_pos neighborhood (data window around the label)")
print("=" * 90)
hits = sfind("af_data_pos[%d]  = ")
for h in hits:
    lo = max(0, h - 0x300)
    seg = d[lo:h + 0x200]
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in seg)
    print(f"\n  --- around 0x{BASE+h:08X} ---")
    for i in range(0, len(seg), 80):
        chunk = txt[i:i+80]
        print(f"    0x{BASE+lo+i:08X} {chunk}")
