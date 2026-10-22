#!/usr/bin/env python3
"""搜索「效果 ID → ROM 参数块地址」的索引表。

依据：效果实现与调校参数在机身 mask ROM（如 0x7E5C9809 / 0x7E5C9B1C），
      而 art_get_dramatic_tone_addr 之类的函数返回的就是 ROM 地址。
      ⇒ 注册表很可能是「按效果 ID 索引的 ROM 地址数组」。

判据：在块 0 中找出若干个 0x7E5C9xxx（及邻近页）的 32 位值，
      观察它们是否按 ID(10/20/30/40/50) 等距排列。

用法: python find_rom_effect_table.py <block0.bin> [base] [pageHex]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
page = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x7E5C9
d = open(path, "rb").read()
N = len(d)
lo_page = page << 12          # page 是 20 位页号（5 位十六进制），左移 12 位得 64KB 页基址
hi_page = lo_page + 0x10000

print(f"块 {path}  base=0x{base:08X}   ROM 页 0x{page:06X}xxxx\n")

# 收集落在该 ROM 页的值及其出现位置
occ = collections.defaultdict(list)
for off in range(0, N - 3):
    v = struct.unpack_from("<I", d, off)[0]
    if lo_page <= v < hi_page:
        occ[v].append(off)

print(f"该 ROM 页被块 0 引用的地址: {len(occ)} 个")
for v in sorted(occ):
    print(f"   0x{v:08X}  x{len(occ[v])}  @ file " +
          ", ".join(f"0x{o:08X}" for o in occ[v][:4]))

# 检查是否存在按 ID 索引的表：找等差且值递增的组
print("\n=== 按 ID 等距排列的候选（步长 4/8/12/16）===")
allpos = sorted((off, v) for v, lst in occ.items() for off in lst)
for step in (4, 8, 12, 16, 20, 24, 32):
    groups = []
    cur = []
    for off, v in allpos:
        if cur and off - cur[-1][0] == step:
            cur.append((off, v))
        else:
            if len(cur) >= 3:
                groups.append(cur)
            cur = [(off, v)]
    if len(cur) >= 3:
        groups.append(cur)
    for g in groups:
        vals = [v for _, v in g]
        inc = all(b > a for a, b in zip(vals, vals[1:]))
        print(f"  step={step}  起始 file 0x{g[0][0]:08X} (rt 0x{base+g[0][0]:08X})  {len(g)} 项  递增={inc}")
        for off, v in g[:14]:
            print(f"      0x{base+off:08X} -> 0x{v:08X}")
        print()
