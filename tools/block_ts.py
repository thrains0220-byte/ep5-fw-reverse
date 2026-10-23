#!/usr/bin/env python3
"""提取容器各层块头 [24:28] 字段并按 UTC 打印，检验其是否为 Unix 构建时间戳。
用法: block_ts.py <.BIN 或 decoded 分区 .bin>...
"""
import struct, sys, os, datetime, glob

def show(tag, off, hdr, size):
    ts = struct.unpack_from('<I', hdr, 24)[0]
    cks = struct.unpack_from('<I', hdr, 28)[0]
    try:
        s = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        s = '-'
    a = struct.unpack_from('<I', hdr, 8)[0]
    kind = struct.unpack_from('<H', hdr, 20)[0]
    ver = struct.unpack_from('<H', hdr, 16)[0]
    print(f"  {tag} @0x{off:06X} addr=0x{a:08X} size=0x{size:>8X} kind=0x{kind:04X} ver=0x{ver:04X} "
          f"[24:28]=0x{ts:08X} ({s})  [28:32]=0x{cks:08X}")
    return ts

def walk(d, start, end, depth, label):
    off = start
    out = []
    while off + 32 <= end:
        hdr = d[off:off+32]
        if hdr[:2] not in (b'OE', b'OM'):
            break
        size = struct.unpack_from('<I', hdr, 12)[0]
        if size == 0 or size % 16:
            break
        ps = off + 32
        pe = ps + size
        if pe + 32 > end:
            break
        tr = d[pe:pe+32]
        out.append((off, hdr, size, tr))
        off = pe + 32
    print(f"\n{label} —— {len(out)} 个块")
    for o, h, s, tr in out:
        show('块', o, h, s)
    return out

for path in sys.argv[1:]:
    print(f"\n########## {path}")
    d = open(path, 'rb').read()
    # 顶层（可能本身就是嵌套格式）
    blocks = walk(d, 0, len(d), 0, '顶层容器')
    for o, h, s, tr in blocks[:1]:
        if h[24:28] == 0:
            continue
    # 若块内含嵌套容器
    for o, h, s, tr in blocks:
        ps = o + 32
        i = d.find(b'OE', ps, ps + s)
        if i >= 0:
            print("\n  ↳ 该块内含嵌套容器：")
            walk(d, i, ps + s, 1, f'嵌套(块 @0x{o:X})')
            break
