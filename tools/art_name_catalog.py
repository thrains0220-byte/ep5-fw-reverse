#!/usr/bin/env python3
"""art 函数名目录 ↔ 函数地址表 配对搜索。

背景:
    Olympus 固件在 art 模块里留有一份**函数名目录**（连续 NUL 分隔的字符串），
    例如 art_set_exec / art_set_filter / art_set_filterlist / art_get_filterlist_tbl ...
    若链接器同时保留了**同序的函数地址数组**，则两者按序配对即可得到
    「函数名 → 运行地址」的完整映射（无需执行、无需符号表）。

策略:
    1. 从给定区间抽出目录里的函数名（顺序保持）;
    2. 在整块里搜索长度为 name_count 的 32 位数组，
       其元素全部落在 [code_lo, code_hi) 且 2 字节对齐;
    3. 报告候选表并打印配对结果。

用法:
    python art_name_catalog.py --blk <blk0.bin> --base 0x402C0000 \
        --cat-lo 0x406FA000 --cat-hi 0x406FD000 \
        --code-lo 0x402C0000 --code-hi 0x411B0000
"""
import argparse
import struct


def extract_catalog(d, lo, hi):
    """抽出区间内连续的 NUL 分隔名字（>=4 字符、以字母开头）。"""
    names = []
    i = lo
    while i < hi:
        j = i
        while j < hi and 32 <= d[j] < 127:
            j += 1
        if j > i:
            s = d[i:j].decode("ascii")
            if len(s) >= 4 and s[0].isalpha():
                names.append((i, s))
            i = j + 1
        else:
            i += 1
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--cat-lo", required=True)
    ap.add_argument("--cat-hi", required=True)
    ap.add_argument("--code-lo", default=None)
    ap.add_argument("--code-hi", default=None)
    ap.add_argument("--min-len", type=int, default=4)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)

    clo = int(args.cat_lo, 0) - base
    chi = int(args.cat_hi, 0) - base
    names = extract_catalog(d, clo, chi)
    print("目录区间 0x%08X..0x%08X  内名字 %d 条" % (base + clo, base + chi, len(names)))
    for k, (off, s) in enumerate(names[:12]):
        print("   [%d] 0x%08X  %s" % (k, base + off, s))
    print("   ...")
    for k, (off, s) in enumerate(names[-6:], start=max(0, len(names) - 6)):
        print("   [%d] 0x%08X  %s" % (k, base + off, s))
    print()

    n = len(names)
    if n < 4:
        return

    lo = int(args.code_lo, 0) if args.code_lo else base
    hi = int(args.code_hi, 0) if args.code_hi else base + 0x1000000

    hits = []
    for start in range(0, N - 4 * n, 4):
        ok = True
        for k in range(n):
            v = struct.unpack_from("<I", d, start + 4 * k)[0]
            if not (lo <= v < hi) or (v & 1):
                ok = False
                break
        if ok:
            hits.append(start)
            if len(hits) >= 20:
                break

    print("长度=%d 的候选地址表 %d 张" % (n, len(hits)))
    for st in hits:
        print("  file 0x%08X  rt 0x%08X" % (st, base + st))
        for k, (off, s) in enumerate(names):
            v = struct.unpack_from("<I", d, st + 4 * k)[0]
            print("      %-40s 0x%08X" % (s, v))
        print()


if __name__ == "__main__":
    main()
