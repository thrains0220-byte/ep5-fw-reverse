#!/usr/bin/env python3
"""按「带通配的指令序列」在固件块中搜索判定模式。

用于把社区改机补丁的字节特征（如 `1c a0 06 c8 ?? a0 03 c8 ?? a0 ?? c8`）
推广到别的机型，定位同一段源码的门控判定。

通配写法：`?` 代表任意单字节，`??` 任意两字节。

用法:
    python find_opcode_pattern.py --blk <blk.bin> --base 0x402C0000 \
        --pat "1c a0 06 c8 ? a0 03 c8 ?? a0 ?? c8" [--ctx 24]
"""
import argparse
import re


def build_re(pat):
    rx = []
    for tok in pat.split():
        if tok == "?":
            rx.append(b".")
        elif tok == "??":
            rx.append(b"..")
        else:
            rx.append(re.escape(bytes.fromhex(tok)))
    return re.compile(b"".join(rx), re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--pat", required=True)
    ap.add_argument("--ctx", type=int, default=24)
    ap.add_argument("--max", type=int, default=40)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk, "rb").read()
    rx = build_re(args.pat)
    print("模式: %s" % args.pat)
    print("块 %s  base 0x%08X  %d B" % (args.blk, base, len(d)))
    n = 0
    for m in rx.finditer(d):
        n += 1
        if n > args.max:
            print("...(截断)"); break
        s, e = m.start(), m.end()
        pre = d[max(0, s - args.ctx):s]
        post = d[e:e + args.ctx]
        print("  rt 0x%08X  file 0x%08X" % (base + s, s))
        print("      命中: %s" % d[s:e].hex(" "))
        print("      前:   %s" % pre.hex(" "))
        print("      后:   %s" % post.hex(" "))
    print("命中 %d 处" % n)


if __name__ == "__main__":
    main()
