#!/usr/bin/env python3
"""反解「基址寄存器 + 16 位位移」寻址：找出能同时解释多个目标地址的基址。

MN103 的 `mov.l @(disp, base)` 用 16 位有符号位移，
因此一串相邻字符串通常共享同一个 page 基址。
本脚本对每个候选基址（page 对齐）计算位移，在块内搜索该 2 字节位移，
统计每个基址能解释多少个目标地址。

用法:
    python find_addr_base.py --blk <blk.bin> --base 0x402C0000 \
        --targets 0x405ED07B,0x405ECF3D,0x405ED17A,0x405ED188 \
        [--cands 0x405E0000-0x405EE0000] [--min-hits 2]
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--cands", default="0x405E0000-0x405EE0000")
    ap.add_argument("--min-hits", type=int, default=2)
    ap.add_argument("--step", type=lambda x: int(x, 0), default=0x1000)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    d = open(args.blk, "rb").read()
    tgt = [int(x, 0) for x in args.targets.split(",") if x.strip()]
    lo_s, hi_s = args.cands.split("-")
    clo = int(lo_s, 0)
    chi = int(hi_s, 0)

    results = []
    for b in range(clo, chi + 1, args.step):
        hits = []
        for t in tgt:
            disp = t - b
            if not (-0x8000 <= disp <= 0x7FFF):
                continue
            pat = struct.pack("<H", disp & 0xFFFF)
            n = d.count(pat)
            if n:
                hits.append((t, disp, n))
        if len(hits) >= args.min_hits:
            results.append((len(hits), b, hits))

    results.sort(key=lambda r: (-r[0], -sum(h[2] for h in r[2])))
    print("目标 %d 个; 候选基址区间 0x%08X..0x%08X 步长 0x%X" % (
        len(tgt), clo, chi, args.step))
    for nh, b, hits in results[:args.top]:
        print("  基址 0x%08X  解释 %d/%d 个目标" % (b, nh, len(tgt)))
        for t, disp, n in hits:
            print("      0x%08X  disp=0x%04X (%d)  出现 %d 次" % (t, disp & 0xFFFF,
                                                                   disp if disp >= 0 else disp - 0x10000, n))


if __name__ == "__main__":
    main()
