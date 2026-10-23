#!/usr/bin/env python3
"""在块 0 里找出所有「基址寄存器」候选值（出现在 `fc dc <imm32>` 立即数里，
且落在给定区间内），并统计每个值附近的字符串是否被该基址覆盖。

背景：MN103 的 `mov.l @(disp, base)` 用 16 位有符号位移，
     一段连续字符串通常共享一个 page 基址。
     找出基址后，就能把「字符串 ↔ 代码」连起来（第十四轮 art 字符串 0 引用之谜）。

用法:
    python tools/find_str_base.py --blk <blk0> --lo 0x40710000 --hi 0x4071C000
"""
import argparse
import collections
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--lo", required=True)
    ap.add_argument("--hi", required=True)
    ap.add_argument("--min-cov", type=int, default=0x800,
                    help="基址必须覆盖的字符串区间长度（判定该基址是否够用）")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    lo = int(args.lo, 0)
    hi = int(args.hi, 0)
    d = open(args.blk, "rb").read()

    cnt = collections.Counter()
    first = {}
    i = 0
    while True:
        i = d.find(b"\xfc\xdc", i)
        if i < 0:
            break
        if i + 6 <= len(d):
            v = struct.unpack_from("<I", d, i + 2)[0]
            if lo <= v < hi:
                cnt[v] += 1
                first.setdefault(v, i)
        i += 1

    print("区间 0x%08X..0x%08X  候选基址 %d 个" % (lo, hi, len(cnt)))
    print("%-12s %-8s %-12s %s" % ("基址", "装载次数", "首次偏移", "可覆盖长度(+-32K)"))
    for v, c in cnt.most_common(args.top):
        print("0x%08X  %-8d 0x%08X  0x%08X..0x%08X" % (
            v, c, first[v], v - 0x8000, v + 0x8000))


if __name__ == "__main__":
    main()
