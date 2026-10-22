#!/usr/bin/env python3
"""在固件块内定位一批名字字符串，并打印每个命中点的上下文与周边字符串。

用于判断"名字到底存在哪、是什么布局、怎么被引用"。

用法:
    python find_name_occurrences.py --blk <blk.bin> --names POPART,PASTEL,... [--ctx 48]
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--names", required=True)
    ap.add_argument("--ctx", type=int, default=48)
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)
    names = [s.strip() for s in args.names.split(",") if s.strip()]

    for nm in names:
        b = nm.encode()
        idx = 0
        hits = 0
        print("=" * 96)
        print("NAME %r" % nm)
        while True:
            k = d.find(b, idx)
            if k < 0 or hits >= args.max:
                break
            hits += 1
            # 要求边界合理：前后不是字母数字
            pre = d[k - 1:k]
            post = d[k + len(b):k + len(b) + 1]
            pre_ok = not pre or not (48 <= pre[0] < 58 or 65 <= pre[0] < 91 or 97 <= pre[0] < 123 or pre[0] == 95)
            post_ok = not post or not (48 <= post[0] < 58 or 65 <= post[0] < 91 or 97 <= post[0] < 123 or post[0] == 95)
            lo = max(0, k - args.ctx)
            hi = min(N, k + len(b) + args.ctx)
            ctx = d[lo:hi]
            # 周边可打印串
            tail = d[k + len(b):k + len(b) + 32].split(b"\x00")[0]
            print("  file 0x%08X  rt 0x%08X  boundary=%s%s  tail=%r" % (
                k, base + k, pre_ok, post_ok, tail.decode("ascii", "replace")))
            print("      ctx=%s" % ctx.hex())
            idx = k + 1
        print("  hits=%d\n" % hits)


if __name__ == "__main__":
    main()
