#!/usr/bin/env python3
"""在 `kind 0x106` 资源容器分区里定位并解析「40 条 (运行地址, 大小) 资源目录」。

背景（第十六轮）:
    新版机型（E-M1 v4.6 / E-M10 II / E-P7 / E-PM1）的 `kind 0x106` 分区内部
    是一个**运行映像**，其首块 payload 开头带一张 40 条的资源目录：
        40 × 16 字节 { u32 运行地址, u32 大小, u32 0, u32 0 }
    目录条目指向若干资源（图像、数据表、JPEG、LUT 类数据表……）。
    E-P5 v1.8 的 0x106 只有 blob、没有目录（见 round16 §6 的未解项）。

本脚本:
    1. 扫描 0x106 分区，定位符合「40 条、地址递增、size 合理、覆盖连续区间」
       特征的资源目录；
    2. 打印每条资源的运行地址 / 大小 / 内容画像（熵、魔数、可打印比）；
    3. 标出「数值表」特征条目（候选 LUT）。

用法:
    python tools/blk106_resdir.py <02_0106_*.decoded.bin> [--base 0x43160000]
"""
import argparse
import collections
import math
import struct


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def classify(b):
    kinds = []
    if b[:2] == b"\xff\xd8":
        kinds.append("JPEG")
    if b[:4] == b"\x89PNG":
        kinds.append("PNG")
    if b[:4] in (b"OTTO", b"true", b"ttcf", b"wOFF", b"\x00\x01\x00\x00"):
        kinds.append("字体/表")
    pr = sum(1 for x in b if 32 <= x < 127 or x in (9, 10, 13)) / max(1, len(b))
    if pr > 0.7:
        kinds.append("文本")
    # 数值表启发式
    if len(b) >= 512:
        vals = struct.unpack_from("<%dH" % (len(b) // 2), b)
        small = sum(1 for v in vals if v <= 255) / len(vals)
        if small > 0.95:
            kinds.append("u16 数值表")
        c = collections.Counter(struct.unpack_from("<%dI" % (len(b) // 4), b))
        if c.most_common(1)[0][1] > len(b) / 4 / 30:
            kinds.append("定长重复项")
    return kinds, pr


def find_dirs(d, base, count=40):
    """找符合特征的 40 条目录。"""
    hits = []
    N = len(d)
    for off in range(0, N - count * 16, 4):
        recs = []
        ok = True
        prev_end = None
        for k in range(count):
            a, s, z1, z2 = struct.unpack_from("<4I", d, off + k * 16)
            if z1 or z2 or s == 0 or s > 4 * 1024 * 1024:
                ok = False
                break
            if not (base <= a < base + 0x2000000):
                ok = False
                break
            if prev_end is not None and a < prev_end:
                ok = False
                break
            prev_end = a + s
            recs.append((a, s))
        if ok and len(recs) == count:
            hits.append((off, recs))
            if len(hits) > 8:
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--base", default=None, help="该分区的运行基址（默认自动推断）")
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--code", default=None,
                    help="代码块（块 0）路径；给出后反查每条资源是否被代码引用")
    ap.add_argument("--code-base", default="0x40300000")
    args = ap.parse_args()

    d = open(args.path, "rb").read()
    print("文件 %s  %d B (0x%X)" % (args.path, len(d), len(d)))

    base = int(args.base, 0) if args.base else None
    if base is None:
        # 分区头：header base（[8:12] 是地址？）—— 用出现的最小地址反推
        cand = [struct.unpack_from("<I", d, i)[0]
                for i in range(0, min(len(d), 0x100), 4)]
        cand = [c for c in cand if 0x40000000 < c < 0x50000000]
        base = (min(cand) & ~0xFFFF) if cand else 0x43000000
    print("推断基址 0x%08X\n" % base)

    hits = find_dirs(d, base, args.count)
    if not hits:
        # 放宽：地址范围放宽
        hits = find_dirs(d, base - 0x2000000, args.count)
    if not hits:
        print("未找到 %d 条资源目录" % args.count)
        return

    code = None
    cbase = int(args.code_base, 0)
    if args.code:
        code = open(args.code, "rb").read()
        print("代码块 %s  %d B  base=0x%08X\n" % (args.code, len(code), cbase))

    for off, recs in hits:
        print("=== 候选目录 @ file 0x%08X ===" % off)
        print("%-4s %-12s %-10s %-6s %-6s %s" % (
            "#", "运行地址", "大小", "熵", "打印%", "内容"))
        span_lo = min(a for a, _ in recs)
        span_hi = max(a + s for a, s in recs)
        for i, (a, s) in enumerate(recs):
            so = a - base
            b = d[so:so + s] if 0 <= so and so + s <= len(d) else b""
            kinds, pr = classify(b)
            ref = ""
            if code is not None:
                pat = struct.pack("<I", a)
                hits_n = code.count(pat)
                # 也查「页基址 + 位移」形式
                ref = "  块0引用×%d" % hits_n if hits_n else ""
                if not hits_n:
                    # 查同页其它偏移（base+disp16）
                    for cand in (a & ~0xFFFF, a & ~0xFFF):
                        pass
            print("%-4d 0x%08X %-10d %-6.2f %-5.0f%% %-22s%s" % (
                i, a, s, entropy(b), pr * 100, ", ".join(kinds), ref))
        print("  覆盖区间 0x%08X..0x%08X (%.1f KB)" % (
            span_lo, span_hi, (span_hi - span_lo) / 1024.0))
        print()


if __name__ == "__main__":
    main()
