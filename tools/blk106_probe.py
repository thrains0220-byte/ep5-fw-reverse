#!/usr/bin/env python3
"""六比特层（kind 0x106 分区资源 #0）结构统计：符号直方图、频率量化到 1/256、
残余类(k=2..64)符号集合、自相关、逐 bit 概率、4:3 重打包反解试验。
结论用途：判定该层是否可用「差分/频率/对齐」等统计法解码。
用法: blk106_probe.py <decoded_02_0106_*.bin> [--data-off 0x3E0 --data-len 0x240000]
"""
import sys, collections, math

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ep5d/02_0106_43da0020.bin'
d = open(path, 'rb').read()
DATA_OFF = 0x3E0
DATA_LEN = 0x240000
data = d[DATA_OFF:DATA_OFF + DATA_LEN]
print(f"file={len(d)} data=[0x{DATA_OFF:X},0x{DATA_OFF+DATA_LEN:X}) len={len(data)}")
print("tail non-FF:", sum(1 for b in d[DATA_OFF+DATA_LEN:] if b != 0xFF), "of", len(d)-DATA_OFF-DATA_LEN)

hist = collections.Counter(data)
print(f"distinct symbols: {len(hist)}  max=0x{max(hist):02X} min=0x{min(hist):02X}")
missing = [i for i in range(64) if i not in hist]
print("missing symbols:", [hex(x) for x in missing])
tot = len(data)
H = -sum((c/tot)*math.log2(c/tot) for c in hist.values())
print(f"entropy={H:.4f} bits/byte")

print("\n-- 频次分布（按值）--")
for v in range(64):
    c = hist.get(v, 0)
    if c:
        print(f"  0x{v:02X}({v:3d}) {c:8d} {c/tot*100:6.3f}%  {'#'*int(c/tot*400)}")
    else:
        print(f"  0x{v:02X}({v:3d})        0  ------")

print("\n-- 位置模 k 偏置（k=1..64 的 2 的幂 + 1536/768/576）--")
for k in [2,3,4,6,8,12,16,24,32,48,64,128,256,512,576,768,1536,3072]:
    buckets = [collections.Counter() for _ in range(k)]
    for i, b in enumerate(data):
        buckets[i % k][b] += 1
    # 用每个 bucket 的熵与全局熵比较
    ent = [(-sum((c/len(data)/k)*math.log2(c/len(data)/k) for c in buck.values())) for buck in buckets]
    avg = sum(ent)/k
    print(f"  k={k:5d} 平均桶熵={avg:.4f} (全局 {H:.4f}) 差 {avg-H:+.4f}")

print("\n-- 游程长度分布 --")
runs = []
cur = data[0]; n = 1
for b in data[1:]:
    if b == cur:
        n += 1
    else:
        runs.append((cur, n)); cur = b; n = 1
runs.append((cur, n))
rl = collections.Counter(n for _, n in runs)
print("  run 长度直方图(前20):", sorted(rl.items())[:20])
print("  平均游程", sum(n for _, n in runs)/len(runs))

print("\n-- 二进制位统计 --")
for bit in range(8):
    c = sum(1 for b in data if b >> bit & 1)
    print(f"  bit{bit}: {c} ({c/tot*100:.2f}%)")

print("\n-- 前 256 字节 --")
for i in range(0, 256, 32):
    print(f"  +0x{i:03X}: " + ' '.join(f'{b:02X}' for b in data[i:i+32]))

print("\n-- 尾部 64 字节 --")
for i in range(64, 0, -16):
    print(f"  -0x{i:03X}: " + ' '.join(f'{b:02X}' for b in data[-i:len(data)-i+16]))
