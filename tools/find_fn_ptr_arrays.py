#!/usr/bin/env python3
"""在固件块中搜索「一组互异且彼此接近的代码地址」数组 —— 候选函数指针表。

约束:
  - 长度 == n
  - 所有值互不相同
  - 所有值 2 字节对齐且 bit0 = 1（MN103 函数地址）
  - max-min <= --span

用法:
    python find_fn_ptr_arrays.py --blk <blk.bin> --n 21 --span 0x40000 [--lo 0x402C0000] [--hi 0x411B0000]
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--span", type=lambda x: int(x, 0), default=0x40000)
    ap.add_argument("--lo", default=None)
    ap.add_argument("--hi", default=None)
    ap.add_argument("--max-show", type=int, default=10)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)
    lo = int(args.lo, 0) if args.lo else base
    hi = int(args.hi, 0) if args.hi else base + 0x1000000
    n = args.n

    found = []
    for start in range(0, N - 4 * n, 4):
        vals = [struct.unpack_from("<I", d, start + 4 * k)[0] for k in range(n)]
        ok = True
        s = set()
        for v in vals:
            if not (lo <= v < hi) or not (v & 1) or v in s:
                ok = False
                break
            s.add(v)
        if not ok:
            continue
        if max(vals) - min(vals) > args.span:
            continue
        found.append((start, vals))
        if len(found) >= args.max_show:
            break

    print("n=%d span=0x%X  候选 %d 组" % (n, args.span, len(found)))
    for st, vals in found:
        print("  file 0x%08X  rt 0x%08X" % (st, base + st))
        print("      " + " ".join("%08X" % v for v in vals))


if __name__ == "__main__":
    main()
