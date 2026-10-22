#!/usr/bin/env python3
"""扫描固件块内的字符串，并定位其 32 位地址引用（MN103 `fc <imm32>` 立即数）。

用途:
  1. 列出指定运行时区间内所有可打印字符串;
  2. 对每个字符串, 在整块内搜索其 4 字节 LE 地址, 区分
     - `fc` 前缀 = mov imm32 (真正的代码引用)
     - 裸 4 字节 = 数据表指针
  3. 可选按名字白名单过滤, 只输出关心的效果名。

用法:
    python art_name_map.py --blk0 <blk0.bin> [--base 0x402C0000]
                           [--lo 0x40AB0000] [--hi 0x40AB3000]
                           [--names POPART,PASTEL,...] [--ctx 32]
"""
import argparse
import struct


def extract_strings(data, lo, hi, minlen=3):
    """返回 [(offset, string)]，offset 为绝对 file offset。"""
    out = []
    i = lo
    n = len(data)
    while i < min(hi, n):
        j = i
        while j < min(hi, n) and 32 <= data[j] < 127:
            j += 1
        if j - i >= minlen:
            out.append((i, data[i:j].decode("ascii")))
        # 跳到下一个可打印串
        while j < min(hi, n) and not (32 <= data[j] < 127):
            j += 1
        i = j
    return out


def find_refs(data, rt, code_lo, code_hi):
    """在 [code_lo, code_hi) 内查找 4 字节 LE 地址 rt。返回 [(offset, kind)]。"""
    pat = struct.pack("<I", rt)
    res = []
    start = code_lo
    while True:
        k = data.find(pat, start, code_hi)
        if k < 0:
            break
        kind = "code-mov" if (k >= 2 and data[k - 2] == 0xFC) else "data-ptr"
        res.append((k, kind))
        start = k + 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--lo", default=None, help="运行时起点")
    ap.add_argument("--hi", default=None, help="运行时终点")
    ap.add_argument("--names", default=None, help="逗号分隔名字白名单")
    ap.add_argument("--ctx", type=int, default=24, help="引用点上下文字节数")
    ap.add_argument("--code-lo", default=None)
    ap.add_argument("--code-hi", default=None)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    N = len(d)

    lo = int(args.lo, 0) - base if args.lo else 0
    hi = int(args.hi, 0) - base if args.hi else N
    clo = int(args.code_lo, 0) - base if args.code_lo else 0
    chi = int(args.code_hi, 0) - base if args.code_hi else N

    whitelist = None
    if args.names:
        whitelist = set(s.strip() for s in args.names.split(",") if s.strip())

    strings = extract_strings(d, lo, hi)
    print("区间 0x%08X..0x%08X  内字符串 %d 条\n" % (base + lo, base + hi, len(strings)))

    total_refs = 0
    for off, s in strings:
        if whitelist is not None and s not in whitelist:
            continue
        rt = base + off
        refs = find_refs(d, rt, clo, chi)
        if not refs:
            continue
        total_refs += len(refs)
        print("0x%08X  %-28s (%2d refs)" % (rt, s[:28], len(refs)))
        for k, kind in refs:
            ctx = d[max(0, k - args.ctx):k + 4 + args.ctx]
            print("    %-9s @0x%08X   ctx=%s" % (kind, base + k, ctx.hex()))
        print()
    print("合计引用: %d" % total_refs)


if __name__ == "__main__":
    main()
