#!/usr/bin/env python3
"""容器校验算法候选公式求解：sum32 / crc32 / adler32 及其对头尾的组合覆盖。
用法: solve_checksum.py <容器 .bin 或 decoded 分区 .bin>
"""
import struct, zlib, binascii, sys
from array import array

def sum32(data):
    if len(data) % 4:
        return None
    w = array('I'); w.frombytes(data)
    return sum(w) & 0xFFFFFFFF

def crc32(data, init=0):
    return zlib.crc32(data, init) & 0xFFFFFFFF

path = sys.argv[1] if len(sys.argv) > 1 else 'dec4/OLY_E_120_1300_0000_0000/decoded/02_0106_43160020.decoded.bin'
d = open(path, 'rb').read()

# 逐块遍历嵌套容器
off = d.find(b'OE')
blocks = []
while off + 32 <= len(d):
    hdr = d[off:off+32]
    if hdr[:2] not in (b'OE', b'OM'):
        break
    size = struct.unpack_from('<I', hdr, 12)[0]
    ps, pe = off+32, off+32+size
    trailer = d[pe:pe+16]
    blocks.append((off, hdr, ps, pe, trailer))
    off = pe + 16
print(f"解析到 {len(blocks)} 个嵌套块")

target = blocks[0][4][12:16]
print("首个块 trailer:", blocks[0][4].hex(' '), " 目标校验值:", target.hex(' '))

payload = d[blocks[0][2]:blocks[0][3]]
hdr = blocks[0][1]
cands = {
    'sum32(payload)': sum32(payload),
    'sum32(hdr+payload)': sum32(hdr+payload),
    'sum32(hdr[0:28]+payload)': sum32(hdr[:28]+payload),
    'sum32(hdr[8:28]+payload)': sum32(hdr[8:28]+payload),
    'sum32(payload+hdr)': sum32(payload+hdr),
    'crc32(payload)': crc32(payload),
    'crc32(hdr+payload)': crc32(hdr+payload),
    'adler32(payload)': binascii.adler32(payload),
}
t = struct.unpack('<I', target)[0]
print("\n候选公式对首个块的结果:")
for k, v in cands.items():
    ok = (v is not None and v == t)
    print(f"  {'★命中' if ok else '  '} {k:<28} = 0x{(v or 0):08X}  目标 0x{t:08X}")

# 尝试：校验值 = 基础 + 块序号
if cands['sum32(payload)'] is not None:
    base = cands['sum32(payload)']
    print(f"\nsum32(payload) 与目标差 = 0x{(t-base)&0xFFFFFFFF:08X}")
    for i,(o,h,ps,pe,tr) in enumerate(blocks[:6]):
        tt = struct.unpack('<I', tr[12:16])[0]
        sp = sum32(d[ps:pe])
        print(f"  块{i}: sum32=0x{sp:08X} trailer=0x{tt:08X} 差=0x{(tt-sp)&0xFFFFFFFF:08X}")
