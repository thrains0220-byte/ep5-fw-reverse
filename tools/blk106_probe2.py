#!/usr/bin/env python3
"""六比特层残余类符号集合精确统计 + 滑窗/4:3 反打包试验（判定是否存在位置相关结构）。
用法: blk106_probe2.py <decoded_02_0106_*.bin>
"""
import sys, collections, itertools

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ep5d/02_0106_43da0020.bin'
d = open(path, 'rb').read()
data = d[0x3E0:0x3E0 + 0x240000]

print("== 残余类符号集合 ==")
for k in [2,3,4,6,8,12,16]:
    print(f"-- k={k}")
    for r in range(k):
        vals = collections.Counter(data[r::k])
        top = ", ".join(f"0x{v:02X}:{c}" for v, c in vals.most_common(6))
        print(f"   r={r:2d} distinct={len(vals):3d}  {top}")

def bits_of(sym, msb=True):
    if msb:
        return [(sym >> (5-i)) & 1 for i in range(6)]
    return [(sym >> i) & 1 for i in range(6)]

def unpack_slide(data, msb=True):
    bits = []
    for s in data:
        bits.extend(bits_of(s, msb))
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for b in bits[i:i+8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)

def unpack_group4(data, msb=True):
    """4 个 6-bit 符号 -> 3 字节（符号连续比特流，8bit 边界在 4 符号处对齐）"""
    bits = []
    for s in data:
        bits.extend(bits_of(s, msb))
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for b in bits[i:i+8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)

for msb in (True, False):
    u = unpack_slide(data, msb)
    printable = sum(1 for b in u[:20000] if 32 <= b < 127 or b in (9,10,13))
    zeros = u[:20000].count(0)
    print(f"\n== MSB={msb} 滑窗反解：前 20000 字节可打印 {printable/200:.1f}%  0x00 占 {zeros/200:.1f}%")
    print("   前 96 字节:", u[:96].hex(' '))
    print("   前 48 字节 ascii:", repr(bytes(c if 32 <= c < 127 else 46 for c in u[:48])))
