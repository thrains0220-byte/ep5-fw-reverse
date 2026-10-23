#!/usr/bin/env python3
"""在块 0 里搜「从 mask ROM 拷一段数据到栈上」的循环模板。

编码（第 21 轮由 Ghidra 反汇编 + 原始字节对齐确定）:
    85 XX        MOV #XX, D1      ; 拷贝长度（0xD0 = -48 = 48 字节 = 12 个 u32）
    db f0        SETLB
    41 45        MOVBU (A1), D0
    f0           INC A1
    50           MOVBU D0, (A0)
    41           INC A0
    44           INC D1
    d9           LNE

社区补丁第二处（镜头 ID 白名单）就在这样一个「先从 ROM 拷表、再线性扫描」的函数里。
本脚本列出所有该模板的出现点，并报告其源地址（拷贝前几条指令里的立即数）。

用法:
    python tools/find_rom_copy_loop.py --blk0 <块0> --base 0x402C0000 [--len 0xd0]
"""
import argparse
import re

TPL = re.compile(rb"\x85([\x00-\xff])\xdb\xf0\x41\x45\xf0\x50\x41\x44\xd9")
# 拷表源地址通常形如 fc dc XX XX XX XX (MOV #imm32, A0) 或 fc dc / 8x XX XX XX XX
LOAD32 = re.compile(rb"\xfc[\xc0-\xdf]([\x00-\xff]{4})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x402C0000)
    ap.add_argument("--len", type=lambda x: int(x, 0), default=None,
                    help="只报告长度为该值的拷贝")
    ap.add_argument("--mask", default="0x7e",
                    help="源地址前缀（十六进制），用于筛 mask ROM")
    ap.add_argument("--ctx", type=int, default=16)
    ap.add_argument("--max", type=int, default=40)
    args = ap.parse_args()

    d = open(args.blk0, "rb").read()
    mask = int(args.mask, 16)
    print("块 0 %s (%d 字节, base=0x%08X)" % (args.blk0, len(d), args.base))

    n = 0
    for m in TPL.finditer(d):
        ln = m.group(1)[0]
        if args.len is not None and ln != args.len:
            continue
        n += 1
        lo = max(0, m.start() - args.ctx)
        # 在模板前方找最近的 32 位立即数加载
        src = None
        for lm in LOAD32.finditer(d, max(0, m.start() - 24), m.start()):
            v = int.from_bytes(lm.group(1), "little")
            src = v
        tag = ""
        if src is not None:
            tag = "  src=0x%08X%s" % (src, "  <== mask ROM" if (src >> 24) == mask else "")
        print("  0x%08X  len=%d (0x%02X)%s" % (
            args.base + m.start(), ln, ln, tag))
        print("      ctx: %s" % d[lo:m.start() + 12].hex(" "))
        if n >= args.max:
            break
    print("\n合计 %d 处（长度过滤 len=%s）" % (n, args.len))


if __name__ == "__main__":
    main()
