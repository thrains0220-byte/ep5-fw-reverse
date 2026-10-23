#!/usr/bin/env python3
"""块 1 资源分区内容分类器 —— 回答「艺术滤镜的 LUT / 参数表在不在块 1 里」。

背景（第十四轮结论）:
    艺术滤镜的 **像素算法**、**菜单描述符**、**调校参数**都被定位在机身 mask ROM
    （0x7Exxxxxx），而 mask ROM 映像**不由 .BIN 承载**（第十七轮实测）。
    ⇒ 唯一还能在 .BIN 内改动的「滤镜数据」候选，就是**块 1 里的资源分区**。

本脚本:
    1. 解析块 1 头部 (ptr, size) 资源表（E-P5 v1.8 为 70 项）；
    2. 对每一项做内容画像：
         - 可打印 ASCII 比例、UTF-16LE 字符串条数、字节熵
         - 是否 JPEG/PNG/字体等已知魔数
         - 是否「数值表」特征（小值分布集中 / 单调斜坡 / 重复行）
         - 是否命中 art / filter / tone / lut / curve / gamma / color 等关键词
    3. 输出可疑的「艺术滤镜数据表」候选。

用法:
    python tools/block1_resource_classify.py [block1.bin] [base] [--json out.json]
"""
import argparse
import collections
import json
import math
import re
import struct

KEYWORDS = [
    b"art", b"ART", b"filter", b"FILTER", b"tone", b"TONE", b"lut", b"LUT",
    b"curve", b"gamma", b"GAMMA", b"color", b"COLOR", b"colour", b"sepia",
    b"SEPIA", b"mono", b"grain", b"GRAIN", b"effect", b"EFFECT", b"colortone",
    b"colortone", b"picture", b"expose",
]


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def printable_ratio(b):
    if not b:
        return 0.0
    return sum(1 for x in b if 32 <= x < 127 or x in (9, 10, 13)) / len(b)


def utf16_strings(b, minlen=4):
    n = 0
    i = 0
    L = len(b)
    while i + 1 < L:
        if 32 <= b[i] < 127 and b[i + 1] == 0:
            j = i + 2
            while j + 1 < L and 32 <= b[j] < 127 and b[j + 1] == 0:
                j += 2
            if (j - i) // 2 >= minlen:
                n += 1
            i = j
        else:
            i += 1
    return n


def looks_numeric_table(b):
    """小整数表 / 单调斜坡 / 定长重复行的启发式。"""
    n = len(b)
    if n < 256:
        return 0.0, []
    reasons = []
    score = 0.0
    # 1) u16 值集中在 0..255
    vals = struct.unpack_from("<%dH" % (n // 2), b)
    small = sum(1 for v in vals if v <= 255)
    if small / len(vals) > 0.9:
        score += 0.35
        reasons.append("u16 值 %.0f%% ≤255" % (100 * small / len(vals)))
    # 2) 存在长单调递增/递减斜坡
    runs = 0
    best = 0
    cur = 0
    prev = None
    for v in vals[:200000]:
        if prev is not None and ((0 < v - prev <= 8) or (0 < prev - v <= 8)):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
        prev = v
    runs = best
    if runs > 64:
        score += 0.25
        reasons.append("单调斜坡长 %d" % runs)
    # 3) 大量 4 字节定长重复（表项）
    c = collections.Counter(struct.unpack_from("<%dI" % (n // 4), b))
    top = c.most_common(1)[0][1] if c else 0
    if top > n / 4 / 20:
        score += 0.2
        reasons.append("u32 值 %d 次重复" % top)
    return score, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("block1", nargs="?",
                    default=r"D:\0_Project\01Test\ep5-fw-reverse\decoded\01_0101_427c0020.decoded.bin")
    ap.add_argument("base", nargs="?", default="0x427C0000")
    ap.add_argument("--json", default=None)
    ap.add_argument("--max-scan", type=int, default=4 * 1024 * 1024)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.block1, "rb").read()
    N = len(d)
    print("块 1: %d B (0x%X)  base=0x%08X" % (N, N, base))

    ent = []
    off = 0
    while off + 8 <= N:
        ptr, size = struct.unpack_from("<II", d, off)
        if not (base <= ptr < base + N) or size == 0 or size > N:
            break
        ent.append((off, ptr, size))
        off += 16
        if len(ent) > 400:
            break
    print("头部资源表: %d 项\n" % len(ent))

    rows = []
    print("%-4s %-11s %-11s %6s %6s %6s %6s  %s" % (
        "#", "地址", "大小", "打印%", "熵", "u16串", "表分", "关键词/说明"))
    for i, (eo, ptr, size) in enumerate(ent):
        so = ptr - base
        b = d[so:so + min(size, args.max_scan)]
        pr = printable_ratio(b)
        en = entropy(b)
        us = utf16_strings(b)
        sc, reasons = looks_numeric_table(b)
        hits = sorted({k.decode("latin-1") for k in KEYWORDS if k in b})
        kind = []
        if b[:2] == b"\xff\xd8":
            kind.append("JPEG")
        if b[:4] == b"\x89PNG":
            kind.append("PNG")
        if b[:4] in (b"OTTO", b"true", b"ttcf", b"wOFF"):
            kind.append("字体")
        if b[:4] == b"RIFF":
            kind.append("RIFF")
        if us > 20:
            kind.append("UTF-16 文本 %d 条" % us)
        elif pr > 0.85:
            kind.append("ASCII 文本")
        if sc >= 0.3:
            kind.append("数值表(%s)" % ";".join(reasons))
        if hits:
            kind.append("KW:" + ",".join(hits[:6]))
        rows.append({"idx": i, "offset": "0x%08X" % eo, "addr": "0x%08X" % ptr,
                     "size": size, "printable": round(pr, 3), "entropy": round(en, 3),
                     "utf16_strings": us, "table_score": round(sc, 3),
                     "kind": kind, "keywords": hits})
        print("%-4d 0x%08X %-11d %5.1f%% %6.2f %6d %6.2f  %s" % (
            i, ptr, size, pr * 100, en, us, sc, " | ".join(kind)[:90]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.json)

    print("\n=== 候选：数值表特征 或 命中关键词 ===")
    for r in rows:
        if r["table_score"] >= 0.3 or r["keywords"]:
            print("  #%-3d 0x%08X %-10d  %s" % (
                r["idx"], int(r["addr"], 16), r["size"],
                " | ".join(r["kind"])[:110]))


if __name__ == "__main__":
    main()
