#!/usr/bin/env python3
"""在归一化反汇编里找出比较了多个 art 效果 ID (10/20/30/40/50) 的函数。

art 效果 ID 空间 = 10(star_light) 20(pinhole) 30(frame) 40(soft_focus) 50(white_edge)
`art_chk_effect` / `art_GetFilterType` 之类的分派函数必然要比较这些值。

用法: python find_art_funcs.py <norm2.txt> [minhits]
"""
import sys, re, collections

CMP = re.compile(r"\bCMP\s+0x([0-9a-f]+)")

path = sys.argv[1]
minhits = int(sys.argv[2]) if len(sys.argv) > 2 else 3
IDS = {10, 20, 30, 40, 50}

rows = []
for line in open(path, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if not line or line.startswith("#") or "|" not in line:
        continue
    entry, body = line.split("|", 1)
    cs = {int(m.group(1), 16) for m in CMP.finditer(body)}
    hit = cs & IDS
    if len(hit) >= minhits:
        rows.append((len(hit), entry.strip(), sorted(hit), len(cs)))

rows.sort(key=lambda t: (-t[0], -t[3]))
print(f"比较了 ≥{minhits} 个 art 效果 ID 的函数: {len(rows)} 个\n")
for n, e, hit, tot in rows[:30]:
    print(f"  {e}  命中 {n}/5 {[hex(x) for x in hit]}   (该函数共 {tot} 个不同比较常量)")
