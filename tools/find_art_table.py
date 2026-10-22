#!/usr/bin/env python3
"""搜索「art 效果注册表」候选：记录数组里 ID 字段出现 10/20/30/40/50。

art 效果 ID 空间为 10/20/30/40/50（star_light/pinhole/frame/soft_focus/white_edge）。
注册表可能是 {id, ?, ...} 的定长记录数组（步长 4/8/12/16/20/24/32），
也可能是「按 id 直接下标」的稀疏数组。

用法: python find_art_table.py <block0.bin> [base]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)
IDS = (10, 20, 30, 40, 50)

print(f"文件 {path}  {N} B  base=0x{base:08X}\n")

# 情形 1：定长记录数组，ID 在记录内的偏移 0 / 2 / 4 / 6
print("=== 情形 1：定长记录数组（ID 在记录内偏移固定） ===")
for stride in (4, 8, 12, 16, 20, 24, 32, 40, 48, 64):
    for id_off in (0, 2, 4, 6):
        # 扫描所有起点，找出能连续命中 >=3 个不同 ID 的最长 run
        best = []
        start = 0
        while start < N - stride * 3:
            seq = []
            off = start
            while off + stride <= N:
                v = struct.unpack_from("<H", d, off + id_off)[0]
                if v in IDS:
                    seq.append((off, v))
                    off += stride
                else:
                    break
            if len(seq) >= 3:
                best.append((len(seq), start, seq))
                start = off + stride
            else:
                start += stride
        if not best:
            continue
        best.sort(reverse=True)
        for n, st, seq in best[:4]:
            if n < 3:
                continue
            print(f"  stride={stride} id@{id_off} 起点 file 0x{st:08X} (rt 0x{base+st:08X})  连续 {n} 条")
            for off, v in seq:
                rec = d[off:off + stride]
                print(f"      0x{base+off:08X}  id={v:<3d}  raw={rec.hex(' ')}")

# 情形 2：按 id 直接下标（步长 stride，槽位 id*stride 处非零）
print("\n=== 情形 2：按 id 直接下标的稀疏数组 ===")
for stride in (4, 8, 12, 16, 20, 24, 32):
    found = []
    for st in range(0, N - stride * 51):
        vals = []
        ok = True
        for i in IDS:
            o = st + i * stride
            if o + stride > N:
                ok = False
                break
            vals.append(d[o:o + stride])
        if not ok:
            continue
        # 至少 4 个槽位非全零，且互不相同
        nz = [v for v in vals if any(v)]
        if len(nz) < 4:
            continue
        if len(set(nz)) < 3:
            continue
        found.append((st, vals))
    if found:
        print(f"  stride={stride}: {len(found)} 个候选")
        for st, vals in found[:6]:
            print(f"    起点 file 0x{st:08X}")
            for i, v in zip(IDS, vals):
                print(f"       id {i:3d} @ 0x{base+st+i*stride:08X}  {v.hex(' ')}")
