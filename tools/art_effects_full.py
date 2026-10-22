#!/usr/bin/env python3
"""枚举块 0 内全部 art_* 函数/符号名，按「效果」归组 —— 即固件实际实现的艺术效果全集。

这是"新增滤镜"可行性的关键：菜单只暴露一部分，但实现都在固件里。

用法: python art_effects_full.py [strings.jsonl]
"""
import json, re, collections, sys

src = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"
rows = [json.loads(l) for l in open(src, encoding="utf-8")]
b0 = [r for r in rows if r["block"] == 0]

arts = [r for r in b0 if re.match(r"^art_", r["text"])]
print(f"块 0 内 art_* 符号: {len(arts)} 条\n")

# 归组：art_<effect>_<func>  ->  effect
groups = collections.defaultdict(list)
for r in arts:
    t = r["text"]
    m = re.match(r"^art_([a-z0-9]+)_(.+)$", t)
    if m:
        groups[m.group(1)].append((t, int(r["decoded_offset"], 16)))
    else:
        groups["<misc>"].append((t, int(r["decoded_offset"], 16)))

# 已知 art_effect_<ID>_<name> 给出 ID 映射
idmap = {}
for r in arts:
    m = re.match(r"^art_effect_(\d+)_([a-z0-9_]+)$", r["text"])
    if m:
        idmap[m.group(2)] = (int(m.group(1)), r["text"])

print("=== 按效果归组（★ = 有 art_effect_<ID> 编号）===")
for k in sorted(groups, key=lambda x: -len(groups[x])):
    lst = sorted(groups[k], key=lambda t: t[1])
    tag = ""
    if k in idmap:
        tag = f"  ★ art_effect_ID={idmap[k][0]}  ({idmap[k][1]})"
    print(f"\n-- art_{k}  ({len(lst)} 个符号){tag}")
    for t, off in lst[:22]:
        print(f"     0x{off:08X}  {t}")
    if len(lst) > 22:
        print(f"     ... 还有 {len(lst)-22} 个")

print("\n=== 有 ID 编号的效果（= 5 个已确认的效果）===")
for name, (i, t) in sorted(idmap.items(), key=lambda kv: kv[1][0]):
    print(f"   ID {i:3d}  {name:24s}  {t}")
