#!/usr/bin/env python3
"""递归解析固件内层「运行映像」容器：块头（地址/大小/kind/版本/[24:28]时间戳）与明文 payload。
用法: parse_nested.py <decoded 分区 .bin>...
"""
import struct, sys, os, hashlib

def blocks(data, start, end, tag):
    print(f"-- {tag}: 扫描 0x{start:X}..0x{end:X}")
    off = start
    out = []
    while off + 32 <= end:
        hdr = data[off:off+32]
        if hdr[:2] not in (b"OE", b"OM"):
            break
        addr = struct.unpack_from("<I", hdr, 8)[0]
        size = struct.unpack_from("<I", hdr, 12)[0]
        kind = struct.unpack_from("<H", hdr, 20)[0]
        ver = struct.unpack_from("<H", hdr, 16)[0]
        model = hdr[2:4].hex()
        pstart = off + 32
        pend = pstart + size
        out.append((off, addr, size, kind, ver, model, pstart, pend))
        off = pend + 16
    return out

for path in sys.argv[1:]:
    d = open(path, 'rb').read()
    base, span = struct.unpack_from('<II', d, 0)
    print(f"\n===== {os.path.basename(os.path.dirname(os.path.dirname(path)))}")
    print(f"  分区文件 {len(d)} B  header base=0x{base:08X} span=0x{span:X}")
    bs = blocks(d, 0x10, len(d), "顶层")
    for o, a, s, k, v, m, ps, pe in bs:
        sha = hashlib.sha256(d[ps:pe]).hexdigest()[:12]
        print(f"   块 @0x{o:06X} addr=0x{a:08X} size=0x{s:X} kind=0x{k:04X} ver=0x{v:04X} model={m} payload=0x{ps:X}..0x{pe:X} sha={sha}")
    # 若顶层只有一个"嵌套容器"（头为 OE/OM），再往里解一层
    if len(bs) == 1:
        o, a, s, k, v, m, ps, pe = bs[0]
        print(f"  -> 该块自身是一个容器，递归解析其 payload")
        inner = blocks(d, ps, pe, "内层")
        for o2, a2, s2, k2, v2, m2, ps2, pe2 in inner:
            sha = hashlib.sha256(d[ps2:pe2]).hexdigest()[:12]
            mx = max(d[ps2:pe2]) if pe2 > ps2 else 0
            print(f"     块 @0x{o2:06X} addr=0x{a2:08X} size=0x{s2:X} kind=0x{k2:04X} ver=0x{v2:04X} model={m2} payload=0x{ps2:X}..0x{pe2:X} maxbyte=0x{mx:02X} sha={sha}")
