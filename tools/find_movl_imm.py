#!/usr/bin/env python3
"""在块 0 里精确扫描 `mov.l #imm, dN` 立即数。

MN10300 编码（本项目反汇编已验证）:
    `fc cX` + 4 字节小端立即数   ==   mov.l #imm, dX
    X 取 0..f，低位 d0..d15。
例:
    fc cc 06 00 00   -> mov.l #0x000006cc, d0
    fc cc 09 00 04 39-> mov.l #0x39040009, d0

用法:
    python tools/find_movl_imm.py --blk0 <块0> [--base 0x402C0020] \
        --imm 0x6cc 0x1c20 0x9d06 0x39040009 0x70000010
"""
import argparse
import re

RE = re.compile(rb"\xfc\xcc([0-9a-f])")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x402C0020)
    ap.add_argument("--imm", nargs="+", required=True)
    ap.add_argument("--ctx", type=int, default=0x18)
    ap.add_argument("--max", type=int, default=20)
    args = ap.parse_args()

    d = open(args.blk0, "rb").read()
    targets = {}
    for s in args.imm:
        targets[int(s, 0)] = []

    print("块 0: %s (%d 字节, base=0x%08X)" % (args.blk0, len(d), args.base))
    for m in RE.finditer(d):
        off = m.start()
        if off + 6 > len(d):
            continue
        imm = int.from_bytes(d[off + 2:off + 6], "little")
        if imm in targets:
            targets[imm].append((off, m.group(1).decode()))

    for imm in sorted(targets):
        hits = targets[imm]
        print("=== imm 0x%X (%d): %d 处 ===" % (imm, imm, len(hits)))
        for off, reg in hits[:args.max]:
            lo = max(0, off - 8)
            print("    @0x%08X  d%s   ctx: %s" % (
                args.base + off, reg, d[lo:off + 6 + args.ctx].hex(" ")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
