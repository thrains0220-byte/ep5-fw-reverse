#!/usr/bin/env python3
"""寻找「art 效果 ID 范围检查」函数：同时比较 10 与 50。

art 效果 ID 空间 = 10..50（10/20/30/40/50）。
若分派走「按 ID 索引的表」，则必有一处 `id <= 50 && id >= 10` 的范围判断，
该函数会同时出现 CMP 10 与 CMP 50。

用法: python find_art_range.py <norm2.txt> [norm2b.txt ...]
"""
import sys, re, collections

CMP = re.compile(r"\bCMP\s+0x([0-9a-f]+)")

rows = []
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "|" not in line:
            continue
        entry, body = line.split("|", 1)
        cs = {int(m.group(1), 16) for m in CMP.finditer(body)}
        if 10 in cs and 50 in cs:
            rows.append((path, entry.strip(), sorted(cs & {10, 20, 30, 40, 50}),
                         len(cs), sorted(cs)[:24]))
    # 每个文件单独统计
print(f"=== 同时比较 10 与 50 的函数 ===")
for path, e, hit, tot, cs in rows:
    print(f"  {path.split(chr(92))[-1]:24s} {e}  artID命中 {[hex(x) for x in hit]}  共 {tot} 个常量")
    print(f"       常量集: {[hex(x) for x in cs]}")
