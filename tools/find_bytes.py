#!/usr/bin/env python3
"""在固件块中搜索给定的字节序列（十六进制字符串），报告全部命中偏移。

用法:
    python find_bytes.py --blk <blk.bin> [--base 0x402C0000] --hex "3f a0 40 a0"
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--hex", required=True, help="十六进制字节，空格或逗号分隔")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    base = int(args.base, 0)
    pat = bytes(int(x, 16) for x in args.hex.replace(",", " ").split())
    d = open(args.blk, "rb").read()
    print("pattern len=%d  %s" % (len(pat), pat.hex()))
    i = 0
    n = 0
    while n < args.limit:
        j = d.find(pat, i)
        if j < 0:
            break
        n += 1
        ctx = d[max(0, j - 16):j + len(pat) + 16]
        print("  file 0x%08X  rt 0x%08X   ctx=%s" % (j, base + j, ctx.hex()))
        i = j + 1
    if n == 0:
        print("  (无命中)")


if __name__ == "__main__":
    main()
