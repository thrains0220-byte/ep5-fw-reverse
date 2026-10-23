#!/usr/bin/env python3
"""在 MN103 代码块中扫描以 32 位立即数形式引用各分区运行地址的位置（用于定位分区消费者）。
用法: scan_part_refs.py <block0.bin> [base]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x402C0020
data = open(path, 'rb').read()

# 关注的分区区间（含少量前后余量）
REGIONS = [
    ("blk1", 0x427C0800, 0x427C0800 + 0x2B3600),
    ("blk2", 0x43DA0400, 0x43DA0400 + 0x240000),
    ("blk3", 0x44000400, 0x44000400 + 0x8DA00),
]

hits = collections.defaultdict(list)
for i in range(0, len(data) - 6, 2):
    v = struct.unpack_from('<I', data, i)[0]
    for name, lo, hi in REGIONS:
        if lo <= v < hi:
            # 前 2 字节作为可能的 opcode
            op = struct.unpack_from('<H', data, i - 2)[0] if i >= 2 else -1
            hits[name].append((i, v, op))

for name, lo, hi in REGIONS:
    lst = hits[name]
    print(f"=== {name}  0x{lo:08X}..0x{hi:08X}  hits={len(lst)}")
    ops = collections.Counter(x[2] for x in lst)
    print("  opcodes:", ", ".join(f"0x{o:04X}x{c}" for o, c in ops.most_common(8)))
    for i, v, op in lst[:40]:
        after = data[i + 4:i + 10].hex(' ')
        print(f"   file=0x{i:06X} addr=0x{base+i:08X} op=0x{op:04X} val=0x{v:08X} next={after}")
    if len(lst) > 40:
        print(f"   ... 其余 {len(lst)-40} 处")
