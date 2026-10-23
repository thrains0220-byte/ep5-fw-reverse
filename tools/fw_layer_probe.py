#!/usr/bin/env python3
"""阶段 1：固件「未知层」探针（差分探针 / 引导桩 / 块头结构 / 索引表）。

用法::

    # 单文件结构探针（方法 B/C/D）
    python fw_layer_probe.py --file fw.bin --out probe.json

    # 双版本差分探针（方法 A）
    python fw_layer_probe.py --file a.bin --file2 b.bin --tag a,b --out probe.json

四个方法（对应逆向规划阶段 1）：

  A 差分探针
      变化字节是否对齐到 4KB / 16KB / 64KB 网格；
      变化是否只集中在块尾；
      64KB 网格上「整片 0xFF」与「高熵」是否交替出现。
  B 引导桩 / 异常向量表
      ARM 风格：连续 4 字节对齐、字首在 0xE1/0xE3/0xE5/0xEA 的指令序列；
      MN103 风格：连续 2 字节对齐、opcode 落在 0xC0-0xCF 分支族的指令序列。
  C 块头结构
      每个 4KB/16KB/64KB 网格点后 12 字节里找 {压缩长度, 原始长度, CRC} 三元组。
  D 索引表
      4 字节对齐的 u32 序列，单调递增，且末值与分区大小自洽。
"""
import argparse
import collections
import json
import math
import struct
import sys

GRIDS = (4096, 16384, 65536)


def entropy(buf):
    if not buf:
        return 0.0
    c = collections.Counter(buf)
    n = len(buf)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def grid_profile(data, grid):
    """每个网格点：熵、是否整片 0xFF、整片 0x00。"""
    out = []
    for g in range(0, len(data), grid):
        blk = data[g:g + grid]
        out.append({
            "off": g,
            "len": len(blk),
            "ent": round(entropy(blk), 3),
            "all_ff": len(blk) == grid and blk.count(0xFF) == len(blk),
            "all_00": len(blk) == grid and blk.count(0x00) == len(blk),
        })
    return out


