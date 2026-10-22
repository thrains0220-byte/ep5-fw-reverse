#!/usr/bin/env python3
"""搜索「指向块 0 的指针数组」——典型的 af_data_pos[] / 效果注册表形态。

特征：一串单调递增的 32 位值，每个都落在块 0 的代码/数据区内。
这种表正是「效果 ID → 参数块」「镜头组 → AF 参数数组」这类注册表的实现形式。

用法: python find_ptr_tables.py <block0.bin> [base] [minlen] [maxlen]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
MIN = int(sys.argv[3]) if len(sys.argv) > 3 else 5
MAX = int(sys.argv[4]) if len(sys.argv) > 4 else 64

d = open(path, "rb").read()
N = len(d)
print(f"文件 {path}  {N} B  base=0x{base:08X}\n")

# 找出块 0 的"有效载荷区"：排除明显的全零/全FF区域
runs = []
i = 0
while i + 4 <= N:
    v = struct.unpack_from("<I", d, i)[0]
    if base <= v < base + N:
        j = i
        prev = v
        while j + 4 <= N:
            v = struct.unpack_from("<I", d, j)[0]
            if not (base <= v < base + N):
                break
            if v < prev:          # 要求单调递增（表内指针通常有序）
                break
            prev = v
            j += 4
        cnt = (j - i) // 4
        if cnt >= MIN:
            runs.append((i, cnt))
        i = max(j, i + 4)
    else:
        i += 4

print(f"找到 {len(runs)} 个候选指针表（长度 >= {MIN}）：\n")
shown = 0
for off, cnt in runs:
    if cnt > MAX:
        continue
    vals = [struct.unpack_from("<I", d, off + 4 * k)[0] for k in range(cnt)]
    print(f"  @ file 0x{off:08X} (rt 0x{base+off:08X})  {cnt} 项")
    print("      " + " ".join(f"0x{v:08X}" for v in vals[:16]))
    shown += 1
    if shown >= 40:
        break
if not shown:
    print("  （无）")
