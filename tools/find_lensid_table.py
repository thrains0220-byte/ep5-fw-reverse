#!/usr/bin/env python3
"""按「数据形状」搜索镜头 ID 白名单表。

背景（第 21 轮）:
    社区改机补丁的第二处改动位于「镜头 ID 白名单校验」函数里：
        MOV (A1),D0 / CMP D0,D1 / BEQ  →  表尾哨兵 0xFFFFFFFF ⇒ 判「未识别」
    表项是 4 字节一个的镜头 ID（24 bit 有效），以 0xFFFFFFFF 收尾。
    E-M1 III 的表在运行地址 0x6079E3A9（块 0 数据段）。

    字节指纹跨机型不通用（E-P5 0 命中），但**表的形状**可能通用：
        一串 < 0x01000000 的 u32，紧跟一个 0xFFFFFFFF。

本脚本:
    1. 从参考机型按运行地址取出表并打印；
    2. 在目标块 0 里按上述形状搜索候选表。

用法:
    python tools/find_lensid_table.py --ref <参考块0> --ref-base 0x40800000 \
        --ref-addr 0x6079e3a9 --entries 12 \
        --targets "E-P5=<块0>:<基址>" ...
"""
import argparse
import struct


def u32s(d, off, n):
    return [struct.unpack_from("<I", d, off + 4 * i)[0] for i in range(n)]


def find_tables(d, base, min_entries=3, max_entries=64):
    """扫描形如 [u32 <2^24]* + 0xFFFFFFFF 的表。"""
    hits = []
    n = len(d)
    i = 0
    while i + 4 <= n:
        v = struct.unpack_from("<I", d, i)[0]
        if v >= 0x01000000:
            i += 1
            continue
        # 尝试从这里往后读连续的合法 u32
        j = i
        cnt = 0
        while j + 4 <= n and cnt < max_entries:
            x = struct.unpack_from("<I", d, j)[0]
            if x == 0xFFFFFFFF:
                if cnt >= min_entries:
                    hits.append((i, cnt))
                break
            if x >= 0x01000000:
                break
            j += 4
            cnt += 1
        i += 4
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None)
    ap.add_argument("--ref-base", type=lambda x: int(x, 0), default=0x40800000)
    ap.add_argument("--ref-addr", type=lambda x: int(x, 0), default=0x6079E3A9)
    ap.add_argument("--entries", type=int, default=12)
    ap.add_argument("--targets", nargs="*", default=[],
                    help="label=路径:基址")
    ap.add_argument("--min-entries", type=int, default=4)
    ap.add_argument("--max", type=int, default=20)
    args = ap.parse_args()

    if args.ref:
        d = open(args.ref, "rb").read()
        off = args.ref_addr - args.ref_base
        vals = u32s(d, off, args.entries)
        print("参考表 %s @ 运行地址 0x%08X (文件偏移 0x%08X):"
              % (args.ref, args.ref_addr, off))
        for i, v in enumerate(vals):
            print("   #%-2d  0x%08X" % (i, v))
        raw = d[off:off + 4 * args.entries]
        print("   raw: %s" % raw.hex(" "))
        print()

    for t in args.targets:
        label, _, rest = t.partition("=")
        path, _, b = rest.partition(":")
        base = int(b, 0) if b else 0x402C0000
        d = open(path, "rb").read()
        hits = find_tables(d, base, args.min_entries)
        print("%-16s %d 处候选表（>=%d 项）" % (label, len(hits), args.min_entries))
        for off, cnt in hits[:args.max]:
            vals = u32s(d, off, cnt)
            print("   @0x%08X (off 0x%08X) %d 项: %s" %
                  (base + off, off, cnt,
                   " ".join("%08X" % v for v in vals[:12])))
        print()


if __name__ == "__main__":
    main()
