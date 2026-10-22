#!/usr/bin/env python3
"""提取奥林巴斯固件中"镜头厂商/协议码"比较表。

该表出现在镜头 ID 解析路径上：取镜头记录 +10 处的 1 字节厂商码，
与一串常量比较，命中则把该厂商码写入全局 0x9A400014。

E-P5 1.8（0x403B5AC9）与 E-P3 v1.6（0x403EDCC7）的形态完全一致：

    mov 10,a0 ; add a1,a0 ; movbu (a0),d0
    cmp 0xB0,d0 ; beq ...      <- 起点特征字节 fa c8 b0 00
    cmp 0xB1,d0 ; beq ...
    cmp 0xB2,d0 ; beq ...
    cmp 0x70,d0 ; beq ...
    cmp 0xC0,d0 ; beq ...
    cmp 0xC1,d0 ; beq ...
    cmp 0xC2,d0 ; beq ...
    cmp 0xC3,d0 ; beq ...
    cmp 0x80,d0 ; beq ...
    cmp 0x81,d0 ; bne ...

本脚本以 `fa c8 b0 00` 为锚点，向后扫描并抽取全部立即数比较，
输出该机型认可的厂商码集合，便于跨机型比对（新增厂商码 = 该机型的补丁）。

用法: maker_code_table.py <decoded_block0.bin> [base_addr]
"""
import sys

ANCHOR = bytes.fromhex("fac8b000")     # cmp 0xB0,d0 —— 表的起点特征
CMP16 = 0xC8                          # fa c8 imm16
CMP8 = 0xA0                           # a0 imm8
MAX_SPAN = 160                        # 表最长字节跨度


def extract(d, i, hi):
    """从 i 起抽取连续比较的立即数，直到分支离开该链。"""
    out = []
    j = i
    while j < min(i + MAX_SPAN, hi):
        if d[j] == 0xFA and d[j + 1] == CMP16 and j + 3 < hi:
            out.append(d[j + 2] | (d[j + 3] << 8))
            j += 4
            continue
        if d[j] == CMP8 and j + 1 < hi:
            out.append(d[j + 1])
            j += 2
            continue
        # 允许条件分支穿过（MN103: c8/c9 XX = beq/bne，2 字节）
        if d[j] in (0xC8, 0xC9) and j + 1 < hi:
            j += 2
            continue
        break
    return out


def main():
    path = sys.argv[1]
    base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
    d = open(path, "rb").read()
    print(f"文件 {path}  ({len(d)} B)  base=0x{base:08X}")
    hits = []
    i = 0
    while True:
        i = d.find(ANCHOR, i)
        if i < 0:
            break
        codes = extract(d, i, len(d))
        if len(codes) >= 4:
            hits.append((i, codes))
        i += 1
    if not hits:
        print("  未找到厂商码比较表")
        return
    for off, codes in hits:
        uniq = []
        for c in codes:
            if c not in uniq:
                uniq.append(c)
        print(f"  表 @0x{base + off:08X}  共 {len(codes)} 次比较 / {len(uniq)} 个不同码")
        print(f"    厂商码: {' '.join('0x%02X' % c for c in uniq)}")


if __name__ == "__main__":
    main()
