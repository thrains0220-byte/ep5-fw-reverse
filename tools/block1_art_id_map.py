#!/usr/bin/env python3
"""把块 1 的字符串资源 ID 精确映射到艺术滤镜名。

只认「整条文本恰好等于某个滤镜名」的记录（避免抓到相邻串里的残留标记），
输出 ID → 名字 的确定性映射，并标出既无滤镜名也无菜单名占用的 ID。

用法:
    python block1_art_id_map.py --blk1 <block1.bin> --out <json>
"""
import argparse
import json
import re
from collections import defaultdict

ART_NAMES = [
    "Pop Art", "Dramatic Tone", "Soft Focus", "Pale&Light Color", "Light Tone",
    "Diorama", "Pin Hole", "Cross Process", "Gentle Sepia", "Grainy Film",
    "Monochrome", "Star Light", "Muted", "Natural", "Vivid", "Portrait",
    "i-Enhance", "White Edge", "Pastel", "Clear Line", "Shading Control",
    "Tone", "Sepia", "Pop", "Grainy",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk1", required=True)
    ap.add_argument("--base", default="0x43C40020")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    raw = open(args.blk1, "rb").read()
    txt = raw.decode("utf-16-le", errors="ignore")
    rx = re.compile(r"@[A-Z][0-9A-F]{2,4}@")

    namemap = {n.lower(): n for n in ART_NAMES}
    id2art = defaultdict(set)
    id2samples = defaultdict(set)
    for mo in rx.finditer(txt):
        rid = mo.group(0)[1:-1]
        j = mo.end()
        k = txt.find("\x00", j)
        if k < 0:
            continue
        s = txt[j:k].strip()
        if not s:
            continue
        id2samples[rid].add(s[:60])
        key = s.lower()
        if key in namemap:
            id2art[rid].add(namemap[key])

    print("=== 资源 ID → 艺术滤镜名（精确整串匹配）===")
    for rid in sorted(id2art):
        names = ", ".join(sorted(id2art[rid]))
        print("  %-8s %s" % (rid, names))

    print()
    print("=== A03F..A060 全量（含非滤镜文本）===")
    occupied = []
    for x in range(0x3F, 0x61):
        rid = "A%03X" % x
        if rid in id2art:
            occupied.append(rid)
            print("  %-8s [艺术滤镜] %s" % (rid, ", ".join(sorted(id2art[rid]))))
        elif rid in id2samples:
            samples = sorted(id2samples[rid])[:2]
            print("  %-8s [其它文本] %s" % (rid, " | ".join(s.replace("\n", " ")[:45] for s in samples)))
        else:
            print("  %-8s [空闲]" % rid)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"id_to_art_filter": {k: sorted(v) for k, v in sorted(id2art.items())},
                       "all_ids": sorted(id2samples.keys())},
                      f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.out)


if __name__ == "__main__":
    main()
