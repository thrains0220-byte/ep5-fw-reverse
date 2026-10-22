#!/usr/bin/env python3
"""解析 E-P5 块 0 中的定长记录表（记录首字段 u32 = 自身长度）。

已定位两张表（E-P5 v1.6 块 0, 基址 0x402C0000）:
    表 A  首记录 0x40E2F004  stride 0x58  43 条
    表 B  首记录 0x40E2F6E8  stride 0x5C  26 条

用法:
    python parse_filter_table.py --blk <blk0.bin> --at 0xB6F6E8 --stride 0x5C --count 26
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--at", required=True)
    ap.add_argument("--stride", type=lambda x: int(x, 0), default=0x5C)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--u32", action="store_true", help="以 u32 列表打印每条记录")
    ap.add_argument("--u16", action="store_true", help="以 u16 列表打印每条记录")
    ap.add_argument("--nocheck", action="store_true", help="不因长度标记不符而中断")
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    start = int(args.at, 0)
    st = args.stride

    print("表首 @file 0x%08X  rt 0x%08X  stride=0x%X" % (start, base + start, st))
    for i in range(args.count):
        off = start + i * st
        if off + st > len(d):
            break
        size = struct.unpack_from("<I", d, off)[0]
        if size != st and not args.nocheck:
            print("  #%d 记录长度标记 = %d (期望 0x%X) —— 表结束" % (i, size, st))
            break
        if args.u32:
            vals = [struct.unpack_from("<I", d, off + k * 4)[0] for k in range(st // 4)]
            print("  #%-3d rt=0x%08X  %s" % (i, base + off,
                  " ".join("%08X" % v for v in vals)))
        elif args.u16:
            vals = [struct.unpack_from("<H", d, off + k * 2)[0] for k in range(st // 2)]
            print("  #%-3d rt=0x%08X  %s" % (i, base + off,
                  " ".join("%04X" % v for v in vals)))
        else:
            print("  #%-3d rt=0x%08X  %s" % (i, base + off,
                  d[off:off + st].hex()))


if __name__ == "__main__":
    main()
