#!/usr/bin/env python3
"""按运行时地址区间列出固件块内的字符串（含偏移/对齐信息）。

用法:
    python strings_in_range.py --blk <blk.bin> --base 0x402C0000 \
        --lo 0x4069CD00 --hi 0x4069D300 [--minlen 3]
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--lo", required=True)
    ap.add_argument("--hi", required=True)
    ap.add_argument("--minlen", type=int, default=3)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    lo = int(args.lo, 0) - base
    hi = int(args.hi, 0) - base
    if lo < 0 or hi > len(d) or hi <= lo:
        print("[bad range]")
        return

    i = lo
    while i < hi:
        j = i
        while j < hi and 32 <= d[j] < 127:
            j += 1
        if j - i >= args.minlen:
            print("0x%08X  +0x%04X  len=%-3d %r" % (
                base + i, i - lo, j - i, d[i:j].decode("ascii")))
        while j < hi and not (32 <= d[j] < 127):
            j += 1
        i = j


if __name__ == "__main__":
    main()
