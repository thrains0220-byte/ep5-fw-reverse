#!/usr/bin/env python3
"""解析 kind 0x101/0x104 分区的 (end_addr,size) 子区段目录，并检查是否覆盖指定目标地址。
用法: parse_dir.py <decoded 分区 .bin>...
"""
import struct, sys, os

TARGETS = {
    0x43DA0400: '分区2 六比特数据区起点 (E-P5 1.8)',
    0x43DA0020: '分区2 payload 起点 (E-P5 1.8)',
    0x43DA0000: '分区2 block 头 (E-P5 1.8)',
}

def parse_dir(path, label):
    d = open(path, 'rb').read()
    print(f"== {label}: {os.path.basename(path)}  size=0x{len(d):X}")
    hdr = struct.unpack_from('<II', d, 0)
    print(f"   头部 u32: 0x{hdr[0]:08X}  0x{hdr[1]:08X}")
    off = 16
    ents = []
    while off + 8 <= len(d):
        a, l = struct.unpack_from('<II', d, off)
        if not (0x40000000 <= a < 0x60000000) or not (0 < l <= 0x4000000):
            break
        ents.append((a, l, off))
        off += 8
    print(f"   目录条目 {len(ents)} 条，结束于 0x{off:X}（其后为数据区）")
    if ents:
        print(f"   首条 end=0x{ents[0][0]:08X} size=0x{ents[0][1]:X}")
        print(f"   末条 end=0x{ents[-1][0]:08X} size=0x{ents[-1][1]:X}")
    tot = sum(l for _, l, _ in ents)
    print(f"   size 合计=0x{tot:X}；数据区实际 0x{len(d)-off:X}")
    for t, desc in TARGETS.items():
        hits = [(a, l, o) for a, l, o in ents if a - l <= t < a]
        if hits:
            for a, l, o in hits:
                print(f"   ★ 命中 {desc} @0x{t:08X}: 目录项 end=0x{a:08X} size=0x{l:X} (表内偏移 0x{o:X})")
        else:
            print(f"   ✗ 未覆盖 {desc} @0x{t:08X}")
    # 目录里出现的所有分区起始（start = end - size）
    starts = sorted({a - l for a, l, _ in ents})
    print(f"   子区段起点数={len(starts)}，前 8: {', '.join('0x%08X'%s for s in starts[:8])}")
    return ents

for p in sys.argv[1:]:
    parse_dir(p, '目录')
    print()
