#!/usr/bin/env python3
"""搜索「效果 ID 列表」与「菜单资源 ID 列表」两张 u16 数组，并尝试配对。

已知：
  * 艺术效果 ID 空间 = {10, 20, 30, 40, 50}
  * 机身照片模式菜单资源 ID = A03F..A048 = {0x3F..0x48}（10 项，连续）
若块 0 数据区里存在一张 u16 数组同时含这两类值（甚至交替出现），
它就是「菜单项 -> 效果 ID」的对应表。

用法: python find_menu_effect_map.py <block0.bin> [base]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)

EFF = {10, 20, 30, 40, 50}
MENU = set(range(0x3F, 0x49))     # A03F..A048
ALL = EFF | MENU

print(f"块 {path}  base=0x{base:08X}")
print(f"效果 ID 集合 {sorted(EFF)}   菜单 ID 集合 0x3F..0x48\n")

# 1) 找全为效果 ID 的连续 u16 数组
def runs_of(vals):
    out = []
    i = 0
    while i < len(vals):
        if vals[i] in ALL:
            j = i
            while j < len(vals) and vals[j] in ALL:
                j += 1
            if j - i >= 3:
                out.append((i, vals[i:j]))
            i = j
        else:
            i += 1
    return out

u16 = [d[i] | (d[i + 1] << 8) for i in range(0, N - 1, 2)]
print("=== 含 ≥3 个（效果ID ∪ 菜单ID）的 u16 数组 ===")
hits = 0
for off, seq in runs_of(u16):
    eff = [v for v in seq if v in EFF]
    men = [v for v in seq if v in MENU]
    if not eff or not men:
        continue
    hits += 1
    fo = off * 2
    print(f"  file 0x{fo:08X} (rt 0x{base+fo:08X})  {len(seq)} 项")
    print(f"      效果ID位: {eff}")
    print(f"      菜单ID位: {[hex(v) for v in men]}")
    print(f"      原始序列: {seq[:40]}")
    print()
    if hits >= 12:
        break
if not hits:
    print("  （未找到同时含两类的数组）")

# 2) 全为效果 ID 的数组
print("=== 全为效果 ID 的 u16 数组（长度>=3）===")
for off, seq in runs_of(u16):
    if all(v in EFF for v in seq) and len(seq) >= 3:
        fo = off * 2
        print(f"  file 0x{fo:08X} (rt 0x{base+fo:08X})  {seq}")
