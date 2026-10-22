#!/usr/bin/env python3
"""枚举块 0 引用的 mask ROM 地址（按 ROM 页聚类），用于发现 ROM 里的资源块数量。

艺术滤镜的每个效果的参数块都在 mask ROM（0x7E5C9xxx 一带）。
枚举这些地址就能知道 **ROM 里一共存在多少个艺术效果**，
而固件只暴露了 5 个（10/20/30/40/50）⇒ 多出来的就是"可解锁"的目标。

用法: python find_rom_refs.py <block0.bin> [romPageHex] [ctxBytes]
"""
import sys, struct, collections

path = sys.argv[1]
d = open(path, "rb").read()
N = len(d)
page = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x7E5C9
ctx = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x200

refs = collections.Counter()
for off in range(0, N - 3):
    v = struct.unpack_from("<I", d, off)[0]
    if (v >> 16) == page:
        refs[v] += 1

print(f"块 {path}  ROM 页 0x{page:06X}xxxx  被引用 {len(refs)} 个不同地址\n")
for v, c in sorted(refs.items()):
    print(f"  0x{v:08X}  被引用 {c} 次")
