#!/usr/bin/env python3
"""判定两版固件代码块的字节差异，是「同一段代码被搬到别处（重链接）」，
还是「原地发生了真实改动」。

方法
----
两版文件长度相同 ⇒ 差异区间可以按文件偏移 1:1 对齐。把所有 A[i]!=B[i] 的
连续区间取出来（diff interval）。对每个区间，用「B 的定长块哈希索引」查它
是否原封不动地出现在 B 的另一个位置：

    若区间内容出现在 B 的 p 位置，则该区间只是搬移，位移 delta = p - s。

统计所有区间的 delta 直方图：
    * 若某个 delta 覆盖了绝大多数差异字节 ⇒ 差异是重链接，不是语义改动；
    * 剩余「无法用位移解释」的区间 ⇒ 候选真实改动点，逐条反汇编输出。

用法: relink_detect.py A.bin B.bin [--win 16] [--top 20] [--out unexplained.json]
"""
import sys, json, hashlib, collections, argparse


def diff_intervals(A, B, minlen=1):
    """返回 [(start, end)]，A[start:end] 与 B[start:end] 逐字节不同。"""
    out = []
    n = min(len(A), len(B))
    i = 0
    while i < n:
        if A[i] != B[i]:
            j = i
            # 用相邻块预筛加速：先跳到下一个不同处
            k = i + 1
            while k < n and A[k] != B[k]:
                k += 1
            j = k
            if j - i >= minlen:
                out.append((i, j))
            i = j
        else:
            i += 1
    if len(A) != len(B):
        out.append((min(len(A), len(B)), max(len(A), len(B))))
    return out


def build_index(B, win):
    """B 的所有 win 字节对齐块的哈希 → 偏移列表。"""
    idx = collections.defaultdict(list)
    for off in range(0, len(B) - win + 1, win):
        idx[hashlib.blake2b(B[off:off + win], digest_size=8).digest()].append(off)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--win", type=int, default=16)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out", default="/tmp/relink_unexplained.json")
    ap.add_argument("--maxlist", type=int, default=200)
    args = ap.parse_args()

    A = open(args.a, 'rb').read()
    B = open(args.b, 'rb').read()
    print(f"A = {args.a}  ({len(A)} B)")
    print(f"B = {args.b}  ({len(B)} B)")
    if len(A) != len(B):
        print("!! 长度不同：位移检测不适用（本工具假定等长）")
    win = args.win

    ivs = diff_intervals(A, B)
    ndiff = sum(e - s for s, e in ivs)
    print(f"\n差异区间 {len(ivs)} 个，差异字节 {ndiff} "
          f"({ndiff*100/max(len(A),1):.3f}%)")

    idx = build_index(B, win)
    delta_hist = collections.Counter()      # delta -> 覆盖字节数
    delta_iv = collections.Counter()        # delta -> 区间数
    explained = set()
    per_iv = []

    for (s, e) in ivs:
        L = e - s
        hit = None
        for w in (win, 8, 4):
            if L < w:
                continue
            key = hashlib.blake2b(A[s:s + w], digest_size=8).digest()
            cands = idx.get(key)
            if cands:
                hit = None
                for p in cands:
                    # 校验整段一致（只对候选做一次全段比较）
                    if p + L <= len(B) and B[p:p + L] == A[s:e]:
                        hit = p
                        break
                if hit is not None:
                    break
        if hit is not None:
            d = hit - s
            delta_hist[d] += L
            delta_iv[d] += 1
            explained.add((s, e))
            per_iv.append((s, e, d, hit))
        else:
            per_iv.append((s, e, None, None))

    tot_delta = sum(delta_hist.values())
    print(f"\n可由位移解释的字节：{tot_delta} / {ndiff} "
          f"({tot_delta*100/max(ndiff,1):.2f}%)")
    print(f"无法解释（候选真实改动）字节：{ndiff - tot_delta}")

    print(f"\n位移直方图（Top {args.top}）：")
    print(f"{'delta':>12} {'字节':>10} {'区间':>8}  {'占差异%':>8}")
    for d, cnt in delta_hist.most_common(args.top):
        print(f"{d:>12} {cnt:>10} {delta_iv[d]:>8}  {cnt*100/max(ndiff,1):>7.2f}%")

    unex = [(s, e) for (s, e, d, p) in per_iv if d is None]
    unex.sort(key=lambda x: -(x[1] - x[0]))
    print(f"\n候选真实改动区间：{len(unex)} 个，共 {sum(e-s for s,e in unex)} B")
    for s, e in unex[:40]:
        print(f"  A/B offset 0x{s:08X}..0x{e:08X}  len={e-s}")
        print(f"    A: {A[s:min(e,s+16)].hex(' ')}")
        print(f"    B: {B[s:min(e,s+16)].hex(' ')}")

    json.dump({"win": win, "total_diff_bytes": ndiff, "intervals": len(ivs),
               "explained_bytes": tot_delta,
               "deltas": [{"delta": d, "bytes": c, "intervals": delta_iv[d]}
                          for d, c in delta_hist.most_common()],
               "unexplained": [{"a_start": s, "a_end": e, "len": e - s,
                                "a_head": A[s:min(e, s + 32)].hex(),
                                "b_head": B[s:min(e, s + 32)].hex()}
                               for s, e in unex]},
              open(args.out, "w"), indent=1)
    print(f"\n机读结果 → {args.out}")


if __name__ == '__main__':
    main()