def method_a(diff_offsets, total):
    """变化分布：网格对齐率、是否集中在尾部。"""
    res = {}
    for g in GRIDS:
        hit = sum(1 for o in diff_offsets if o % g == 0)
        res[f"aligned_{g}"] = hit
        res[f"ratio_{g}"] = round(hit / max(1, len(diff_offsets)), 4)
    if diff_offsets:
        lo, hi = min(diff_offsets), max(diff_offsets)
        res["span_start"] = lo
        res["span_end"] = hi
        res["span_len"] = hi - lo + 1
        res["span_ratio"] = round((hi - lo + 1) / max(1, total), 4)
        # 最后 1% 区域内的变化占比
        tail = max(1, total // 100)
        res["tail_1pct_changes"] = sum(1 for o in diff_offsets if o >= total - tail)
        res["tail_1pct_ratio"] = round(res["tail_1pct_changes"] / max(1, len(diff_offsets)), 4)
    else:
        res["span_start"] = res["span_end"] = res["span_len"] = 0
        res["span_ratio"] = 0.0
        res["tail_1pct_changes"] = 0
        res["tail_1pct_ratio"] = 0.0
    return res


ARM_VEC = {0xE1, 0xE3, 0xE5, 0xEA}


def method_b(data):
    """找异常向量表 / 引导桩：ARM 风格与 MN103 风格各扫一遍。"""
    arm = []
    tops = {x << 24 for x in ARM_VEC}
    for g in range(0, len(data) - 4 * 8, 4):
        ws = struct.unpack_from("<8I", data, g)
        if all((w & 0xFF000000) in tops for w in ws):
            arm.append(g)
    # 合并相邻
    def merge(xs):
        out = []
        for x in xs:
            if out and x == out[-1][1] + 4:
                out[-1][1] = x
            else:
                out.append([x, x])
        return [tuple(x) for x in out]

    mn = []
    for g in range(0, len(data) - 2 * 8, 2):
        ops = [data[g + 2 * i] for i in range(8)]
        if all(0xC0 <= o <= 0xCF for o in ops):
            mn.append(g)
    return {"arm_vector_runs": merge(arm)[:40],
            "mn103_branch_runs": merge(mn)[:40],
            "arm_run_count": len(merge(arm)),
            "mn103_run_count": len(merge(mn))}


def method_c(data, sizes):
    """网格点后 12 字节里的 {压缩长度, 原始长度, CRC} 三元组。"""
    hits = []
    for g in GRIDS:
        for off in range(0, len(data) - 12, g):
            a, b, c = struct.unpack_from("<III", data, off)
            if 0 < a < b and 0 < c and c < (1 << 31):
                # 自洽性：b 与某分区大小同量级，且 off+a 不越界
                if b in sizes or any(abs(b - s) <= s // 8 for s in sizes):
                    hits.append({"grid": g, "off": off, "comp": a, "raw": b, "crc": c})
            a16, b16, c16 = struct.unpack_from("<HHH", data, off)
            if 0 < a16 < b16 and 0 < c16 and b16 in sizes:
                hits.append({"grid": g, "off": off, "comp16": a16, "raw16": b16, "x16": c16})
    return hits[:200]


def method_d(data, sizes):
    """索引表：单调递增的 u32 序列，末值与分区大小自洽。"""
    hits = []
    n = len(data) // 4
    arr = struct.unpack_from(f"<{n}I", data, 0) if n else ()
    i = 0
    while i < n:
        j = i
        while j + 1 < n and arr[j + 1] > arr[j] and arr[j + 1] - arr[j] < (1 << 24):
            j += 1
        if j - i >= 7:
            last = arr[j]
            for s in sizes:
                if last and abs(last - s) <= s // 4:
                    hits.append({"off": i * 4, "count": j - i + 1,
                                 "first": arr[i], "last": last, "part_size": s})
                    break
        i = max(j + 1, i + 1)
    return hits[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--file2", default=None)
    ap.add_argument("--tag", default="a,b")
    ap.add_argument("--out", default=None)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0)
    args = ap.parse_args()

    A = open(args.file, "rb").read()
    ta, tb = (args.tag.split(",") + ["b"])[:2]
    print(f"[{ta}] {args.file}  {len(A):,} B")
    sizes = [len(A)]

    out = {"file": args.file, "size": len(A), "tag": ta}

    if args.file2:
        B = open(args.file2, "rb").read()
        print(f"[{tb}] {args.file2}  {len(B):,} B")
        out["file2"] = args.file2
        out["size2"] = len(B)
        out["tag2"] = tb
        n = min(len(A), len(B))
        diffs = [i for i in range(n) if A[i] != B[i]]
        print(f"\n=== 方法 A：差分探针（{len(diffs):,} 个不同字节 / {n:,}）===")
        ma = method_a(diffs, n)
        out["method_a"] = ma
        for k, v in ma.items():
            print(f"   {k}: {v}")

    print("\n=== 方法 B：引导桩 / 异常向量表 ===")
    mb = method_b(A)
    out["method_b"] = mb
    print(f"   ARM 风格向量段 {mb['arm_run_count']} 个（示例 {mb['arm_vector_runs'][:5]}）")
    print(f"   MN103 分支族段 {mb['mn103_run_count']} 个（示例 {mb['mn103_branch_runs'][:5]}）")

    print("\n=== 方法 C：网格点后的 {压缩长, 原始长, CRC} 三元组 ===")
    mc = method_c(A, sizes)
    out["method_c"] = mc
    print(f"   命中 {len(mc)} 处（示例 {mc[:5]}）")

    print("\n=== 方法 D：索引表（单调 u32 序列）===")
    md = method_d(A, sizes)
    out["method_d"] = md
    print(f"   命中 {len(md)} 处（示例 {md[:5]}）")

    print("\n=== 64KB 网格熵剖面（找 0xFF/高熵交替 = 块边界）===")
    prof = grid_profile(A, 65536)
    out["grid64k"] = prof
    alt = sum(1 for p in prof if p["all_ff"] or p["all_00"])
    hi = sum(1 for p in prof if p["ent"] > 7.5)
    print(f"   64KB 网格 {len(prof)} 个；整片填充 {alt} 个；高熵(>7.5) {hi} 个")
    seq = "".join("F" if p["all_ff"] else ("0" if p["all_00"] else ("H" if p["ent"] > 7.5 else "."))
                  for p in prof)
    print(f"   模式（前 200 格）: {seq[:200]}")

    if args.out:
        json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[JSON] {args.out}")


if __name__ == "__main__":
    main()
