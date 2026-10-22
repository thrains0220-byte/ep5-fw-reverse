#!/usr/bin/env python3
"""把块 0 的字符串按「前缀簇」聚类，产出完整子系统清单 + 逆向覆盖度评估。

 Olympus 固件用大写下划线前缀标识子系统（IMG_ / AF_ / SCENE_ / MENU_ / USB_ ...）。
 本脚本统计每个前缀簇的字符串数量、涉及的字符串样例、以及在块 0 中的地址分布，
 用来回答"哪些固件信息还没逆向成功"。

用法: python subsystem_survey.py <strings.jsonl>
"""
import json, re, collections, sys, os

path = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"

rows = [json.loads(l) for l in open(path, encoding="utf-8")]
byblock = collections.Counter(r["block"] for r in rows)
print(f"字符串总���: {len(rows)}   按块: {dict(sorted(byblock.items()))}\n")

# ---- 前缀提取：连续大写/数字/下划线段（Olympus 风格）----
PREFIX = re.compile(r"^([A-Z][A-Z0-9]*(?:_[A-Z0-9]+){0,4})")

clusters = collections.defaultdict(list)
for r in rows:
    if r["block"] != 0:
        continue
    t = r["text"]
    m = PREFIX.match(t)
    if m:
        key = m.group(1)
    else:
        # 非大写开头：取第一个下划线前的词
        key = t.split("_")[0][:14] if "_" in t else t[:8]
    clusters[key].append(r)

print(f"块 0 前缀簇数量: {len(clusters)}\n")
print("=== 按规模排序的前 70 个簇 ===")
print(f"{'簇':<22}{'条数':>7}  {'首现偏移':>12}  样例")
for key, lst in sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:70]:
    lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
    lo = lst[0]["decoded_offset"]
    samp = "; ".join(r["text"][:26] for r in lst[:3])
    print(f"{key:<22}{len(lst):>7}  {lo:>12}  {samp}")

print("\n=== 全部簇（按首现偏移排序，便于定位）===")
rows2 = []
for key, lst in clusters.items():
    lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
    rows2.append((int(lst[0]["decoded_offset"], 16), key, len(lst)))
for off, key, n in sorted(rows2):
    print(f"  0x{off:08X}  {key:<26} {n}")

print("\n=== 统计 ===")
sizes = sorted((len(v) for v in clusters.values()), reverse=True)
print(f"簇总数 {len(clusters)}   最大簇 {sizes[:10]}")
print(f"覆盖字符串: {sum(sizes)} / {byblock[0]}")
print(f"单条簇（多为普通文本）: {sum(1 for s in sizes if s == 1)}")
