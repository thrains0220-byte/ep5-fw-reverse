#!/usr/bin/env python3
"""按偏移顺序列出块 1 中某个语言分区内的字符串（含 @Axxx@ 资源 ID 标记）。

用法:
    python block1_dump_partition.py --blk1 <blk1.bin> --lo 0x353000 --hi 0x35C000
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk1", required=True)
    ap.add_argument("--lo", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--hi", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    raw = open(args.blk1, "rb").read()
    lo, hi = args.lo, args.hi
    txt = raw[lo:hi].decode("utf-16-le", errors="replace")

    n = 0
    i = 0
    while i < len(txt):
        j = txt.find("\x00", i)
        if j < 0:
            break
        s = txt[i:j]
        if s.strip():
            n += 1
            if n > args.max:
                print("... (截断)")
                break
            off = lo + i * 2
            print("0x%08X  %r" % (off, s[:100]))
        i = j + 1


if __name__ == "__main__":
    main()
