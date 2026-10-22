#!/usr/bin/env python3
"""找出块 0 内所有引用「艺术效果 ID 全局变量」的指令/函数。

0x605fcd3c = iRam605fcd3c（由 FUN_4078846d 的伪代码确认：效果 ID 10/50）
用法: python find_art_global.py <block0.bin> <base> [global_addr_hex]
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
gaddr = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x605FCD3C

d = open(path, "rb").read()
N = len(d)
pat = struct.pack("<I", gaddr)
hits = [i for i in range(N - 3) if d[i:i + 4] == pat]
print(f"块 {path}  {N} B  base=0x{base:08X}")
print(f"全局 0x{gaddr:08X} 的 4 字节引用: {len(hits)} 处\n")
for off in hits:
    print(f"  file 0x{off:08X}  (rt 0x{base+off:08X})   前 6 字节: {d[max(0,off-6):off+4].hex(' ')}")

# 附近是否有其它"效果 ID"候选全局（同一 0x605fcdxx 区）
print(f"\n=== 0x605FCD00..0x605FCD7F 区内的其它全局（按引用次数）===")
cnt = collections.Counter()
for i in range(N - 3):
    v = struct.unpack_from("<I", d, i)[0]
    if 0x605FCD00 <= v <= 0x605FCD80:
        cnt[v] += 1
for v, c in cnt.most_common(20):
    print(f"  0x{v:08X}  被引用 {c} 次")
