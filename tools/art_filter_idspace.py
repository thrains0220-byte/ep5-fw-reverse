#!/usr/bin/env python3
"""提取固件块内所有 `art_filter_<hex>_<name>` 形式的字符串，重建艺术滤镜 ID 空间。

背景:
    Olympus 固件把每个艺术滤镜处理任务命名为 `art_filter_<XX>_<name>`,
    其中 <XX> 是该滤镜在**全局滤镜 ID 空间**中的编号（十六进制, 两位）。
    这条命名把「ID ↔ 名字」直接编码进了固件自带的调试符号串，
    是目前唯一不依赖执行即可拿到的完整 ID↔名字映射证据。

用法:
    python art_filter_idspace.py --blk <blk.bin> [--base 0x402C0000]
                                 [--pattern 'art_filter_([0-9a-fA-F]{2})_(.*)']
"""
import argparse
import collections
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--pattern", default=r"art_filter_([0-9a-fA-F]{2})_([A-Za-z0-9_]+)")
    ap.add_argument("--also", action="append", default=[],
                    help="额外匹配的前缀, 例如 art_filter_dramatic_tone")
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    N = len(d)

    rx = re.compile(args.pattern)

    # 收集可打印字符串区间
    hits = collections.defaultdict(list)
    i = 0
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= 6:
            s = d[i:j].decode("ascii")
            for m in rx.finditer(s):
                fid = int(m.group(1), 16)
                hits[fid].append((base + i, m.group(0), s))
        i = j + 1 if j > i else i + 1

    print("块 %s  base=0x%08X" % (args.blk, base))
    print("匹配到 art_filter_<XX>_<name> 的字符串: %d 个不同编号\n" % len(hits))
    for fid in sorted(hits):
        for rt, full, whole in hits[fid][:3]:
            print("  ID 0x%02X (%3d)  %-40s  @0x%08X" % (fid, fid, full, rt))
            print("        完整串: %r" % whole[:120])
    print()
    print("ID 汇总: %s" % ", ".join("0x%02X" % f for f in sorted(hits)))
    print("缺号: %s" % ", ".join(
        "0x%02X" % f for f in range(0, max(hits) + 1) if f not in hits) if hits else "-")


if __name__ == "__main__":
    main()
