#!/usr/bin/env python3
"""在固件块中搜索若干函数地址是否出现在指针表里（块 0 数据段扫描）。

用法:
    python find_fn_ptr_refs.py --blk <blk.bin> --addrs 0x405d30dc,0x403e7e94
"""
import argparse
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--addrs", required=True)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    for tok in args.addrs.split(","):
        tgt = int(tok.strip(), 0)
        hits = []
        for delta in (0, 1):
            pat = struct.pack("<I", tgt + delta)
            i = 0
            while True:
                j = d.find(pat, i)
                if j < 0:
                    break
                hits.append(base + j)
                i = j + 1
        hits = sorted(set(hits))
        print("0x%08X -> %d 处: %s" % (tgt, len(hits), [hex(h) for h in hits[:8]]))


if __name__ == "__main__":
    main()
