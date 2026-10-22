#!/usr/bin/env python3
"""解析块 1（多语言 UI 资源块）的内部布局。

要回答：哪里是 UTF-16 文本池、哪里是字体/图形数据、语言分区边界在哪、
字符串如何对齐（为"等长替换/插入名字"做准备）。

做法：
  1) 逐 512 字节统计：可打印 UTF-16 比例、零字节比例、非文本数据比例
  2) 找出连续的「文本密集区」与「二进制区」
  3) 在文本区里找「语言分区」边界：连续出现同一组 @A0xx@ 资源 ID 的区域
  4) 报告块 1 头部（前 0x400）的结构

用法: python block1_layout.py [block1.bin]
"""
import sys, re, collections

path = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\01_0101_427c0020.decoded.bin"
d = open(path, "rb").read()
N = len(d)
print(f"块 1: {N} B (0x{N:X})\n")

# ---------- 1. 头部结构 ----------
print("=== 头部前 0x80 字节 ===")
for off in range(0, 0x80, 16):
    row = d[off:off + 16]
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"  0x{off:04X}  {row.hex(' ')}  |{txt}|")

# ---------- 2. 区块类型扫描（4KB 粒度）----------
CH = 4096
buckets = []
for off in range(0, N, CH):
    seg = d[off:off + CH]
    if not seg:
        continue
    # UTF-16 可打印对占比
    pairs = 0
    for i in range(0, len(seg) - 1, 2):
        if 0x20 <= seg[i] < 0x7F and seg[i + 1] == 0:
            pairs += 1
    utf16_ratio = pairs / max(1, len(seg) // 2)
    zeros = seg.count(0) / len(seg)
    buckets.append((off, utf16_ratio, zeros))

def kind(r, z):
    if r > 0.55:
        return "UTF16文本"
    if z > 0.90:
        return "全零/填充"
    if r < 0.03 and z < 0.2:
        return "二进制数据"
    return "混合"

print("\n=== 区域类型（4KB 粒度）===")
runs = []
for off, r, z in buckets:
    k = kind(r, z)
    if runs and runs[-1][0] == k:
        runs[-1][2] = off + CH
        runs[-1][3] += 1
    else:
        runs.append([k, off, off + CH, 1])
for k, a, b, n in runs:
    print(f"  {k:<10} 0x{a:08X}..0x{b:08X}  ({n} x 4KB)")

# ---------- 3. 语言分区边界（@A0xx@ 密度）----------
print("\n=== 语言分区候选（@A0xx@ 密度峰）===")
ITEM = re.compile(rb"@(A0[0-9A-F]{2})@")
cnt = collections.Counter()
for off in range(0, N - 8, 2):
    m = ITEM.match(d[off:off + 8])
    if m:
        cnt[off // 0x1000] += 1
top = sorted(cnt.items(), key=lambda kv: -kv[1])[:20]
for kb, c in top:
    print(f"  0x{kb*0x1000:08X}  命中 {c}")

# ---------- 4. 字符串池对齐规则 ----------
print("\n=== 字符串池对齐抽样（前 40 个 UTF-16 串的起始偏移奇偶与对齐）===")
starts = []
i = 0
while i < N - 4 and len(starts) < 40:
    if d[i + 1] == 0 and 0x20 <= d[i] < 0x7F and (i == 0 or not (d[i - 1] == 0 and 0x20 <= d[i - 2] < 0x7F)):
        j = i
        ok = True
        while j + 1 < N and d[j + 1] == 0 and 0x20 <= d[j] < 0x7F:
            j += 2
        if j - i >= 8 and (j >= N or d[j] == 0):
            starts.append(i)
        i = j
    else:
        i += 1
print("  起始偏移 mod 4 分布:", collections.Counter(s % 4 for s in starts))
print("  起始偏移 mod 2 分布:", collections.Counter(s % 2 for s in starts))
print("  样例:", [hex(s) for s in starts[:12]])
