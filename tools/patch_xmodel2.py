#!/usr/bin/env python3
"""跨机型补丁签名交叉（组语义版）。

判据
----
2018-12-18 的松下镜头 AF 修复同日下发给 9 个 MFT 机型。
把机型分成两组：

  post 组（已含修复）: E-M5 v2.3 / E-PM2 v1.6 / E-PL5 v1.6 / E-PL6 v1.4 /
                      E-M10 v1.4 / E-P3 v1.6 / E-PL3 v1.6 / E-PM1 v1.6 / E-P5 1.8
  pre  组（修复前）  : E-M5 v2.2 / E-PM2 v1.5.0.1 / E-PM2 v1.4.0.0

**真补丁字节**应当：出现在 post 组里、且不出现在 pre 组里。
再回查 E-P5 1.8 即得目标坐标。

也支持只用两个机型做交叉（--mode pair），用于观察。

用法::

    python patch_xmodel2.py --post A.bin B.bin C.bin --pre X.bin Y.bin \
        --target ep5=post.bin --n 16 --json out.json
"""
import argparse
import json
import numpy as np

POLY = np.uint64(1000003)


def grams(data, n):
    if len(data) < n:
        return np.empty(0, dtype="<u8")
    arr = np.frombuffer(data, dtype=np.uint8)
    if n == 8:
        w = np.lib.stride_tricks.sliding_window_view(arr, 8)
        return np.ascontiguousarray(w).view("<u8").ravel()
    w = np.lib.stride_tricks.sliding_window_view(arr, n)
    h = np.zeros(w.shape[0], dtype=np.uint64)
    for i in range(n):
        h = h * POLY + w[:, i].astype(np.uint64)
    return h


def locate(data, n, values):
    if len(values) == 0:
        return {}
    h = grams(data, n)
    order = np.argsort(h, kind="stable")
    hs = h[order]
    lo = np.searchsorted(hs, values, side="left")
    hi = np.searchsorted(hs, values, side="right")
    out = {}
    for i, v in enumerate(values):
        pos = order[lo[i]:hi[i]]
        if len(pos):
            out[int(v)] = pos.tolist()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", nargs="+", required=True, help="post=path 列表")
    ap.add_argument("--pre", nargs="+", required=True, help="pre=path 列表")
    ap.add_argument("--target", required=True)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--require-all-post", action="store_true",
                    help="要求签名在**所有** post 机型里都出现（默认：至少 2 个）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--maxhits", type=int, default=60)
    args = ap.parse_args()

    n = args.n
    print(f"=== n-gram = {n} 字节 ===\n")

    posts, pres = [], []
    for spec in args.post:
        name, path = spec.split("=", 1)
        d = open(path, "rb").read()
        g = np.unique(grams(d, n))
        posts.append((name, g, d))
        print(f"[post] {name:12s} {len(d):>9} B  唯一 {n}-gram {len(g)}")
    for spec in args.pre:
        name, path = spec.split("=", 1)
        d = open(path, "rb").read()
        g = np.unique(grams(d, n))
        pres.append((name, g, d))
        print(f"[pre ] {name:12s} {len(d):>9} B  唯一 {n}-gram {len(g)}")

    # post 组的交集（或按出现机型计数）
    if args.require_all_post:
        inter = posts[0][1]
        for name, g, _ in posts[1:]:
            inter = np.intersect1d(inter, g, assume_unique=True)
        print(f"\npost 组交集 {len(inter)}")
        cand = inter
    else:
        # 统计每个签名在多少个 post 机型里出现
        union = np.unique(np.concatenate([g for _, g, _ in posts]))
        counts = np.zeros(len(union), dtype=np.int32)
        for name, g, _ in posts:
            counts += np.isin(union, g, assume_unique=True).astype(np.int32)
        cand = union[counts >= 2]
        print(f"\npost 组并集 {len(union)}，出现在 ≥2 个机型的 {len(cand)}")

    for name, g, _ in pres:
        cand = np.setdiff1d(cand, g, assume_unique=True)
    print(f"再减去全部 pre 组后，**候选签名** {len(cand)}")

    if len(cand) == 0:
        print("\n无候选签名。")
        return

    tname, tpath = args.target.split("=", 1)
    tgt = open(tpath, "rb").read()
    tloc = locate(tgt, n, cand)
    print(f"\n=== 回查目标 {tname}（{len(tgt)} B）: 命中 {len(tloc)} 个签名 ===")

    # 每个候选在各 post 机型里的位置
    plocs = []
    for name, g, d in posts:
        plocs.append((name, locate(d, n, cand)))

    rows = []
    for v, poss in tloc.items():
        per = {}
        for (name, _), lc in zip(posts, plocs):
            if v in lc:
                per[name] = lc[v]
        if not per:
            continue
        rows.append({"bytes": tgt[poss[0]:poss[0] + n].hex(" "),
                     "target_offsets": poss, "in_models": per})
    rows.sort(key=lambda r: (len(r["target_offsets"]), -len(r["in_models"])))
    print(f"其中在 post 组里也命中的：{len(rows)}\n")
    for r in rows[: args.maxhits]:
        pos = ", ".join(f"0x{p:08X}" for p in r["target_offsets"][:8])
        extra = "" if len(r["target_offsets"]) <= 8 else f" (+{len(r['target_offsets'])-8})"
        per = "  ".join(f"{nm}@{','.join(hex(x) for x in ps[:2])}" for nm, ps in r["in_models"].items())
        print(f"  {r['bytes']}  目标 {pos}{extra}  | {per}")

    if args.json:
        json.dump({"n": n, "candidates": len(cand), "hits": rows},
                  open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[JSON] {args.json}")


if __name__ == "__main__":
    main()
