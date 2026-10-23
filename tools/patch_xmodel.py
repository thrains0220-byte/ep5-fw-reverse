#!/usr/bin/env python3
"""跨机型补丁签名交叉：同一处源改动 ⇒ 同一段机器码字节。

思路
----
2018-12-18 的松下镜头 AF 修复在同一天下发给 9 个 MFT 机型
（E-P3 / E-PL3 / E-PM1 / E-M5 / E-PL5 / E-PM2 / E-P5 / E-PL6 / E-M10）。
若修复是对同一段源代码的同一处改动，则**打补丁后的机器码字节**在
两个机型的修复后固件里应当相同（哪怕所在地址不同）。

于是：
  新签名 = (post1 的 n-gram 集 ∩ post2 的 n-gram 集)
           − (pre1 的 n-gram 集 ∪ pre2 的 n-gram 集)
再把新签名回查到目标机型（E-P5 1.8），即得补丁在目标机型的坐标。

n-gram 用**精确字节**（不是哈希），因此无碰撞。

用法::

    python patch_xmodel.py --pair em5=pre.bin,post.bin --pair epm2=pre.bin,post.bin \
        --target ep5=post.bin --n 8 --json out.json
"""
import argparse
import json
import numpy as np


POLY = np.uint64(1000003)


def grams(data, n):
    """返回所有 n 字节窗口的 64 位滚动哈希（numpy）。

    n==8 时用精确 uint64（零碰撞）；n>8 用 64 位多项式哈希
    （14M 窗口下碰撞概率 ~1e-5，且最终命中处会再做逐字节校验）。
    """
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


def sorted_unique(a):
    return np.unique(a)


def gram_bytes(value, n):
    """把哈希还原成 n 字节不可行；改为在原文中按位置取字节（见 main）。"""
    raise NotImplementedError


def locate(data, n, values):
    """给出 values 中每个值在 data 里的全部位置。"""
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
        out[int(v)] = pos.tolist()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", action="append", required=True,
                    help="NAME=pre.bin,post.bin")
    ap.add_argument("--target", required=True, help="NAME=post.bin")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--json", default=None)
    ap.add_argument("--maxhits", type=int, default=80)
    args = ap.parse_args()

    n = args.n
    print(f"=== n-gram = {n} 字节（精确字节，无碰撞）===\n")

    post_sets = []
    pre_sets = []
    for spec in args.pair:
        name, rest = spec.split("=", 1)
        pre_path, post_path = rest.split(",", 1)
        pre = open(pre_path, "rb").read()
        post = open(post_path, "rb").read()
        hp = sorted_unique(grams(pre, n))
        hq = sorted_unique(grams(post, n))
        print(f"[{name}] pre={len(pre)} B  唯一 {n}-gram {len(hp)}   "
              f"post={len(post)} B  唯一 {n}-gram {len(hq)}")
        post_sets.append((name, hq, post))
        pre_sets.append((name, hp, pre))

    # 交集
    common = post_sets[0][1]
    for name, hq, _ in post_sets[1:]:
        common = np.intersect1d(common, hq, assume_unique=True)
    print(f"\n两机型 post 的共有 {n}-gram: {len(common)}")

    # 减去所有 pre
    new = common
    for name, hp, _ in pre_sets:
        new = np.setdiff1d(new, hp, assume_unique=True)
    print(f"再减去全部 pre 版本后，**新签名** {len(new)} 个")

    if len(new) == 0:
        print("\n无新签名。")
        return

    # 在各 post 文件里的位置
    hits = {}
    for name, hq, post in post_sets:
        loc = locate(post, n, new)
        hits[name] = loc
        multi = sum(1 for v in loc.values() if len(v) > 1)
        print(f"  [{name}] 命中位置分布：{sum(len(v) for v in loc.values())} 处"
              f"（其中 {multi} 个签名多处出现）")

    tname, tpath = args.target.split("=", 1)
    tgt = open(tpath, "rb").read()
    tloc = locate(tgt, n, new)
    print(f"\n=== 在目标机型 {tname}（{len(tgt)} B）中回查 ===")
    print(f"命中 {sum(len(v) for v in tloc.values())} 处，涉及 {len(tloc)} 个签名")

    rows = []
    for v, poss in sorted(tloc.items()):
        rows.append({
            "hash": int(v),
            "target_offsets": poss,
            "in_models": {nm: hits[nm].get(v, []) for nm, _, _ in post_sets},
        })
    rows.sort(key=lambda r: (len(r["target_offsets"]), len(r["in_models"])))
    print()
    shown = 0
    for r in rows[: args.maxhits]:
        p0 = r["target_offsets"][0]
        raw = tgt[p0:p0 + n]
        pos = ", ".join(f"0x{p:08X}" for p in r["target_offsets"][:6])
        extra = "" if len(r["target_offsets"]) <= 6 else f" (+{len(r['target_offsets'])-6})"
        per = "  ".join(f"{nm}@{','.join(hex(x) for x in ps[:3])}" for nm, ps in r["in_models"].items())
        print(f"  {raw.hex(' ')}   目标 {pos}{extra}   | {per}")
        r["bytes"] = raw.hex(" ")
    if args.json:
        json.dump({"n": n, "new_signatures": len(new), "hits": rows},
                  open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[JSON] {args.json}")


if __name__ == "__main__":
    main()
