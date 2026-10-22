#!/usr/bin/env python3
"""提取 E-P5 1.8 块 0 内**全部**艺术效果实现（含编号体系）。

命名规律（从符号名归纳）：
  art_effect_<ID>_<name>          带显式 ID 的效果（如 art_effect_20_pinhole）
  art_filter_<NN>_<name>          带 2 位编号的过滤器（如 art_filter_06_rough_monochrome）
  art_<name>_pass1..N             效果实现主体（每个效果一组 pass）
  art_<name>_get_inf              效果参数区查询
用法: python art_effects_numbered.py [strings.jsonl]
"""
import json, re, collections, sys

src = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"
rows = [json.loads(l) for l in open(src, encoding="utf-8")]
b0 = [r for r in rows if r["block"] == 0]
arts = [r for r in b0 if re.match(r"^art_", r["text"])]

# 1) 显式 ID
print("=== A. art_effect_<ID>_<name> ===")
ids = {}
for r in arts:
    m = re.match(r"^art_effect_(\d+)_([a-z0-9_]+)$", r["text"])
    if m:
        ids.setdefault(int(m.group(1)), (m.group(2), int(r["decoded_offset"], 16)))
for i in sorted(ids):
    print(f"   ID {i:3d}  {ids[i][0]:24s} @ 0x{ids[i][1]:08X}")

# 2) art_filter_<NN>_<name>
print("\n=== B. art_filter_<NN>_<name> ===")
fnums = collections.defaultdict(set)
for r in arts:
    m = re.match(r"^art_filter_(\d+)_([a-z0-9_]+)$", r["text"])
    if m:
        fnums[int(m.group(1))].add(m.group(2))
for n in sorted(fnums):
    print(f"   NN {n:3d}  {' '.join(sorted(fnums[n]))}")

# 3) 每个效果实现的 pass 数量 + get_inf
print("\n=== C. 效果实现主体（按 pass 数排序）===")
impl = collections.defaultdict(lambda: {"pass": 0, "inf": False, "err": False,
                                       "free": False, "misc": [], "first": None})
for r in arts:
    t = r["text"]
    off = int(r["decoded_offset"], 16)
    m = re.match(r"^art_([a-z0-9_]+?)_(pass\d+|get_inf|pass_err|free)(.*)$", t)
    if not m:
        continue
    eff, kind = m.group(1), m.group(2)
    d = impl[eff]
    if d["first"] is None or off < d["first"]:
        d["first"] = off
    if kind.startswith("pass") and kind[4:].isdigit():
        d["pass"] = max(d["pass"], int(kind[4:]))
    elif kind == "get_inf":
        d["inf"] = True
    elif kind == "pass_err":
        d["err"] = True
    elif kind == "free":
        d["free"] = True

rowsx = []
for eff, d in impl.items():
    if d["pass"] < 2 and not d["inf"]:
        continue
    rowsx.append((d["pass"], eff, d))
rowsx.sort(key=lambda t: (-t[0], t[1]))
print(f"{'效果':<26}{'pass数':>7}{'get_inf':>9}{'err':>5}{'free':>6}   首现")
for p, eff, d in rowsx:
    print(f"art_{eff:<23}{p:>7}{'Y' if d['inf'] else '-':>9}"
          f"{'Y' if d['err'] else '-':>5}{'Y' if d['free'] else '-':>6}   0x{d['first']:08X}")

print(f"\n实现主体数: {len(rowsx)}")
