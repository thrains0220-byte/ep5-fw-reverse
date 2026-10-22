#!/usr/bin/env python3
"""块 1 艺术滤镜「资源 ID ↔ 名字」的偏移级精确对齐。

在 UTF-16LE 字符串池里找出所有形如 `@Axxx@<艺术滤镜名>` 的串，
按偏移排序并聚类成语言分区，输出每个分区内的
「资源 ID → 名字」有序序列。

用法:
    python block1_art_id_dump.py --blk1 <blk1.bin> [--out dump.json]
"""
import argparse
import json
import re
from collections import defaultdict

ART = [
    "Pop Art", "Dramatic Tone", "Soft Focus", "Pale&Light Color", "Light Tone",
    "Diorama", "Pin Hole", "Cross Process", "Gentle Sepia", "Grainy Film",
    "Monochrome", "Star Light", "Muted", "Natural", "Vivid", "Portrait",
    "i-Enhance", "White Edge", "Pastel", "Clear Line", "Shading Control",
    "Mute", "Flat", "Pop", "Grainy", "Tone", "Sepia",
]
LOW = {a.lower(): a for a in ART}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk1", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--gap", type=int, default=0x400, help="分区切分间隔")
    args = ap.parse_args()

    raw = open(args.blk1, "rb").read()
    txt = raw.decode("utf-16-le", errors="ignore")
    rx = re.compile(r"@([A-Z][0-9A-F]{2,4})@")

    hits = []
    for mo in rx.finditer(txt):
        rid = mo.group(1)
        j = mo.end()
        k = txt.find("\x00", j)
        if k < 0:
            continue
        s = txt[j:k].strip()
        if s.lower() in LOW:
            hits.append((mo.start() * 2, rid, LOW[s.lower()], s))

    hits.sort()
    print("块 1 共匹配到 %d 条「@ID@艺术滤镜名」记录\n" % len(hits))

    # 聚类
    clusters = []
    cur = []
    for h in hits:
        if cur and h[0] - cur[-1][0] > args.gap:
            clusters.append(cur)
            cur = []
        cur.append(h)
    if cur:
        clusters.append(cur)

    out = []
    for ci, cl in enumerate(clusters):
        ids = {}
        for off, rid, name, raw_txt in cl:
            ids.setdefault(rid, set()).add(name)
        # 同一 ID 在同一分区内若对应多个名字 → 冲突
        conflicts = {k: sorted(v) for k, v in ids.items() if len(v) > 1}
        out.append({
            "cluster": ci,
            "range": ["0x%08X" % cl[0][0], "0x%08X" % cl[-1][0]],
            "n": len(cl),
            "id_to_names": {k: sorted(v) for k, v in sorted(ids.items())},
            "conflicts": conflicts,
        })
        print("── 分区 #%d  0x%08X..0x%08X  (%d 条)" % (
            ci, cl[0][0], cl[-1][0], len(cl)))
        for off, rid, name, raw_txt in cl:
            print("    0x%08X  %-6s %-18s %r" % (off, rid, name, raw_txt[:40]))
        if conflicts:
            print("    ⚠ 同 ID 多名: %s" % conflicts)
        print()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("[written] %s" % args.out)


if __name__ == "__main__":
    main()
