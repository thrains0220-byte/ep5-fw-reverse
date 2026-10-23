#!/usr/bin/env python3
"""AF 哑引用机制：把 `fcs_*` 字符串族与块 0 里的**函数入口表**对上。

背景（第十七轮 → 第二十轮）:
    `fcs_lens_mfts_move_lens_ofset_target` 这类字符串在固件内**没有 u32 指针引用**，
    疑似「哑元数据」—— 真正的绑定是「函数入口 + 调用点」，不是数据表里的指针。

本脚本:
    1. 列出块 0 里全部 `fcs_*` / `fcs_lens_*` 字符串（偏移 + 名字 + 上下文）；
    2. 在块 0 里找**函数入口表候选**：连续 ≥N 个 u32 元素全部落在块 0 地址区间、
       2 字节对齐、且相邻差值在合理范围（函数体长度量级）；
    3. 把入口表与字符串数量/顺序做比对，找出「名字 ↔ 入口」的可能对应。

用法:
    python tools/find_lens_dumb_refs.py --blk0 <块0> [--base 0x402C0000] [--min-run 4]
"""
import argparse
import collections
import re
import struct


def printable_spans(d, minlen=4):
    out = []
    i = 0
    N = len(d)
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= minlen:
            out.append((i, d[i:j].decode("ascii")))
        i = j + 1 if j > i else i + 1
    return out


def find_ptr_runs(d, base, lo, hi, min_run, max_stride=0x8000):
    """找连续的 u32 函数入口表候选。"""
    runs = []
    i = 0
    N = len(d)
    while i + 4 * min_run <= N:
        vals = []
        j = i
        ok = True
        while j + 4 <= N and len(vals) < 4096:
            v = struct.unpack_from("<I", d, j)[0]
            if not (lo <= v < hi) or (v & 1) == 0:
                ok = False
                break
            if vals and not (0 < v - vals[-1] <= max_stride):
                ok = False
                break
            vals.append(v)
            j += 4
        if ok and len(vals) >= min_run:
            runs.append((i, vals))
            i = j
        else:
            i += 4
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--lo", default=None, help="块 0 地址区间下界（默认 base）")
    ap.add_argument("--hi", default=None, help="块 0 地址区间上界（默认 base+size）")
    ap.add_argument("--min-run", type=int, default=4)
    ap.add_argument("--prefix", default="fcs_")
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    lo = int(args.lo, 0) if args.lo else base
    hi = int(args.hi, 0) if args.hi else base + len(d)

    spans = printable_spans(d)
    fcs = [(off, s) for off, s in spans if s.startswith(args.prefix)]
    print("块 0 %s  (%d B)" % (args.blk0, len(d)))
    print("`%s*` 字符串 %d 条\n" % (args.prefix, len(fcs)))
    for off, s in fcs:
        print("  0x%08X  %s" % (base + off, s))
    print()

    # 字符串在块内的分布（判断它们是否集中在一个"哑元数据区"）
    if fcs:
        offs = [base + o for o, _ in fcs]
        print("字符串地址范围 0x%08X .. 0x%08X" % (min(offs), max(offs)))
        gaps = collections.Counter()
        for a, b in zip(offs, offs[1:]):
            gaps[b - a] += 1
        print("相邻间距分布 (前 8): %s" % gaps.most_common(8))
        print()

    runs = find_ptr_runs(d, base, lo, hi, args.min_run)
    print("函数入口表候选 (>=%d 项, 落在 0x%08X..0x%08X): %d 张"
          % (args.min_run, lo, hi, len(runs)))
    for off, vals in sorted(runs, key=lambda x: -len(x[1]))[:15]:
        print("  @0x%08X  %d 项  首=0x%08X  末=0x%08X" % (
            base + off, len(vals), vals[0], vals[-1]))
    print()
    print("提示：若某张入口表的项数与 `fcs_*` 字符串条数相同或接近，")
    print("      且两者地址顺序单调同向，即为「哑元数据 ↔ 函数入口」绑定的候选。")


if __name__ == "__main__":
    main()
