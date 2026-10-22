#!/usr/bin/env python3
"""搜索「资源 ID → art 效果 ID」映射表。

块 1 里 E-P5 照片模式的名字带资源 ID A03F..A048（连续）。
若固件内部有一张「资源 ID → 效果 ID(10/20/30/40/50)」的表，
它应当以连续的资源 ID 序列（u16 或 u8）开头，紧跟效果 ID。

用法: python find_res_map.py <file1> [file2 ...]
"""
import sys, struct

RES = list(range(0x3F, 0x49))          # A03F..A048
PAT_U16 = b"".join(struct.pack("<H", r) for r in RES)
PAT_U8 = bytes(RES)

def scan(path, pat, label):
    d = open(path, "rb").read()
    i = d.find(pat)
    out = []
    while i >= 0:
        out.append(i)
        i = d.find(pat, i + 1)
    print(f"  [{label}] {len(out)} 处命中")
    for off in out[:12]:
        print(f"      0x{off:08X}  后 32 字节: {d[off:off+32].hex(' ')}")
    return out

for path in sys.argv[1:]:
    print(f"=== {path} ===")
    scan(path, PAT_U16, "u16 连续资源 ID")
    scan(path, PAT_U8,  "u8  连续资源 ID")
    print()
