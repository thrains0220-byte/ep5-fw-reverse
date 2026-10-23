#!/usr/bin/env python3
"""镜头子系统 mask ROM 指针表：修复前 / 修复后 逐表比对（位移归一化）。

定位方式（不依赖硬编码地址，跨机型通用）：
  1. 在块 0 里找 "af_data_pos" 字符串 ⇒ 得到镜头子系统的大致位置
  2. 在其后的区间里找「连续 4 字节、值落在 0x7D–0x7F」的指针数组
  3. 两版之间：mask ROM 镜像整体位移（E-PM2 +0x2AC/+0x288，E-M5 +0x2C0/+0x298），
     用「两版指针值集合的众数位移」归一化后再逐项比较
  4. 归一化后仍不同的项 = 语义改动（例如「换用哪一组 AF 参数」）

用法::

    python lens_rom_tables.py --pre pre.bin --post post.bin --base 0x402C0000
"""
import argparse
import collections
import struct

MAGIC = b"af_data_pos"
LO, HI = 0x7D000000, 0x80000000


def lens_region(d, base):
    i = d.find(MAGIC)
    if i < 0:
        raise SystemExit("未找到 af_data_pos 字符串")
    start = i
    end = min(len(d), i + 0x20000)
    return base + start, base + end, i


def pointer_runs(d, base, lo_off, hi_off, minlen=8):
    """区间内连续 4 字节对齐、值落在 mask ROM 的指针数组。"""
    res = []
    cur = []
    for off in range(lo_off - lo_off % 4, hi_off, 4):
        if off + 4 > len(d):
            break
        v = struct.unpack_from("<I", d, off)[0]
        if LO <= v < HI:
            cur.append((off, v))
        else:
            if len(cur) >= minlen:
                res.append(cur)
            cur = []
    if len(cur) >= minlen:
        res.append(cur)
    return [(base + c[0][0], [v for _, v in c]) for c in res]


def modal_shift(A_vals, B_vals, maxabs=0x2000):
    """求 B 相对 A 的众数位移。

    ROM 镜像在不同区段位移不同（E-PM2 有 +0x2AC 与 +0x288 两个插入点），
    所以位移必须**按表**计算，而不是全局一个值。
    做法：在两张表的取值集合之间统计所有差值，取出现次数最多且 |差值|<maxabs 的。
    """
    if not A_vals or not B_vals:
        return 0
    sA = set(A_vals)
    cnt = collections.Counter()
    for v in B_vals:
        for u in sA:
            dd = v - u
            if abs(dd) <= maxabs:
                cnt[dd] += 1
    if not cnt:
        return 0
    return cnt.most_common(1)[0][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--post", required=True)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x402C0000)
    ap.add_argument("--minlen", type=int, default=16)
    args = ap.parse_args()

    pre = open(args.pre, "rb").read()
    post = open(args.post, "rb").read()

    lo1, hi1, o1 = lens_region(pre, args.base)
    lo2, hi2, o2 = lens_region(post, args.base)
    print(f"pre : af_data_pos @0x{lo1:08X}   区间 0x{lo1:08X}-0x{hi1:08X}")
    print(f"post: af_data_pos @0x{lo2:08X}   区间 0x{lo2:08X}-0x{hi2:08X}")

    A = pointer_runs(pre, args.base, o1, min(len(pre), o1 + 0x20000), args.minlen)
    B = pointer_runs(post, args.base, o2, min(len(post), o2 + 0x20000), args.minlen)
    print(f"\npre 指针数组 {len(A)} 段 / post {len(B)} 段")

    # 用长度建立对应关系（同一张表在两版里长度不变）
    a_by_len = collections.defaultdict(list)
    for addr, vals in A:
        a_by_len[len(vals)].append((addr, vals))
    b_by_len = collections.defaultdict(list)
    for addr, vals in B:
        b_by_len[len(vals)].append((addr, vals))

    common_lens = sorted(set(a_by_len) & set(b_by_len), reverse=True)
    print(f"两版共有长度的表: {common_lens}\n")

    allvalsA = [v for _, vals in A for v in vals]
    allvalsB = [v for _, vals in B for v in vals]
    shift = modal_shift(allvalsA, allvalsB)
    print(f"mask ROM 镜像全局众数位移: {shift:+#x} ({shift:+d})\n")

    shown = 0
    for L in common_lens:
        for (aa, av), (ba, bv) in zip(a_by_len[L], b_by_len[L]):
            # 按表计算位移
            sh = modal_shift(av, bv)
            norm_b = [v - sh for v in bv]
            diff = [(i, av[i], norm_b[i]) for i in range(min(len(av), len(norm_b)))
                    if av[i] != norm_b[i]]
            if not diff:
                continue
            shown += 1
            print(f"=== 表 len={L}  pre@0x{aa:08X}  post@0x{ba:08X}  "
                  f"表内位移 {sh:+#x}  归一化后不同项 {len(diff)}/{L} ===")
            for i, x, y in diff[:40]:
                print(f"    [{i:3d}] pre 0x{x:08X}  ->  post(归一) 0x{y:08X}")
            if len(diff) > 40:
                print(f"    ... 共 {len(diff)} 项")
    print(f"\n归一化后仍有差异的表: {shown} 张")


if __name__ == "__main__":
    main()
