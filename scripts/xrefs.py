#!/usr/bin/env python3
"""Find code references (xrefs) to strings/data in E-P5 decoded block 0.

MN103 encodes a 32-bit immediate inline: `fc <reg> <imm32 LE>` (objdump:
"mov <imm>,d0"). We therefore look for the LE32 address of the target.
"""
import json
import re
import struct
import sys

BASE = 0x402C0000
BLOCK = "/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work/decoded/00_0100_402c0020.decoded.bin"
d = open(BLOCK, "rb").read()


def xrefs(addr, require_prefix=True):
    """Return [(offset, prefix_bytes)] where addr is loaded as a 32-bit immediate."""
    p = struct.pack("<I", addr)
    out = []
    for m in re.finditer(re.escape(p), d):
        o = m.start()
        if require_prefix and o < 2:
            continue
        pref = d[o-2:o]
        # mn103 `mov imm32,Dn` == fc <lo nibble selects reg> ; fc cc = d0
        if require_prefix and pref[0] != 0xFC:
            continue
        out.append((o, pref.hex()))
    return out


def refs_to_any(addrs, label):
    print(f"\n--- {label} ---")
    for a in addrs:
        x = xrefs(a)
        if x:
            for o, pref in x[:6]:
                print(f"   target 0x{a:08X} <- code 0x{BASE+o-2:08X} (file 0x{o-2:X}) prefix={pref}")
    return


targets = sys.argv[1:] or [
    "LENS_INFO_MAKERNOTE", "af_data_pos", "LENS_INFO_AF_CON",
    "LENS_INFO_MAKERNOTE_A", "maker_code", "LENS_INFO_STATE",
]

rows = [json.loads(l) for l in open("/home/sanyu/Projects/work/E-P5_固件_1.8/rea_work/decoded/strings.jsonl")]
b0 = [r for r in rows if r["block"] == 0]

for t in targets:
    hits = [r for r in b0 if t in r["text"]]
    print("=" * 88)
    print(f"TARGET {t!r}: {len(hits)} occurrence(s)")
    for r in hits[:8]:
        off = int(r["decoded_offset"], 16)
        rt = BASE + off
        x = xrefs(rt)
        tag = ", ".join(f"0x{BASE+o-2:08X}" for o, _ in x[:6]) or "NO DIRECT XREF"
        print(f"   str@file 0x{off:08X} runtime 0x{rt:08X}  text={r['text'][:52]!r}")
        print(f"      xrefs: {tag}")
