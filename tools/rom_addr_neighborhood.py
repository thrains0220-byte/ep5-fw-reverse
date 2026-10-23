#!/usr/bin/env python3
"""mask ROM 地址窗口普查：某段 ROM 地址区间内，哪些地址被块 0 的代码引用。

用途（第十八/十九轮）:
    E-P5 的菜单描述符在 `0x7E452BDC` / `0x7E452BE4` 两张。
    要判断「录像 10 项」的清单是否也存在于 E-P5 自己的 ROM 地址空间，
    只需看 **同一族相邻地址**（0x7E452Bxx 段）里还有哪些地址被引用、
    被多少处引用 —— 引用的簇往往就是同一张表的多个变体。

用法:
    python tools/rom_addr_neighborhood.py --blk0 <块0> --center 0x7E452BDC --span 0x200
"""
import argparse
import collections
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--center", required=True)
    ap.add_argument("--span", type=lambda x: int(x, 0), default=0x200)
    ap.add_argument("--label", default="")
    ap.add_argument("--json", default=None)
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    c = int(args.center, 0)
    lo = c - args.span
    hi = c + args.span
    d = open(args.blk0, "rb").read()

    hits = collections.defaultdict(list)
    i = 0
    while True:
        i = d.find(b"\xfc\xdc", i)
        if i < 0:
            break
        if i + 6 <= len(d):
            v = struct.unpack_from("<I", d, i + 2)[0]
            if lo <= v < hi:
                hits[v].append(i)
        i += 1

    print("块 0 %s" % (args.label or args.blk0))
    print("窗口 0x%08X .. 0x%08X  被引用的 ROM 地址 %d 个\n" % (lo, hi, len(hits)))
    print("%-12s %-8s %-10s %s" % ("ROM 地址", "引用数", "首次偏移", "相邻地址"))
    for v in sorted(hits):
        firsts = hits[v][0]
        near = ""
        for w in sorted(hits):
            if w != v and abs(w - v) <= 0x10:
                near += " %s" % ("0x%08X" % w)
        print("0x%08X  %-8d 0x%08X  %s" % (v, len(hits[v]), firsts, near[:60]))

    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"center": "0x%08X" % c, "span": args.span,
                       "window": ["0x%08X" % lo, "0x%08X" % hi],
                       "addresses": {"0x%08X" % v: len(hits[v]) for v in sorted(hits)}},
                      f, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
