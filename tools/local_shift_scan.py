#!/usr/bin/env python3
"""局部重同步法求局部位移：定位两版固件代码块里的所有「插入 / 删除」点。

原理
----
A、B 两版代码块大部分相同。若在偏移 x 附近 B 比 A 多出（插入）或少了（删除）
d 字节，则该点之后的对应关系整体平移 d。

算法
----
遍历 A 的所有差异区间；对每个区间，在其后方取一段 24 字节的「后续内容」，
在 B 的同一区域 ±W 字节内用 bytes.find 定位它 ⇒ 得到该区间的局部位移 d。
相邻区间的位移若不同 ⇒ 中间发生了插入/删除。

输出
----
* 位移分段表
* 全部插入/删除点（A 侧偏移、增删字节数、上下文 hexdump）

用法: local_shift_scan.py A.bin B.bin [--window 96] [--needle 24] [--out JSON]
"""
import sys, os, json, argparse, collections

VERBOSE_CTX = 12


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--window", type=int, default=96)
    ap.add_argument("--needle", type=int, default=24)
    ap.add_argument("--out", default="/tmp/local_shift.json")
    args = ap.parse_args()

    A = open(args.a, 'rb').read()
    B = open(args.b, 'rb').read()
    W, N = args.window, args.needle
    print(f"A {len(A)} B   B {len(B)} B   window=±{W} needle={N}")

    ivs = diff_intervals(A, B)
    print(f"差异区间 {len(ivs)}，差异字节 {sum(e-s for s,e in ivs)}")

    shifts = []
    for (s, e) in ivs:
        tail = A[e:e + N]
        if len(tail) < N:
            shifts.append(None)
            continue
        lo = max(0, s - W)
        hi = min(len(B), e + W)
        # B 中对应内容可能整体平移 d，tail 在 B 中的位置 ≈ e + d
        cand = B.find(tail, max(0, s - W), min(len(B), e + W))
        if cand < 0:
            shifts.append(None)
            continue
        shifts.append(cand - e)

    hist = collections.Counter(d for d in shifts if d is not None)
    print(f"\n局部位移取值 {len(hist)} 种：")
    for d, c in hist.most_common(20):
        print(f"  Δ={d:>+8}  × {c}")

    # 找出位移变化点 = 插入/删除
    ins = []
    prev = None
    for i, d in enumerate(shifts):
        if d is None:
            continue
        if prev is not None and d != prev[1]:
            s, e = ivs[prev[0]]
            ins.append({"a_offset": s, "a_end": e, "from_shift": prev[1],
                        "to_shift": d, "delta": d - prev[1],
                        "a_ctx": A[max(0, s - VERBOSE_CTX):s].hex(),
                        "b_ctx": B[max(0, s + prev[1] - VERBOSE_CTX):s + prev[1]].hex()})
        prev = (i, d)

    print(f"\n=== 插入/删除点：{len(ins)} 处 ===")
    tot = collections.Counter()
    for x in ins:
        tot[x["delta"]] += 1
    print("位移变化量分布：")
    for d, c in sorted(tot.items(), key=lambda kv: -abs(kv[0]) * kv[1])[:15]:
        print(f"  Δ{d:+}  × {c}")

    big = sorted(ins, key=lambda x: -abs(x["delta"]))
    print(f"\n--- 位移变化最大的 30 处 ---")
    for x in big[:30]:
        print(f"  A 0x{x['a_offset']:08X}..0x{x['a_end']:08X}  "
              f"{x['from_shift']:+} → {x['to_shift']:+}   (Δ{x['delta']:+})")
        print(f"     A ctx: {x['a_ctx']} | {A[x['a_offset']:x['a_end']].hex(' ')} | {A[x['a_end']:x['a_end']+VERBOSE_CTX].hex()}")
        print(f"     B ctx: {x['b_ctx']} | {B[x['a_offset']+x['from_shift']:x['a_end']+x['from_shift']].hex(' ')} | {B[x['a_end']+x['from_shift']:x['a_end']+x['from_shift']+VERBOSE_CTX].hex()}")

    json.dump({"a": args.a, "b": args.b,
               "shift_hist": [{"shift": d, "n": c} for d, c in hist.most_common()],
               "insert_delete_points": ins},
              open(args.out, "w"), indent=1)
    print(f"\n机读结果 → {args.out}")


if __name__ == '__main__':
    main()
