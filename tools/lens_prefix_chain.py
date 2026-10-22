#!/usr/bin/env python3
"""提取 MN103 固件中"镜头 ID 两字节前缀比较链"的常量集合。

背景
----
奥林巴斯相机通过镜头上的电子触点读取 4 字节镜头 ID（记录 +14..+17，大端）。
固件里多处按 ID 的**高两字节**做前缀比较：命中即走"已知镜头"分支。
E-P5 1.8 中该比较链位于 0x403B7989，7 个前缀：
0xC180 0xC100 0xC0F1 0xC0E1 0x80F1 0x81E3 0x81F1

指令形态（MN103）
-----------------
    movbu (a0),d0          ; f0 40      —— ID 高字节（a0 = 记录+14）
    mov  <H>,d1            ; 2d H 00    —— H > 0x7F 时编译器用长形式
    cmp  d1,d0             ; a4
    bne  ...               ; c9 XX
    movbu (15,a2),d0       ; f8 42 0f   —— ID 次字节
    cmp  <L>,d0            ; fa c8 L 00 （L > 0x7F）/ a0 L （L <= 0x7F）
    beq/bne ...            ; c8/c9 XX

编译器会复用寄存器（同一个 H 只 mov 一次），因此本脚本不强行配对，
而是把每条链里出现的比较常量按出现顺序输出，供跨机型集合比对。

用法: lens_prefix_chain.py <decoded_block0.bin> [base_addr]
"""
import sys

# --- MN103 指令字节常量 ---
MOVBU_A0_D0 = 0x40        # f0 40      movbu (a0),d0
MOVBU_DISP_D0 = 0x42      # f8 42 0f   movbu (15,a2),d0
CMP_IMM16 = 0xC8          # fa c8 imm16
MOV_IMM16_D1 = 0x2D       # 2d imm16   mov <H>,d1
CMP_D1_D0 = 0xA4          # a4         cmp d1,d0
CMP_IMM8 = 0xA0           # a0 imm8    cmp <L>,d0


def sites_movbu_disp(d, disp):
    """所有 movbu (disp,aN),d0 的位置（f8 4N disp）。"""
    out = []
    for i in range(len(d) - 3):
        if d[i] == 0xF8 and (d[i + 1] & 0xE0) == 0x40 and d[i + 2] == disp:
            out.append(i)
    return out


def read_cmp_imm(d, i, hi):
    """在 [i,hi) 内从 i 起解读一条 cmp 立即数指令，返回 (立即数, 指令长度)。

    支持两种编码：
      fa c8 <imm16>   cmp <imm16>,d0
      a0  <imm8>     cmp <imm8>,d0
    """
    if i + 1 >= hi:
        return None
    if d[i] == 0xFA and d[i + 1] == CMP_IMM16 and i + 3 < hi:
        return d[i + 2] | (d[i + 3] << 8), 4
    if d[i] == CMP_IMM8 and i + 1 < hi:
        return d[i + 1], 2
    return None


def chains_of(d, disp=0x0F, gap=64, min_hits=3):
    """找出比较链：窗口内出现 >=min_hits 个 movbu(disp) 且其间有 cmp 立即数。"""
    sites = sites_movbu_disp(d, disp)
    groups, cur = [], []
    for s in sites:
        if cur and s - cur[-1] > gap:
            groups.append(cur)
            cur = []
        cur.append(s)
    if cur:
        groups.append(cur)

    res = []
    for g in groups:
        if len(g) < min_hits:
            continue
        lo, hi = g[0] - 48, g[-1] + 16
        if lo < 0:
            lo = 0
        if hi > len(d):
            hi = len(d)
        # 逐个 movbu 之后找最近的 cmp 立即数
        pairs = []
        for s in g:
            j = s + 3
            while j < min(s + 20, hi):
                got = read_cmp_imm(d, j, hi)
                if got:
                    pairs.append((s, got[0]))
                    break
                j += 1
        if len(pairs) >= min_hits:
            res.append((lo, hi, g, pairs))
    return res


def high_bytes(d, lo, hi):
    """窗口内 mov <H>,d1（2d H 00）的 H —— 编译器只对 >0x7F 的高字节用长形式。"""
    out = []
    i = lo
    while i < hi - 2:
        if d[i] == MOV_IMM16_D1 and d[i + 2] == 0x00:
            out.append((i, d[i + 1]))
            i += 3
            continue
        i += 1
    return out


def main():
    path = sys.argv[1]
    base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
    d = open(path, "rb").read()
    print(f"文件 {path}  ({len(d)} B)  base=0x{base:08X}")
    found = False
    for idx, (lo, hi, g, pairs) in enumerate(chains_of(d)):
        found = True
        lows = [v for _, v in pairs]
        highs = [v for _, v in high_bytes(d, lo, hi)]
        print(f"\n### 链 #{idx}  0x{base + lo:08X} .. 0x{base + hi:08X}  "
              f"movbu(15) 点 {len(g)}，次字节比较 {len(pairs)}")
        print("    次字节常量: " + " ".join(f"0x{v:02X}" for v in lows))
        print("    高字节常量: " + " ".join(f"0x{v:02X}" for v in highs))
    if not found:
        print("未找到镜头 ID 前缀比较链")


if __name__ == "__main__":
    main()
