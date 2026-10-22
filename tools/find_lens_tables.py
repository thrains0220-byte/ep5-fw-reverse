#!/usr/bin/env python3
"""搜索块 0 内所有含多个「已知镜头 ID 对」的数据窗口 —— 找第二张镜头表。

已知镜头 ID 前缀（来自 LENS_INFO 主表与比较链）：
  C1:80 C1:00 C0:F1 C0:E1 80:F1 81:E3 81:F1
若 AF 修复是往**另一张**表里加松下镜头条目，这里会看到。

用法: python find_lens_tables.py <block0.bin> <base>
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)

PAIRS = [(0xC1, 0x80), (0xC1, 0x00), (0xC0, 0xF1), (0xC0, 0xE1),
         (0x80, 0xF1), (0x81, 0xE3), (0x81, 0xF1)]
# 更宽的候选集：LENS_INFO 表里出现过的全部 maker:model
WIDE = set()
for mk in (0x60, 0x70, 0x80, 0x81, 0xB0, 0xB1, 0xC0, 0xC1, 0xC2, 0xC3, 0xD0, 0xD1, 0xE0):
    for mo in range(256):
        WIDE.add((mk, mo))

print(f"文件 {path}  {N} B  base=0x{base:08X}\n")

# 滑动窗口，统计窗口内出现的已知前缀对（相邻两字节）
WIN = 256
hits = collections.defaultdict(set)
for i in range(N - 1):
    p = (d[i], d[i + 1])
    if p in WIDE:
        hits[i // WIN].add(p)

best = []
for b, s in hits.items():
    known = len(s & set(PAIRS))
    if known >= 2 or len(s) >= 6:
        best.append((known, len(s), b, s))
best.sort(key=lambda t: (-t[0], -t[1]))
print(f"=== 命中窗口（前 30）===")
for known, tot, b, s in best[:30]:
    lo = b * WIN
    sample = " ".join(f"{m:02X}:{v:02X}" for m, v in sorted(s)[:14])
    print(f"  file 0x{lo:08X}..0x{lo+WIN:08X}  已知前缀 {known}/7  候选对 {tot}  {sample}")

# 精确找 7 对全中的窗口
print("\n=== 含全部 7 个已知前缀的窗口 ===")
allw = set(PAIRS)
for b, s in hits.items():
    if s >= allw:
        lo = b * WIN
        print(f"  file 0x{lo:08X}..0x{lo+WIN:08X}  {sorted(s)}")
