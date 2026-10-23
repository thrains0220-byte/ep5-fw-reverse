#!/usr/bin/env python3
"""把两版代码块的差异分成「重链接位移」与「语义改动」：对 4 字节对齐的 u32 计算
(新-旧) 有符号差，若差值集中在少数常量上 ⇒ 属布局位移。
注意：代码整体搬家时 u32 对齐会失真，结论需结合指令级差分复核。
用法: relink_vs_semantic.py <A_block0.bin> <B_block0.bin> [base]
"""
import sys, collections, struct

def analyze(a_path, b_path, base=0):
    a = open(a_path, 'rb').read()
    b = open(b_path, 'rb').read()
    n = min(len(a), len(b))
    deltas = collections.Counter()
    sem = []
    for i in range(0, n - 3, 2):
        x = struct.unpack_from('<I', a, i)[0]
        y = struct.unpack_from('<I', b, i)[0]
        if x == y:
            continue
        d = (y - x) & 0xFFFFFFFF
        if d >= 0x80000000:
            d -= 0x100000000
        deltas[d] += 1
        if d not in (0, 0x1F, 0x10, 0xB8, 0x11, 0x2C, 0x1E):
            sem.append((i, x, y, d))
    print(f"=== {a_path}\n    vs {b_path}")
    print(f"    4 字节对齐且内容不同的 u32 槽位：{sum(deltas.values())}")
    print("    差值直方图（前 12）：")
    for d, c in deltas.most_common(12):
        print(f"      {d:+#12x} ({d:>12})  x{c}")
    tot = sum(deltas.values())
    known = sum(c for d, c in deltas.items() if d in (0, 0x1F, 0x10, 0xB8, 0x11, 0x2C, 0x1E))
    print(f"    落在已知位移集合 {{0,+0x1F,+0x10,+0xB8}} 的占 {known}/{tot} = {known*100//max(tot,1)}%")
    print(f"    语义改动候选（差值不在已知集合）：{len(sem)}")
    for i, x, y, d in sem[:25]:
        print(f"      偏移 0x{i:08X} (运行地址 0x{base+i:08X})  0x{x:08X} -> 0x{y:08X}  ({d:+d})")
    return deltas, sem

if __name__ == "__main__":
    base = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    analyze(sys.argv[1], sys.argv[2], base)
