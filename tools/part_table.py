#!/usr/bin/env python3
"""解析固件分区头 (base, span) 与其后的 (end_addr, size) 子区段目录表。
用法: part_table.py <decoded 分区 .bin>...
"""
import struct, sys, os

def parse(path, base_expect=None):
    d = open(path, 'rb').read()
    base, span = struct.unpack_from('<II', d, 0)
    print(f"== {os.path.basename(path)}  size={len(d)} (0x{len(d):X})")
    print(f"   header: base=0x{base:08X} span=0x{span:X}  base+span=0x{base+span:08X}")
    off = 16
    ents = []
    while off + 8 <= len(d):
        a, l = struct.unpack_from('<II', d, off)
        if a == 0 and l == 0:
            off += 8
            continue
        ents.append((a, l, off))
        off += 8
    print(f"   目录条目数={len(ents)}  目录结束于 0x{off:X}")
    tot = sum(l for _, l, _ in ents)
    print(f"   条目 size 合计=0x{tot:X}   文件剩余=0x{len(d)-off:X}  差={len(d)-off-tot}")
    for i, (a, l, o) in enumerate(ents[:6]):
        print(f"   [{i}] end=0x{a:08X} size=0x{l:X} start=0x{a-l:08X}")
    if len(ents) > 6:
        print("   ...")
        for i, (a, l, o) in list(enumerate(ents))[-3:]:
            print(f"   [{i}] end=0x{a:08X} size=0x{l:X} start=0x{a-l:08X}")
    return base, span, ents, d, off

for p in sys.argv[1:]:
    parse(p)
    print()
