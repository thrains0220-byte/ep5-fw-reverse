#!/usr/bin/env python3
"""对比社区补丁归档 stock 与 patched 的块 0，列出全部差异字节（含连续段）。

用途（第二十一轮）:
    确认「模式 A」社区补丁到底改了几处、各是什么。

用法:
    python tools/patch_diff.py --pairs "stock_dir=patched_dir" ...
    python tools/patch_diff.py --pairs ... --json out.json
"""
import argparse
import json
import os


def runs_of(diffs):
    if not diffs:
        return []
    out = []
    st = prev = diffs[0]
    for i in diffs[1:]:
        if i == prev + 1:
            prev = i
            continue
        out.append((st, prev))
        st = prev = i
    out.append((st, prev))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", required=True,
                    help="stock_dir=patched_dir")
    ap.add_argument("--ext", default=".bin")
    ap.add_argument("--json", default=None)
    ap.add_argument("--maxruns", type=int, default=12)
    args = ap.parse_args()

    report = []
    for pair in args.pairs:
        sd, _, pd = pair.partition("=")
        label = os.path.basename(sd.rstrip("\\/"))
        print("=" * 78)
        print("### %s   stock=%s  patched=%s" % (label, sd, pd))
        names = sorted(set(os.listdir(sd)) & set(os.listdir(pd)))
        for fn in names:
            if not fn.endswith(args.ext):
                continue
            a = open(os.path.join(sd, fn), "rb").read()
            b = open(os.path.join(pd, fn), "rb").read()
            if len(a) != len(b):
                print("  %-40s 长度不同 %d vs %d" % (fn, len(a), len(b)))
                continue
            diffs = [i for i in range(len(a)) if a[i] != b[i]]
            if not diffs:
                continue
            rr = runs_of(diffs)
            print("  %-40s %d 字节差异，%d 段" % (fn, len(diffs), len(rr)))
            for st, en in rr[:args.maxruns]:
                print("     off 0x%08X  len %d" % (st, en - st + 1))
                print("       stock  : %s" % a[st:en + 1].hex(" "))
                print("       patched: %s" % b[st:en + 1].hex(" "))
                report.append({
                    "model": label, "file": fn, "offset": st,
                    "len": en - st + 1,
                    "stock": a[st:en + 1].hex(" "),
                    "patched": b[st:en + 1].hex(" "),
                })
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print("[written] %s (%d 段)" % (args.json, len(report)))


if __name__ == "__main__":
    main()
