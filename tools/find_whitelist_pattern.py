#!/usr/bin/env python3
"""在 E-P5 块 0 里找「镜头 ID 白名单」函数（社区补丁模式 A 第二处）的等价位置。

第二处补丁在 E-M1 III / E-M1 II / E-M1 等机型上都是：
    71 a1        MOV (A1),D0
    c8 XX        BEQ  +XX        ← 被补丁改成 cb cb (NOP NOP)
    80 01        MOV 0x1,D0
    f8 92 04     MOVBU D0,(0x4,SP)
语义：删掉「表尾哨兵 → 判定未识别」这条分支 ⇒ 镜头 ID 不在白名单也判为「已识别」。

本脚本用若干松紧不同的正则去 E-P5 块 0 里找同构位置。

用法:
    python tools/find_whitelist_pattern.py --blk0 <块0> [--base 0x402C0000]
"""
import argparse
import re

PATS = [
    ("tight  BEQ/BNE + MOV1 + MOVBU",
     re.compile(rb"\x71\xa1[\xc8\xc9][\x00-\xff]\x80\x01\xf8\x92\x04")),
    ("mid    BEQ/BNE + MOV1",
     re.compile(rb"[\xc8\xc9][\x00-\xff]\x80\x01\xf8\x92\x04")),
    ("movA1  MOV(A1),D0 + BEQ/BNE",
     re.compile(rb"\x71\xa1[\xc8\xc9][\x00-\xff]")),
    ("movA1+",
     re.compile(rb"\x71\xa1[\xc8\xc9][\x00-\xff]\x80\x01")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x402C0000)
    ap.add_argument("--ctx", type=int, default=16)
    args = ap.parse_args()

    b = open(args.blk0, "rb").read()
    print("块 0 %s (%d 字节, base=0x%08X)" % (args.blk0, len(b), args.base))
    for name, p in PATS:
        hits = [m.start() for m in p.finditer(b)]
        print("\n--- %s : %d 处 ---" % (name, len(hits)))
        for h in hits[:10]:
            lo = max(0, h - args.ctx)
            print("   0x%08X  %s" % (args.base + h, b[lo:h + 20].hex(" ")))


if __name__ == "__main__":
    main()
