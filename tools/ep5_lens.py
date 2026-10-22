#!/usr/bin/env python3
"""EP5 镜头识别结构精确提取器（MN103）。

两个子命令：
  chain <block0.bin> <base>   —— 精确还原「镜头 ID 两字节前缀比较链」的 (maker, model) 对
  table <block0.bin> <base>   —— 提取 LENS_INFO 主表（8 字节记录）
  diff  <A.bin> <B.bin> <base> —— 两个固件的 chain + table 差分

chain 的精确性来自还原编译器的两种比较风格：
  风格 A:  mov <maker>,d1 ; cmp d1,d0        ; cmp <model>,d0
  风格 B:  cmp <maker>,d0                    ; cmp <model>,d0
两种风格下，"比的是高字节还是次字节"由前一条 load 指令决定：
  f0 40      movbu (a0),d0       -> 高字节（记录+14）
  f8 42 0f   movbu (15,a2),d0    -> 次字节（记录+15）

用法示例:
  python ep5_lens.py chain decoded/00_0100_402c0020.decoded.bin 0x402C0000
"""
import sys, struct

# --- MN103 指令常量 ---
OP_MOV_IMM16_D1 = 0x2D      # 2d HH 00   mov HH,d1
OP_CMP_D1_D0   = 0xA4      # a4         cmp d1,d0
OP_CMP_IMM16   = 0xC8      # fa c8 LL 00
OP_CMP_IMM8    = 0xA0      # a0 LL      cmp LL,d0
OP_MOVBU_A0_D0 = 0x40      # f0 40      movbu (a0),d0
OP_MOVBU_15_A2 = 0x42      # f8 42 0f   movbu (15,a2),d0


def decode_chain(d, base, lo, hi):
    """在 [lo,hi) 内精确还原前缀比较链，返回 [(addr, maker, model)]。

    策略：线性扫描，维护：
      cur_maker  —— d1 中当前持有的厂商码（来自 mov HH,d1）
      last_reg   —— d0 当前持有的是「高字节」还是「次字节」
    """
    out = []
    cur_maker = None
    last_reg = None
    i = lo
    while i < hi - 1:
        b = d[i]
        # f0 40 : movbu (a0),d0   -> 高字节
        if b == 0xF0 and d[i + 1] == OP_MOVBU_A0_D0:
            last_reg = "hi"
            i += 2
            continue
        # f8 42 0f : movbu (15,a2),d0 -> 次字节
        if b == 0xF8 and d[i + 1] == OP_MOVBU_15_A2 and d[i + 2] == 0x0F:
            last_reg = "lo"
            i += 3
            continue
        # 2d HH 00 : mov HH,d1
        if b == OP_MOV_IMM16_D1 and d[i + 2] == 0x00:
            cur_maker = d[i + 1]
            i += 3
            continue
        # a4 : cmp d1,d0
        if b == OP_CMP_D1_D0:
            if last_reg == "hi" and cur_maker is not None:
                pending = cur_maker
                # 下一条应是 cmp <model>,d0
                m, ln = _read_cmp_imm(d, i + 1)
                if m is not None:
                    out.append((base + i - 4, pending, m))
                    i += 1 + ln
                    last_reg = "lo"
                    continue
            i += 1
            continue
        # fa c8 LL 00 : cmp LL,d0
        if b == 0xFA and d[i + 1] == OP_CMP_IMM16 and i + 3 < hi:
            imm = d[i + 2] | (d[i + 3] << 8)
            if last_reg == "hi":
                # 风格 B：直接比高字节 -> 记住为候选 maker
                pending_maker = imm
                i += 4
                # 紧随其后的应该是次字节比较
                m, ln = _read_cmp_imm(d, i)
                if m is not None:
                    out.append((base + i - 4, pending_maker, m))
                    i += ln
                    last_reg = "lo"
                    continue
                cur_maker = pending_maker
                continue
            elif last_reg == "lo" and cur_maker is not None:
                out.append((base + i - 4, cur_maker, imm))
                i += 4
                continue
            i += 4
            continue
        # a0 LL : cmp LL,d0 (8 位立即数形式)
        if b == OP_CMP_IMM8:
            if last_reg == "lo" and cur_maker is not None:
                out.append((base + i - 4, cur_maker, d[i + 1]))
            i += 2
            continue
        i += 1
    return out


def _read_cmp_imm(d, i):
    """在 i 处读一条 cmp 立即数指令，返回 (立即数, 长度)。"""
    if i + 1 >= len(d):
        return None, 0
    if d[i] == 0xFA and d[i + 1] == OP_CMP_IMM16 and i + 3 < len(d):
        return d[i + 2] | (d[i + 3] << 8), 4
    if d[i] == OP_CMP_IMM8:
        return d[i + 1], 2
    return None, 0


def find_chain_windows(d, base, gap=64, min_hits=3):
    """定位比较链所在窗口：movbu (15,a2),d0 密集出现且其间有 cmp 立即数。"""
    sites = []
    for i in range(len(d) - 3):
        if d[i] == 0xF8 and (d[i + 1] & 0xE0) == 0x40 and d[i + 2] == 0x0F:
            sites.append(i)
    groups, cur = [], []
    for s in sites:
        if cur and s - cur[-1] > gap:
            groups.append(cur)
            cur = []
        cur.append(s)
    if cur:
        groups.append(cur)
    wins = []
    for g in groups:
        if len(g) < min_hits:
            continue
        lo = max(0, g[0] - 64)
        hi = min(len(d), g[-1] + 16)
        wins.append((lo, hi, g))
    return wins


