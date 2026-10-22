#!/usr/bin/env python3
"""快速定位「艺术效果注册表」：ID 字段含 10/20/30/40/50 的定长记录数组。

做法：先按 (stride, id_off) 建索引 —— 记录所有 u16 值 ∈ art ID 集合的位置，
再在索引里找「间距恰为 stride」的等差链（≥4 个不同 ID）。
复杂度 O(匹配数)，而不是暴力 O(N × stride × 偏移)。

用法: python find_art_reg_fast.py <block0.bin> <base>
"""
import sys, struct, collections

path = sys.argv[1]
base = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x402C0000
d = open(path, "rb").read()
N = len(d)
IDS = {10, 20, 30, 40, 50}

# ---- 1. 收集所有 art ID 值出现的位置（按 u16 解释，任意字节对齐）----
pos = collections.defaultdict(list)   # value -> [offset]
for off in range(0, N - 1):
    v = d[off] | (d[off + 1] << 8)
    if v in IDS:
        pos[v].append(off)
print(f"art ID 值出现次数: " + ", ".join(f"0x{v:02X}:{len(p)}" for v, p in sorted(pos.items())))

# ---- 2. 对每种 (stride, id_off)，找等差链 ----
def chain_for(sig, stride, id_off):
    """sig: 同余类（offset % stride == id_off % stride）的位置集合。"""
    by = collections.defaultdict(list)
    for v, plist in pos.items():
        for o in plist:
            if (o - id_off) % stride == 0:
                by[o].append(v)
    if not by:
        return []
    # 沿 stride 前进
    starts = sorted(by.keys())
    chains = []
    seen = set()
    for s in starts:
        if s in seen:
            continue
        chain = []
        o = s
        while o in by:
            chain.append((o, tuple(sorted(by[o]))))
            seen.add(o)
            o += stride
        if len(chain) >= 3:
            ids = set()
            for _, vs in chain:
                ids.update(vs)
            if len(ids) >= 3:
                chains.append((chain, ids))
    return chains

print()
for stride in (4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 64):
    for id_off in range(0, min(stride, 8), 2):
        for chain, ids in chain_for(None, stride, id_off):
            if len(ids) < 4:
                continue
            # 校验：记录里是否含指向镜像内的 32 位指针
            print(f"  stride={stride} id@{id_off}  链长 {len(chain)}  ID 集 {sorted(ids)}")
            for o, vs in chain[:10]:
                rec = d[o:o + stride]
                ptrs = []
                for p_off in range(0, stride - 3, 4):
                    if p_off == id_off:
                        continue
                    pv = struct.unpack_from("<I", d, o + p_off)[0]
                    if base <= pv < base + N:
                        ptrs.append(f"+{p_off}:0x{pv:08X}")
                print(f"      0x{base+o:08X} id={vs} raw={rec.hex(' ')}  指针 {' '.join(ptrs)}")
            print()
