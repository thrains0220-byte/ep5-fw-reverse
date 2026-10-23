#!/usr/bin/env python3
"""精确挖 E-P5 块 0 里 [firmup] 子系统的文件名 / 目录 / 流程串（按原始字节顺序）。"""
import re

PATH = r"D:\0_Project\01Test\ep5-fw-reverse\decoded\00_0100_402c0020.decoded.bin"
BASE = 0x402C0000
d = open(PATH, "rb").read()

REGIONS = [
    ("固件文件名模板区", 0x405F1E80, 0x405F1F60),
    ("[firmup] 主流程区", 0x405F2080, 0x405F2200),
    ("C:\\WF* 文件名表区", 0x40DF3980, 0x40DF3A00),
]

for title, lo, hi in REGIONS:
    print("=" * 74)
    print("%s  0x%08X..0x%08X" % (title, lo, hi))
    o = lo - BASE
    blob = d[o:o + (hi - lo)]
    for m in re.finditer(rb"[\x20-\x7e]{4,}", blob):
        a = BASE + o + m.start()
        print("  0x%08X  %r" % (a, m.group().decode("latin-1")))
    print()

print("=" * 74)
print("=== 'E108????BIN' 附近的原始 96 字节 ===")
o = 0x405F1ED0 - BASE
print(d[o - 48:o + 48].hex(" "))
print()
for i in range(-48, 48, 16):
    a = 0x405F1ED0 + i
    print("  0x%08X  %s" % (a, d[o + i:o + i + 16].hex(" ")))
