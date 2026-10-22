#!/usr/bin/env python3
"""在艺术簇附近搜索「效果 ID → 实现函数」的注册表（32 位函数指针数组）。

判据：文件内某处存在一段连续的 32 位值，每个都落在 art 簇代码范围内
（运行时 0x40780000-0x40790000），且这些地址确实对应 art 效果实现函数。

用法: python find_effect_registry.py <block0.bin> <base> [loOff] [hiOff]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
lo = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x400000
hi = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x500000

d = open(path, "rb").read()
N = len(d)
# art 簇代码区（运行时）
CODE_LO, CODE_HI = base + 0x4C0000, base + 0x4D0000

print(f"块 {path}  base=0x{base:08X}")
print(f"在 file 0x{lo:08X}..0x{hi:08X} 内搜指向 art 簇代码的指针数组\n")

runs = []
i = lo
while i < hi - 4:
    v = struct.unpack_from("<I", d, i)[0]
    if CODE_LO <= v < CODE_HI:
        j = i
        vals = []
        while j + 4 <= N:
            v = struct.unpack_from("<I", d, j)[0]
            if not (CODE_LO <= v < CODE_HI):
                break
            vals.append(v)
            j += 4
        if len(vals) >= 3:
            runs.append((i, vals))
            i = j
            continue
    i += 4

print(f"找到 {len(runs)} 段候选指针数组\n")
for off, vals in runs[:30]:
    print(f"  file 0x{off:08X} (rt 0x{base+off:08X})  {len(vals)} 项")
    for k, v in enumerate(vals[:20]):
        print(f"      [{k:2d}] 0x{v:08X}")
    print()
