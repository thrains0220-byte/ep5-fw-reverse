#!/usr/bin/env python3
"""定位 AF 修复在 .BIN 里的唯一可见痕迹：`fcs_lens_mfts_move_lens_ofset_target`。

第十七轮结论：修复版（E-PM2 v1.6 / E-M5 v2.3）里
「全固件唯一签名 = `fcs_lens_mfts_move_lens_ofset_target` 被移除」。
若该字符串在修复前版本里存在、修复后消失，且它是一个**函数名**
（而非日志格式串），则**修复 = 删掉了一个做「镜头偏移」的函数**
⇒ 补丁方向反转：把该函数/其调用点改回去。

本脚本:
    1. 在多个块 0 里查该字符串（及其变体）；
    2. 打印它在修复前版本里的**邻域字符串**（判断它是函数名目录还是日志串）；
    3. 若邻域是「函数名目录」，继续统计同族函数名，得出被删的函数集合。

用法:
    python tools/find_af_fix_signature.py --targets <块0路径> ...
"""
import argparse
import re


def spans(d, minlen=4):
    out = []
    i = 0
    N = len(d)
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= minlen:
            out.append((i, d[i:j].decode("ascii")))
        i = j + 1 if j > i else i + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", required=True, help="label=块0路径")
    ap.add_argument("--name", default="fcs_lens_mfts_move_lens_ofset_target")
    ap.add_argument("--ctx", type=int, default=14, help="显示邻域串数")
    args = ap.parse_args()

    for t in args.targets:
        label, _, path = t.partition("=")
        d = open(path, "rb").read()
        sp = spans(d)
        names = [s for _, s in sp]
        idx = [i for i, s in enumerate(names) if args.name in s]
        print("=" * 100)
        print("%s   %s" % (label, path))
        if not idx:
            print("   ★ 未找到 `%s`" % args.name)
            # 找相近名字
            near = [s for s in names if "ofset" in s or "move_lens" in s]
            if near:
                print("   相近的名字: %s" % sorted(set(near))[:12])
            print()
            continue
        for i in idx:
            lo = max(0, i - args.ctx)
            hi = min(len(names), i + args.ctx + 1)
            print("   命中于第 %d 个字符串：" % i)
            for k in range(lo, hi):
                mark = " >>" if k == i else "   "
                print("     %s %s" % (mark, names[k]))
            print()


if __name__ == "__main__":
    main()
