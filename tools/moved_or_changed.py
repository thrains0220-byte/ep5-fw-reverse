#!/usr/bin/env python3
"""区域级「搬走 vs 真改」判定。

问题：两版固件代码块里有大片差异字节，它们是同一段内容被搬到了别处
（重链接），还是内容真的变了？

做法
----
1. 先算出所有差异区间。
2. 把差异区间按「距离 ≤GAP 就合并」聚成若干**变化区**（zone）。
3. 对每个 zone：
   * 取 A 侧 zone 前后各留 CONTEXT 字节的窗口 W_A；
   * 在 B 里精确查找 W_A：
       - 找到 ⇒ 该 zone 只是被搬走（给出 B 侧位置与位移）；
       - 找不到 ⇒ 该 zone 内容真的变了（真改动候选）。
4. 输出真改动区清单。

用法: moved_or_changed.py A.bin B.bin [--gap 64] [--context 16] [--out JSON]
"""
import sys, os, json, argparse, collections


def diff_intervals(A, B):
    out = []
    n = min(len(A), len(B))
    i = 0
    while i < n:
        if A[i] != B[i]:
            k = i + 1
            while k < n and A[k] != B[k]:
                k += 1
            out.append((i, k))
            i = k
        else:
            i += 1
    return out


def merge(ivs, gap):
    out = []
    for s, e in ivs:
        if out and s - out[-1][1] <= gap:
            out[-1][1] = e
        else:
            out.append([s, e])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--gap", type=int, default=64)
    ap.add_argument("--context", type=int, default=16)
    ap.add_argument("--out", default="/tmp/moved_or_changed.json")
    args = ap.parse_args()

    A = open(args.a, 'rb').read()
    B = open(args.b, 'rb').read()
    ivs = diff_intervals(A, B)
    zones = merge(ivs, args.gap)
    ndiff = sum(e - s for s, e in ivs)
    print(f"A {len(A)} B  B {len(B)} B")
    print(f"差异字节 {ndiff}，区间 {len(ivs)}，聚成 {len(zones)} 个变化区")

    moved, changed = [], []
    for (s, e) in zones:
        lo = max(0, s - args.context)
        hi = min(len(A), e + args.context)
        W = A[lo:hi]
        pos = B.find(W)
        if pos >= 0:
            moved.append({"a_start": lo, "a_end": hi, "b_pos": pos,
                          "shift": pos - lo, "diff_len": e - s})
        else:
            changed.append({"a_start": s, "a_end": e, "diff_len": e - s,
                            "a_head": A[s:min(e, s + 24)].hex(),
                            "b_head": B[s:min(e, s + 24)].hex()})

    print(f"\n被搬走（可精确匹配到别处）: {len(moved)} 区，"
          f"覆盖差异字节 {sum(m['diff_len'] for m in moved)}")
    print(f"真改动（找不到对应内容）  : {len(changed)} 区，"
          f"覆盖差异字节 {sum(m['diff_len'] for m in changed)}")

    sh = collections.Counter(m["shift"] for m in moved)
    print("\n搬移位移分布（Top 15）：")
    for d, c in sh.most_common(15):
        b = sum(m['diff_len'] for m in moved if m['shift'] == d)
        print(f"  Δ={d:>+10}  区={c:<6} 覆盖差异 {b:>9} B")

    changed.sort(key=lambda x: -x["diff_len"])
    print(f"\n--- 真改动区 Top 40 ---")
    for z in changed[:40]:
        print(f"  0x{z['a_start']:08X}..0x{z['a_end']:08X}  len={z['diff_len']}")
        print(f"     A: {z['a_head']}")
        print(f"     B: {z['b_head']}")

    json.dump({"a": args.a, "b": args.b, "diff_bytes": ndiff,
               "zones": len(zones),
               "moved_zones": moved, "changed_zones": changed,
               "moved_shift_hist": [{"shift": d, "n": c} for d, c in sh.most_common()]},
              open(args.out, "w"), indent=1)
    print(f"\n机读结果 → {args.out}")


if __name__ == '__main__':
    main()
