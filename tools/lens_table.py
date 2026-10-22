#!/usr/bin/env python3
"""解析 E-P5 1.8 块 0 中的「镜头 ID 表」。

结构（观察，0x405E8F80 起）：
    uint16 category; uint16 index; uint8 maker; uint8 model; uint16 pad(0)
每条记录 = 一个镜头：category+index 可能是内部编号，maker/model 是 4 字节镜头 ID 的高两字节。

用法: lens_table.py <block0.bin> [base] [start] [end]
"""
import sys, collections

def parse(d, base, start, end):
    recs = []
    off = start - base
    while off + 8 <= len(d) and base + off < end:
        cat = d[off] | (d[off+1] << 8)
        idx = d[off+2] | (d[off+3] << 8)
        maker, model = d[off+4], d[off+5]
        pad = d[off+6] | (d[off+7] << 8)
        recs.append((base+off, cat, idx, maker, model, pad))
        off += 8
    return recs

def main():
    path = sys.argv[1]
    base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
    start = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x405E8F80
    end = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x405EA000
    d = open(path, "rb").read()
    recs = parse(d, base, start, end)

    # 只保留 pad==0 且 cat 合理、maker 合理的记录
    good = [r for r in recs if r[5] == 0 and r[1] in (0,1,2,3,4,5,6,7) and r[3] != 0]
    print(f"区间 0x{start:08X}..0x{end:08X}  解析 {len(recs)} 条，结构完好 {len(good)} 条\n")

    print("=== 按 category 分组 ===")
    bycat = collections.defaultdict(list)
    for r in good:
        bycat[r[1]].append(r)
    for cat in sorted(bycat):
        rs = bycat[cat]
        makers = sorted({r[3] for r in rs})
        print(f"\n  category {cat}  ({len(rs)} 条)  厂商码: " +
              " ".join(f"{m:02X}" for m in makers))
        for addr, c, idx, mk, mo, _ in rs:
            print(f"    0x{addr:08X}  idx=0x{idx:04X}  lensID={mk:02X}:{mo:02X}")

    print("\n=== 全表汇总：按厂商码列型号码 ===")
    bymaker = collections.defaultdict(list)
    for r in good:
        bymaker[r[3]].append((r[2], r[4], r[1], r[0]))
    for mk in sorted(bymaker):
        items = sorted(bymaker[mk])
        print(f"  {mk:02X}: " + " ".join(f"{mo:02X}" for _, mo, _, _ in items) +
              f"   (idx: " + " ".join(f"{i:02X}" for i, _, _, _ in items) + ")")

    print("\n=== 与 E-P5 1.8 比较链的交集 ===")
    chain = [(0xC1,0x80),(0xC1,0x00),(0xC0,0xF1),(0xC0,0xE1),(0x80,0xF1),(0x81,0xE3),(0x81,0xF1)]
    tableset = {(r[3], r[4]) for r in good}
    for c in chain:
        mark = "  <= 链命中" if c in tableset else ""
        print(f"  {c[0]:02X}:{c[1]:02X}{mark}")
    print("\n  表中有、链中没有的 C0/C1/80/81 项:")
    for t in sorted(tableset):
        if t[0] in (0xC0, 0xC1, 0x80, 0x81) and t not in chain:
            print(f"    {t[0]:02X}:{t[1]:02X}")

if __name__ == "__main__":
    main()
