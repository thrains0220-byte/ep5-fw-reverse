#!/usr/bin/env python3
"""在块 0 数据区定位「艺术效果注册表」：一个记录数组，其 ID 字段含 10/20/30/40/50。

约束（比 find_art_table.py 更严）：
  * 记录步长 S ∈ {4,8,12,16,20,24,28,32}
  * 记录内 ID 字段偏移固定
  * 一个 64 字节窗口内至少出现 4 个不同的 art 效果 ID
  * 记录里同时含有指向块 0 的 32 位指针（说明是"ID + 处理函数/参数块"结构）

用法: python find_art_reg.py <block0.bin> <base>
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)
IDS = {10, 20, 30, 40, 50}

def in_img(v):
    return base <= v < base + N

print(f"块 {path}  {N} B  base=0x{base:08X}\n")
found = 0
for S in (4, 8, 12, 16, 20, 24, 28, 32):
    for id_off in range(0, S, 2):
        for ptr_off in range(0, S - 3, 4):
            if id_off + 2 > ptr_off and ptr_off + 4 > id_off:
                continue
            for start in range(0, N - S * 8, 4):
                # 先快速看窗口内是否有 >=4 个不同 ID
                win_ids = set()
                for k in range(8):
                    o = start + k * S
                    if o + id_off + 2 > N:
                        break
                    v = struct.unpack_from("<H", d, o + id_off)[0]
                    if v in IDS:
                        win_ids.add(v)
                if len(win_ids) < 4:
                    continue
                # 逐条校验：ID 有效 + 指针在镜像内
                ok = 0
                for k in range(8):
                    o = start + k * S
                    if o + S > N:
                        break
                    v = struct.unpack_from("<H", d, o + id_off)[0]
                    if v not in IDS:
                        continue
                    p = struct.unpack_from("<I", d, o + ptr_off)[0]
                    if in_img(p):
                        ok += 1
                if ok < 4:
                    continue
                found += 1
                print(f"  stride={S} id@{id_off} ptr@{ptr_off}  起点 file 0x{start:08X} (rt 0x{base+start:08X})")
                for k in range(8):
                    o = start + k * S
                    if o + S > N:
                        break
                    rec = d[o:o + S]
                    v = struct.unpack_from("<H", d, o + id_off)[0]
                    p = struct.unpack_from("<I", d, o + ptr_off)[0]
                    mark = "  <<< art ID" if v in IDS else ""
                    print(f"      0x{base+o:08X}  id={v:<4d} ptr=0x{p:08X}{mark}   raw={rec.hex(' ')}")
                print()
                if found >= 6:
                    sys.exit(0)
if not found:
    print("  未找到满足条件的注册表")
