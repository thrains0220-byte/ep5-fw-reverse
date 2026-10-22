#!/usr/bin/env python3
"""解析块 1 头部的 (ptr, size) 资源表，并计算每条记录后的可用空白（gap）。

用途：为"往块 1 加入新字符串"找落脚点（块 1 大小固定，不能加长，只能用空白或等长替换）。

用法: python block1_manifest.py [block1.bin] [base]
"""
import sys, struct, collections

path = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\01_0101_427c0020.decoded.bin"
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x427C0000
d = open(path, "rb").read()
N = len(d)

print(f"块 1: {N} B (0x{N:X})  base=0x{base:08X}\n")
print("=== 头部 (ptr, size) 表 ===")
ent = []
off = 0
while off + 8 <= N:
    ptr, size = struct.unpack_from("<II", d, off)
    if not (base <= ptr < base + N) or size == 0 or size > N:
        break
    ent.append((off, ptr, size))
    off += 16
    if len(ent) > 400:
        break
print(f"共 {len(ent)} 条记录\n")
print(f"{'#':>3} {'表偏移':>10} {'地址':>12} {'大小':>10} {'结束':>12} {'到下一条空白':>12}")
for i, (eo, ptr, size) in enumerate(ent):
    end = ptr + size
    nxt = ent[i + 1][1] if i + 1 < len(ent) else base + N
    gap = nxt - end
    print(f"{i:>3} 0x{eo:08X} 0x{ptr:08X} {size:>10} 0x{end:08X} {gap:>12}")

# 空白统计
gaps = []
for i, (eo, ptr, size) in enumerate(ent):
    end = ptr + size
    nxt = ent[i + 1][1] if i + 1 < len(ent) else base + N
    gaps.append((nxt - end, i, ptr, size))
print("\n=== 空白最大的 10 个分区 ===")
for g, i, ptr, size in sorted(gaps, reverse=True)[:10]:
    print(f"  记录 #{i:3d} addr 0x{ptr:08X} size 0x{size:X}  后续空白 {g} B")

# 主文本池的 UTF-16 结构
big = max(ent, key=lambda e: e[2])
po, pptr, psize = big
print(f"\n=== 主文本池 0x{pptr:08X} size 0x{psize:X} ===")
seg = d[pptr - base: pptr - base + psize]
tail = seg[-4096:]
print("  末尾 64 字节:", tail[-64:].hex(" "))
print("  末尾零字节数:", len(tail) - len(tail.rstrip(b"\x00")))
# 池内是否有连续大段零
runs = []
i = 0
while i < len(seg):
    if seg[i] == 0:
        j = i
        while j < len(seg) and seg[j] == 0:
            j += 1
        if j - i >= 64:
            runs.append((i, j - i))
        i = j
    else:
        i += 1
print(f"  池内 >=64B 的零填充段: {len(runs)} 段")
for o, l in sorted(runs, key=lambda t: -t[1])[:8]:
    print(f"    池内 +0x{o:X}  长度 {l} (0x{l:X})")
