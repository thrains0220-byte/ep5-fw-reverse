#!/usr/bin/env python3
"""E-P5 固件子系统测绘（第二版）：用三类高信噪比标记。

  1. 日志标签      "[MOV_ART]" "[AVCHD]" "[WIFI@]" "[chls]" ...
  2. 全局状态变量  "g_lens_firmup_send_num" "g_ois_sw_info" ...
  3. 多级小写函数名 "api_adj_Get_Adjust_DispErr" "mov_art_get_ctrl_..."

这三类几乎不产生噪声，可直接当作子系统的"锚点"。

用法: python subsystem_map.py [strings.jsonl] [out.md]
"""
import json, re, collections, sys, os

src = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"
out = sys.argv[2] if len(sys.argv) > 2 else None

rows = [json.loads(l) for l in open(src, encoding="utf-8")]
b0 = [r for r in rows if r["block"] == 0]
print(f"块 0 字符串 {len(b0)} 条\n")

# ---------- 1. 日志标签 ----------
TAG = re.compile(r"\[([A-Za-z][A-Za-z0-9_@ ]{1,24})\]")
tags = collections.defaultdict(list)
for r in b0:
    for m in TAG.finditer(r["text"]):
        t = m.group(1).strip()
        if t and not t.isdigit():
            tags[t].append(r)
print(f"=== 日志标签: {len(tags)} 个 ===")
for t, lst in sorted(tags.items(), key=lambda kv: -len(kv[1]))[:60]:
    lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
    print(f"  {t:<26} x{len(lst):<5} 首现 0x{lst[0]['decoded_offset']}  {lst[0]['text'][:44]!r}")

# ---------- 2. g_* 全局 ----------
gglob = collections.defaultdict(list)
for r in b0:
    t = r["text"]
    m = re.match(r"^g_([a-z0-9_]+)$", t)
    if m:
        gglob[m.group(1).split("_")[0]].append(r)
print(f"\n=== g_* 全局变量: {sum(len(v) for v in gglob.values())} 个 / {len(gglob)} 个二级前缀 ===")
for k, lst in sorted(gglob.items(), key=lambda kv: -len(kv[1]))[:40]:
    lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
    print(f"  g_{k:<20} x{len(lst):<4} 0x{lst[0]['decoded_offset']}  {lst[0]['text'][:40]!r}")

# ---------- 3. 函数名簇（多级小写下划线） ----------
FN = re.compile(r"^([a-z][a-z0-9]*(?:_[a-z0-9]+){1,4})_")
fnc = collections.defaultdict(list)
for r in b0:
    t = r["text"]
    if not re.match(r"^[a-z][a-z0-9_]*$", t):
        continue
    m = FN.match(t)
    if m:
        fnc[m.group(1)].append(r)
print(f"\n=== 函数名簇（≥2 段）: {len(fnc)} 个 ===")
for k, lst in sorted(fnc.items(), key=lambda kv: -len(kv[1]))[:70]:
    lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
    print(f"  {k:<34} x{len(lst):<4} 0x{lst[0]['decoded_offset']}  {lst[0]['text'][:38]!r}")

if out:
    with open(out, "w", encoding="utf-8") as f:
        f.write("# E-P5 1.8 块 0 子系统测绘\n\n")
        f.write(f"来源: `{os.path.basename(src)}`（块 0 共 {len(b0)} 条字符串）\n\n")
        f.write("## 1. 日志标签（子系统锚点）\n\n")
        f.write("| 标签 | 条数 | 首现偏移 | 样例 |\n|---|---|---|---|\n")
        for t, lst in sorted(tags.items(), key=lambda kv: -len(kv[1])):
            lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
            f.write(f"| `{t}` | {len(lst)} | 0x{lst[0]['decoded_offset']} | {lst[0]['text'][:40]!r} |\n")
        f.write("\n## 2. g_* 全局状态变量\n\n| 二级前缀 | 条数 | 首现偏移 | 样例 |\n|---|---|---|---|\n")
        for k, lst in sorted(gglob.items(), key=lambda kv: -len(kv[1])):
            lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
            f.write(f"| `g_{k}` | {len(lst)} | 0x{lst[0]['decoded_offset']} | {lst[0]['text'][:40]!r} |\n")
        f.write("\n## 3. 函数名簇\n\n| 簇 | 条数 | 首现偏移 | 样例 |\n|---|---|---|---|\n")
        for k, lst in sorted(fnc.items(), key=lambda kv: -len(kv[1])):
            lst = sorted(lst, key=lambda r: int(r["decoded_offset"], 16))
            f.write(f"| `{k}` | {len(lst)} | 0x{lst[0]['decoded_offset']} | {lst[0]['text'][:40]!r} |\n")
    print(f"\n已写出 {out}")
