#!/usr/bin/env python3
"""枚举两个固件块之间的所有差异区间（连续不同字节聚成区间）。

用法:
    python block0_diffranges.py --a <pre.decoded.bin> --b <post.decoded.bin>
                               [--base 0x402C0000] [--min-len 1] [--max-len 4096]
                               [--context 16]
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--min-len", type=int, default=1)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--context", type=int, default=16)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    base = int(args.base, 0)
    A = open(args.a, "rb").read()
    B = open(args.b, "rb").read()
    n = min(len(A), len(B))
    print("A %s  %d B" % (args.a, len(A)))
    print("B %s  %d B" % (args.b, len(B)))
    if len(A) != len(B):
        print("[!] 长度不同，只比较前 %d B" % n)
    print()

    ranges = []
    i = 0
    while i < n:
        if A[i] != B[i]:
            j = i
            while j < n and A[j] != B[j]:
                j += 1
            ranges.append((i, j - i))
            i = j
        else:
            i += 1

    total = sum(r[1] for r in ranges)
    print("差异区间 %d 段, 不同字节 %d 个 (%.4f%%)" % (
        len(ranges), total, 100.0 * total / n))
    print()
    print("%-12s %-8s %-8s %s" % ("rt", "len", "file", "bytes"))
    for off, ln in ranges:
        if ln > args.max_len:
            print("0x%08X  %-8d 0x%08X  (超长, 跳过)" % (base + off, ln, off))
            continue
        if ln < args.min_len:
            continue
        a = A[off:off + ln]
        b = B[off:off + ln]
        print("0x%08X  %-8d 0x%08X  A=%s  B=%s" % (
            base + off, ln, off, a.hex(" "), b.hex(" ")))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"a": args.a, "b": args.b, "base": "0x%08X" % base,
                       "ranges": [{"rt": "0x%08X" % (base + o), "file": "0x%08X" % o,
                                   "len": l, "a": A[o:o + l].hex(),
                                   "b": B[o:o + l].hex()} for o, l in ranges]},
                      f, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
