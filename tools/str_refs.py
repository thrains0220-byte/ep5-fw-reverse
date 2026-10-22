#!/usr/bin/env python3
"""批量定位若干函数名字符串的 4 字节代码引用（MN103 `fc <imm32>`）。

用法:
    python str_refs.py --blk <blk.bin> --base 0x402C0000 --names a,b,c
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--names", required=True)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)

    for nm in [s.strip() for s in args.names.split(",") if s.strip()]:
        b = nm.encode()
        # 字符串本体（精确匹配 + NUL 结尾）
        idx = 0
        while True:
            k = d.find(b + b"\x00", idx)
            if k < 0:
                break
            rt = base + k
            pat = struct.pack("<I", rt)
            j = 0
            refs = []
            while True:
                m = d.find(pat, j)
                if m < 0:
                    break
                kind = "code(fc)" if (m >= 2 and d[m - 2] == 0xFC) else "data"
                refs.append((base + m, kind, m))
                j = m + 1
            if refs:
                print("%-34s str@0x%08X" % (nm, rt))
                for a, kind, off in refs:
                    print("      %-8s ref@0x%08X   ctx=%s" % (
                        kind, a, d[max(0, off - 12):off + 8].hex()))
            idx = k + 1
        else:
            pass


if __name__ == "__main__":
    main()
