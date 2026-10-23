#!/usr/bin/env python3
"""通用「镜头 ID 前缀比较链」扫描器（MN103）。
E-P5 1.8 的链形态：f0 40 (movbu (a0),d0) + 2d <H> 00 (mov <H>,d1) + a4 (cmp d1,d0)
                     + f8 42 <disp> (movbu (<disp>,a2),d0) + fa c8 <L> 00 / a0 <L>
不同机型「次字节」位移可能不同，故对 disp = 0..63 全扫。
用法: lens_chain_scan.py <decoded_block0.bin> [base]
"""
import sys, collections

def movbu_disp_sites(d, disp):
    out = []
    for i in range(len(d) - 3):
        if d[i] == 0xF8 and (d[i + 1] & 0xE0) == 0x40 and d[i + 2] == disp:
            out.append(i)
    return out

def cmp_imm(d, i, hi):
    if i + 1 >= hi:
        return None
    if d[i] == 0xFA and d[i + 1] == 0xC8 and i + 3 < hi:
        return d[i + 2] | (d[i + 3] << 8), 4
    if d[i] == 0xA0 and i + 1 < hi:
        return d[i + 1], 2
    return None

def mov16_d1(d, i, hi):
    """2d H 00 —— mov <H>,d1"""
    if i + 2 < hi and d[i] == 0x2D and d[i + 2] == 0x00:
        return d[i + 1], 3
    return None

def clusters(sites, gap=64):
    out = []
    if not sites:
        return out
    cur = [sites[0]]
    for x in sites[1:]:
        if x - cur[-1] <= gap:
            cur.append(x)
        else:
            out.append(cur); cur = [x]
    out.append(cur)
    return out

def main():
    path = sys.argv[1]
    base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    d = open(path, 'rb').read()
    print(f"文件 {path} ({len(d)} B) base=0x{base:08X}")
    best = []
    for disp in range(0, 64):
        for g in clusters(movbu_disp_sites(d, disp)):
            if len(g) < 6:
                continue
            lo = max(0, g[0] - 64)
            hi = min(len(d), g[-1] + 32)
            lows, highs = [], []
            i = lo
            while i < hi:
                c = cmp_imm(d, i, hi)
                if c:
                    lows.append(c[0]); i += c[1]; continue
                m = mov16_d1(d, i, hi)
                if m:
                    highs.append(m[0]); i += m[1]; continue
                i += 1
            # 镜头 ID 前缀：高字节 > 0x7F 且次字节多为小值
            score = sum(1 for h in highs if h > 0x7F)
            if score >= 2 and len(lows) >= 3:
                best.append((score, len(lows), disp, lo, hi, lows, highs))
    best.sort(reverse=True)
    for score, nl, disp, lo, hi, lows, highs in best[:12]:
        print(f"\n### disp=0x{disp:02X}  窗口 0x{base+lo:08X}..0x{base+hi:08X}  "
              f"高字节(>7F) {score} 个, 次字节比较 {nl} 个")
        print("    次字节常量: " + " ".join(f"0x{v:02X}" for v in lows))
        print("    高字节常量: " + " ".join(f"0x{v:02X}" for v in highs))
    if not best:
        print("未找到候选镜头 ID 比较链")

if __name__ == "__main__":
    main()
