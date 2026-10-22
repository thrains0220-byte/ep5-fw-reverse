#!/usr/bin/env python3
"""搜索「效果 ID / 槽位 → art 效果名指针」的注册表。

背景：art_* 是**字符串**（消息名），不是函数名；实际像素处理在图像处理核里。
因此注册表应当是"一串指向这些字符串的 32 位指针"。

判据：块 0 内存在若干个 32 位值，其值落在 art 字符串区
      （运行时 0x40714000..0x4071A000，对应 E-P5 的 art 名字带），
      且这些指针**成组排列**（步长 4/8/12/16）。

用法: python find_art_name_table.py <block0.bin> <base>
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)

# art 名字带：从 art_effect_10 字符串起、到 art_* 最后一条
NAME_LO = base + 0x454E00
NAME_HI = base + 0x45A000
print(f"块 {path}  base=0x{base:08X}")
print(f"art 名字带: 0x{NAME_LO:08X}..0x{NAME_HI:08X}\n")

# 收集所有落在名字带里的 32 位指针
ptrs = collections.defaultdict(list)   # value -> [offsets]
for off in range(0, N - 3):
    v = struct.unpack_from("<I", d, off)[0]
    if NAME_LO <= v < NAME_HI:
        ptrs[v].append(off)

print(f"指向 art 名字带的指针值: {len(ptrs)} 个不同地址，"
      f"共 {sum(len(v) for v in ptrs.values())} 处引用\n")

# 找出成组（相邻 offset 间隔 <= 16）的引用簇
occ = sorted((off, v) for v, lst in ptrs.items() for off in lst)
clusters = []
for off, v in occ:
    if clusters and off - clusters[-1][-1][0] <= 16:
        clusters[-1].append((off, v))
    else:
        clusters.append([(off, v)])

print(f"引用簇（间距<=16）: {len(clusters)} 个\n")
for c in sorted(clusters, key=lambda x: -len(x))[:20]:
    print(f"  file 0x{c[0][0]:08X} (rt 0x{base+c[0][0]:08X})  {len(c)} 项")
    for off, v in c[:20]:
        # 读出被指向的字符串
        so = v - base
        s = d[so:so + 40].split(b"\x00")[0]
        print(f"      @0x{off:08X} -> 0x{v:08X}  {s.decode('ascii','replace')!r}")
    print()
