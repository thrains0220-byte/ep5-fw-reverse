#!/usr/bin/env python3
"""在固件块中寻找「指向某地址区间的连续指针表」。

用途: 定位 dispatch 表（效果 ID → 处理函数）这类结构。
判据: 连续 >= min_run 个 32 位值都落在 [lo, hi) 内。

（与 `find_ptr_tables.py` 的区别: 后者找的是「指向块 0 内部、且单调递增」的指针数组；
本脚本不要求单调，可指定任意目标区间，也可附加「值互异」约束 —— 见 `find_fn_ptr_arrays.py`。）

用法:
    python find_ptr_ranges.py --blk <blk.bin> --lo 0x406F0000 --hi 0x40700000 --min-run 6
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--lo", required=True)
    ap.add_argument("--hi", required=True)
    ap.add_argument("--min-run", type=int, default=6)
    ap.add_argument("--max-show", type=int, default=40)
    args = ap.parse_args()

    base = int(args.base, 0)
    lo = int(args.lo, 0)
    hi = int(args.hi, 0)
    d = open(args.blk, "rb").read()
    N = len(d)

    run_start = None
    run_len = 0
    runs = []

    def flush():
        nonlocal run_start, run_len
        if run_len >= args.min_run:
            runs.append((run_start, run_len))
        run_start = None
        run_len = 0

    off = 0
    while off + 4 <= N:
        v = struct.unpack_from("<I", d, off)[0]
        if lo <= v < hi:
            if run_start is None:
                run_start = off
            run_len += 1
        else:
            flush()
        off += 4
    flush()

    print("区间 [0x%08X,0x%08X)  连续指针表 (>=%d) 共 %d 张" % (lo, hi, args.min_run, len(runs)))
    shown = 0
    for st, ln in runs:
        if shown >= args.max_show:
            break
        shown += 1
        vals = [struct.unpack_from("<I", d, st + 4 * i)[0] for i in range(min(ln, 24))]
        print("  file 0x%08X rt 0x%08X  len=%d" % (st, base + st, ln))
        print("      " + " ".join("%08X" % v for v in vals))


if __name__ == "__main__":
    main()
