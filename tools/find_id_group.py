#!/usr/bin/env python3
"""在固件块中寻找「一组 u16 资源 ID 出现在同一小窗口内」的菜单表。

用法:
    python find_id_group.py --blk <blk.bin> --base 0x402C0000 \
        --ids A03F,A040,A041,A042,A043,A044,A045,A046,A047,A048 --window 512
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--ids", required=True, help="逗号分隔，如 A03F,A040")
    ap.add_argument("--window", type=int, default=512)
    ap.add_argument("--max-show", type=int, default=10)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)
    want = [int(x.strip().replace("0x", "").replace("0X", ""), 16)
            for x in args.ids.split(",") if x.strip()]
    pats = {v: struct.pack("<H", v) for v in want}
    pats_be = {v: struct.pack(">H", v) for v in want}

    hits = []
    for start in range(0, N - args.window, 4):
        win = d[start:start + args.window]
        got = set()
        for v, p in pats.items():
            if p in win:
                got.add(v)
        if len(got) == len(want):
            hits.append((start, "LE"))
            if len(hits) >= args.max_show:
                break
    if not hits:
        for start in range(0, N - args.window, 4):
            win = d[start:start + args.window]
            got = set()
            for v, p in pats_be.items():
                if p in win:
                    got.add(v)
            if len(got) == len(want):
                hits.append((start, "BE"))
                if len(hits) >= args.max_show:
                    break

    print("目标 %d 个 ID: %s" % (len(want), ", ".join("0x%04X" % v for v in want)))
    print("窗口 %d B 内全部出现的候选位置: %d" % (args.window, len(hits)))
    for st, endian in hits:
        print("  file 0x%08X  rt 0x%08X  (%s)" % (st, base + st, endian))
        win = d[st:st + args.window]
        for v in want:
            p = pats[v]
            i = win.find(p)
            if i >= 0:
                print("      0x%04X @ win+0x%03X" % (v, i))


if __name__ == "__main__":
    main()