# ---------------- LENS_INFO 主表 ----------------

LENS_INFO_MARK = b"LENS_INFO SIZE"


def find_lens_info_table(d, base):
    """定位 LENS_INFO 主表。

    结构：表尾之后紧跟一段 ASCII 字符串区（"set/reset/aperture/focus/.../LENS_INFO SIZE"），
    表本身是连续的 8 字节记录（uint16 cat, uint16 slot, uint8 maker, uint8 model, uint16 extra）。
    因此：先找 'LENS_INFO SIZE'，再回退找到字符串区起点 = 表尾，然后按 8 字节向前回溯记录。
    """
    m = d.find(LENS_INFO_MARK)
    if m < 0:
        return None, []
    # 回退到字符串区起点：可打印 ASCII / 0 的连续区
    s = m
    while s > 0 and (32 <= d[s - 1] < 127 or d[s - 1] == 0):
        s -= 1
    # 字符串区起点未必与 8 字节记录对齐，逐个候选偏移试，取能回溯出最多合法记录者
    best = ([], None)
    for adj in range(-8, 8):
        table_end = s + adj
        recs = []
        o = table_end - 8
        while o >= 0:
            cat, slot = struct.unpack_from("<HH", d, o)
            maker, model = d[o + 4], d[o + 5]
            if cat not in (2, 3, 5) or maker == 0:
                break
            # 排除误吞的 ASCII 文本（两个字节都可打印 = 字符串，不是记录）
            if 32 <= maker < 127 and 32 <= model < 127:
                break
            extra = struct.unpack_from("<H", d, o + 6)[0]
            recs.append((base + o, cat, slot, maker, model, extra))
            o -= 8
        recs.reverse()
        if len(recs) > len(best[0]):
            best = (recs, recs[0][0] - base if recs else None)
    recs, start = best
    if not recs:
        return None, []
    return start, recs


def cmd_chain(path, base):
    d = open(path, "rb").read()
    print(f"文件 {path}  {len(d)} B  base=0x{base:08X}\n")
    for lo, hi, g in find_chain_windows(d, base):
        pairs = decode_chain(d, base, lo, hi)
        if len(pairs) < 3:
            continue
        print(f"### 比较链窗口 0x{base+lo:08X}..0x{base+hi:08X}  "
              f"movbu(15) x{len(g)}  -> {len(pairs)} 对")
        for addr, mk, mo in pairs:
            print(f"    0x{addr:08X}   {mk:02X}:{mo:02X}")
        print()


def cmd_table(path, base):
    d = open(path, "rb").read()
    print(f"文件 {path}  {len(d)} B  base=0x{base:08X}\n")
    start, recs = find_lens_info_table(d, base)
    if start is None:
        print("未定位到 LENS_INFO 表")
        return
    print(f"LENS_INFO 表 @ 0x{base+start:08X}   记录数 {len(recs)}\n")
    for addr, cat, slot, mk, mo, ex in recs:
        print(f"  0x{addr:08X}  cat={cat} slot=0x{slot:04X} lensID={mk:02X}:{mo:02X} extra=0x{ex:04X}")
    print("\n--- 集合形式 ---")
    ids = sorted({(r[3], r[4]) for r in recs})
    print("  " + " ".join(f"{m:02X}:{s:02X}" for m, s in ids))
    print(f"  共 {len(ids)} 个唯一 lensID")


def cmd_diff(a, b, base):
    da, db = open(a, "rb").read(), open(b, "rb").read()
    ca, cb = [], []
    for d, acc in ((da, ca), (db, cb)):
        for lo, hi, g in find_chain_windows(d, base):
            p = decode_chain(d, base, lo, hi)
            if len(p) >= 3:
                acc.append([(m, s) for _, m, s in p])
    sa, sb = [], []
    for d, acc in ((da, sa), (db, sb)):
        _, recs = find_lens_info_table(d, base)
        acc.append({(r[3], r[4]) for r in recs})
    print("=== 比较链 ===")
    for i, (x, y) in enumerate(zip(ca, cb)):
        print(f"  链#{i}: A={len(x)} 项  B={len(y)} 项")
        print(f"    仅 A 有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(set(x) - set(y))))
        print(f"    仅 B 有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(set(y) - set(x))))
    print("\n=== LENS_INFO 表 ===")
    for i, (x, y) in enumerate(zip(sa, sb)):
        print(f"  表#{i}: A={len(x)} 项  B={len(y)} 项")
        print(f"    仅 A 有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(x - y)))
        print(f"    仅 B 有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(y - x)))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "chain":
        cmd_chain(sys.argv[2], int(sys.argv[3], 0))
    elif cmd == "table":
        cmd_table(sys.argv[2], int(sys.argv[3], 0))
    elif cmd == "diff":
        cmd_diff(sys.argv[2], sys.argv[3], int(sys.argv[4], 0))
    else:
        print(__doc__)
