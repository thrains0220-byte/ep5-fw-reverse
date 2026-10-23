#!/usr/bin/env python3
"""把 Ghidra 反汇编与块 0 原始字节对齐，反推 MN10300 助记符 <-> opcode 映射。

用法:
    python tools/opcode_map.py --blk0 <块0> --base 0x402C0000 --disasm <disasm.txt>
"""
import argparse
import collections
import re

RX = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+\S+\s+(.+?)\s*$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--disasm", required=True)
    ap.add_argument("--prefix", default=None,
                    help="只看 opcode 以此前缀开头的指令，如 cb")
    args = ap.parse_args()

    d = open(args.blk0, "rb").read()
    lines = open(args.disasm, encoding="utf-8", errors="replace").read().splitlines()
    rows = []
    for l in lines:
        m = RX.match(l)
        if not m:
            continue
        rows.append((int(m.group(1), 16), m.group(2).strip()))

    table = collections.defaultdict(collections.Counter)
    for i, (addr, txt) in enumerate(rows):
        off = addr - args.base
        if off < 0 or off >= len(d):
            continue
        op = d[off]
        mn = txt.split()[0].upper()
        table[op][mn] += 1

    print("opcode -> 助记符 统计（Ghidra 反汇编对齐原始字节）")
    print("-" * 70)
    for op in sorted(table):
        if args.prefix and not ("%02x" % op).startswith(args.prefix.lower()):
            continue
        items = ", ".join("%s x%d" % (m, c) for m, c in table[op].most_common())
        print("  0x%02X : %s" % (op, items))


if __name__ == "__main__":
    main()
