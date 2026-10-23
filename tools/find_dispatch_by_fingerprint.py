#!/usr/bin/env python3
"""用「按 sxN 编号分派」比较链的字节指纹，在别的机型块 0 里定位同一函数。

背景（第二十轮）:
    社区改机补丁模式 A 的字节 `1c a0 06 c8 14 a0 03 c8 10 a0 08 c8`
    是一串 `cmp <编号>,d0 ; beq` 链，比较的编号 6 / 3 / 8 —— 与固件里的
    「函数目录」`sx0..sxF` 编号体系吻合
    （#3=stop_lens_force, #4=scan_lens, #6=scan_only_lens, #13=move_lens_ofset*）。
    ⇒ 这是**按函数编号分派**的 switch。

用法:
    python tools/find_dispatch_by_fingerprint.py \
        --ref  <参考块0> --ref-at 0x33399F \
        --targets <label=块0> ...
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="参考块 0")
    ap.add_argument("--ref-at", required=True, help="参考命中点（file offset，0x 开头）")
    ap.add_argument("--targets", nargs="+", required=True, help="label=块0路径")
    ap.add_argument("--len", type=lambda x: int(x, 0), default=0x30)
    ap.add_argument("--before", type=lambda x: int(x, 0), default=0x10)
    args = ap.parse_args()

    ref = open(args.ref, "rb").read()
    at = int(args.ref_at, 0)
    lo = at - args.before
    hi = at + args.len
    fp = ref[lo:hi]
    print("参考 %s @0x%X 的 %d 字节指纹:" % (args.ref, at, len(fp)))
    print("  " + fp.hex(" "))
    print()

    for t in args.targets:
        label, _, path = t.partition("=")
        d = open(path, "rb").read()
        hits = []
        i = 0
        while True:
            j = d.find(fp, i)
            if j < 0:
                break
            hits.append(j)
            i = j + 1
        print("%-16s 命中 %d 处: %s" % (
            label, len(hits), [hex(h) for h in hits[:6]]))
        for h in hits[:3]:
            # 打印整条比较链
            k = h + args.before
            end = k
            while end + 2 <= len(d) and end - k < 0x80:
                end += 1
            print("      @file 0x%08X : %s" % (h, d[h:h + 0x60].hex(" ")))


if __name__ == "__main__":
    main()
