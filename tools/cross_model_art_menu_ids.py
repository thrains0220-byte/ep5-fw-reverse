#!/usr/bin/env python3
"""跨机型聚合：艺术滤镜「资源 ID ↔ 名字」对照表（第十八轮 ROADMAP §3）。

对每个机型的块 1：
  1. 抽出所有 `@Axxx@<文本>` 串（文本须精确命中艺术滤镜名白名单）；
  2. 汇总成「ID → 名字集合」与「名字 → ID 集合」；
  3. 横向比较：**同一个名字在不同机型上落在哪个 ID**，
     以及**照片菜单段 / 录像菜单段**的 ID 边界。

用法:
    python tools/cross_model_art_menu_ids.py --blk1 <机型=块1路径> [...] [--json out.json]
"""
import argparse
import json
import os
import re
from collections import defaultdict

ART = [
    "Pop Art", "Dramatic Tone", "Soft Focus", "Pale&Light Color", "Light Tone",
    "Diorama", "Pin Hole", "Cross Process", "Gentle Sepia", "Grainy Film",
    "Monochrome", "Monotone", "Star Light", "Muted", "Natural", "Vivid", "Portrait",
    "i-Enhance", "White Edge", "Pastel", "Clear Line", "Shading Control", "Sepia",
]
LOW = {}
for a in ART:
    LOW.setdefault(a.lower(), a)
RX = re.compile(r"@([A-Z][0-9A-F]{2,4})@")


def scan(path):
    raw = open(path, "rb").read()
    txt = raw.decode("utf-16-le", errors="ignore")
    id2n = defaultdict(set)
    n2id = defaultdict(set)
    i = 0
    n = len(txt)
    while i < n:
        j = txt.find("\x00", i)
        if j < 0:
            j = n
        s = txt[i:j]
        m = RX.match(s)
        if m:
            body = s[m.end():].strip()
            if body.lower() in LOW:
                nm = LOW[body.lower()]
                id2n[m.group(1)].add(nm)
                n2id[nm].add(m.group(1))
        i = j + 1
    return id2n, n2id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk1", nargs="+", required=True, help="机型名=块1路径")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    models = []
    for m in args.blk1:
        name, _, p = m.partition("=")
        models.append((name, p))

    print("%-16s %s" % ("机型", "ID → 名字（艺术滤镜相关）"))
    print("-" * 118)
    allid2n = defaultdict(lambda: defaultdict(set))
    alln2id = defaultdict(lambda: defaultdict(set))
    for name, p in models:
        if not os.path.exists(p):
            print("%-16s 缺失" % name)
            continue
        id2n, n2id = scan(p)
        for k, v in id2n.items():
            for x in v:
                allid2n[k][name].add(x)
        for k, v in n2id.items():
            for x in v:
                alln2id[k][name].add(x)
        items = sorted(id2n.items(), key=lambda kv: kv[0])
        print("%-16s %s" % (name, "  ".join(
            "%s=%s" % (k, "/".join(sorted(v))) for k, v in items)))
        print()

    print("=" * 118)
    print("=== 名字 → ID（跨机型对照）===")
    for nm in sorted(alln2id):
        row = []
        for name, _ in models:
            ids = alln2id[nm].get(name)
            row.append("%s:%s" % (name.split()[0], ",".join(sorted(ids)) if ids else "-"))
        print("  %-18s %s" % (nm, "  ".join(row)))

    print()
    print("=" * 118)
    print("=== ID → 名字（跨机型对照）===")
    for rid in sorted(allid2n):
        row = []
        for name, _ in models:
            v = allid2n[rid].get(name)
            row.append("%s:%s" % (name.split()[0], "/".join(sorted(v)) if v else "-"))
        print("  %-6s %s" % (rid, "  ".join(row)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "id_to_name": {k: {m: sorted(v) for m, v in d.items()}
                               for k, d in allid2n.items()},
                "name_to_id": {k: {m: sorted(v) for m, v in d.items()}
                               for k, d in alln2id.items()},
            }, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
