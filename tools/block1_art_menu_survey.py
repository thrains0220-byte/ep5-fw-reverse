#!/usr/bin/env python3
"""跨机型统计块 1 里「艺术滤镜菜单」的资源 ID 清单。

要回答的问题（第十八轮 ROADMAP §3）:
    E-P5 的照片艺术菜单有 10 项、录像艺术菜单只有 4 项 ——
    这个「4 vs 10」是 **E-P5 特有配置**，还是 **产品线结构性规律**？
    若是结构性的，则「让录像走照片那张描述符」的补丁方向被证实。

做法:
    1. 对每个机型的块 1，整池 UTF-16LE 解码；
    2. 抽出所有 `@Axxxx@<文本>` 形式的资源串（整串精确匹配文本白名单）；
    3. 按偏移聚类成「语言/屏幕分区」，每区内得到一条有序的 (ID, 名) 清单；
    4. 汇总：每个机型各分区的艺术滤镜条数与清单内容。

用法:
    python tools/block1_art_menu_survey.py --models <机型=块1路径> [...] [--json out.json]
    # 或直接扫目录：
    python tools/block1_art_menu_survey.py --scan <目录> [--json out.json]
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict

ART = [
    "Pop Art", "Dramatic Tone", "Soft Focus", "Pale&Light Color", "Light Tone",
    "Diorama", "Pin Hole", "Cross Process", "Gentle Sepia", "Grainy Film",
    "Monochrome", "Monotone", "Star Light", "Muted", "Natural", "Vivid", "Portrait",
    "i-Enhance", "White Edge", "Pastel", "Clear Line", "Shading Control",
    "Pop Art", "Tone", "Sepia", "Magic Filter", "Magic",
]
LOW = {}
for a in ART:
    LOW.setdefault(a.lower(), a)
RX = re.compile(r"@([A-Z][0-9A-F]{2,4})@")


def strings(txt):
    """切出 (offset_char, text) 的 NUL 分隔串。"""
    i = 0
    n = len(txt)
    while i < n:
        j = txt.find("\x00", i)
        if j < 0:
            j = n
        if j > i:
            yield i, txt[i:j]
        i = j + 1


def survey(path, gap=0x600):
    raw = open(path, "rb").read()
    txt = raw.decode("utf-16-le", errors="ignore")
    entries = []
    for off, s in strings(txt):
        m = RX.match(s)
        if not m:
            continue
        body = s[m.end():].strip()
        if body.lower() in LOW:
            entries.append((off * 2, m.group(1), LOW[body.lower()], body))
    # 聚类
    clusters = []
    cur = []
    for e in entries:
        if cur and e[0] - cur[-1][0] > gap:
            clusters.append(cur)
            cur = []
        cur.append(e)
    if cur:
        clusters.append(cur)
    out = []
    for c in clusters:
        seq = [(rid, nm) for _, rid, nm, _ in c]
        ids = [rid for rid, _ in seq]
        out.append({"range": ["0x%08X" % c[0][0], "0x%08X" % c[-1][0]],
                    "n": len(seq), "seq": seq,
                    "id_span": (ids[0], ids[-1]) if ids else None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[], help="机型名=块1路径")
    ap.add_argument("--scan", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--min-art", type=int, default=3,
                    help="分区里至少几条艺术滤镜才算一个『菜单清单』")
    args = ap.parse_args()

    models = []
    for m in args.models:
        name, _, p = m.partition("=")
        models.append((name, p))
    if args.scan:
        for p in sorted(glob.glob(os.path.join(args.scan, "**", "01_0101_*.decoded.bin"),
                                recursive=True)):
            tag = "%s/%s" % (os.path.basename(os.path.dirname(p)),
                             os.path.basename(p))
            models.append((tag, p))

    res = {}
    for name, p in models:
        if not os.path.exists(p):
            print("缺失: %s (%s)" % (name, p))
            continue
        cl = survey(p)
        menus = [c for c in cl if c["n"] >= args.min_art]
        res[name] = {"file": p, "clusters": cl, "menus": menus}
        print("=" * 100)
        print("%s   (%s)" % (name, os.path.basename(p)))
        print("  含艺术滤镜的分区 %d 个" % len(cl))
        for c in cl:
            mark = "★菜单" if c["n"] >= args.min_art else "  "
            seq = "  ".join("%s=%s" % (rid, nm) for rid, nm in c["seq"])
            print("   %s [%s..%s] n=%-3d %s" % (
                mark, c["range"][0], c["range"][1], c["n"], seq[:150]))
        # 统计：全局 ID → 名字集合
        id2n = defaultdict(set)
        for c in cl:
            for rid, nm in c["seq"]:
                id2n[rid].add(nm)
        multi = {k: sorted(v) for k, v in id2n.items() if len(v) > 1}
        if multi:
            print("  ⚠ 同 ID 多名（说明 ID 非全局唯一 / 分区语义不同）:")
            for k, v in sorted(multi.items()):
                print("     %s -> %s" % (k, ", ".join(v)))
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("[written] %s" % args.json)


if __name__ == "__main__":
    main()
