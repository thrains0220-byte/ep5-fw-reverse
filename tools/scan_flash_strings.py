#!/usr/bin/env python3
"""从 E-P5 块 0 字符串里挖「机身 flash」线索：芯片/分区/容量/读写例程。

目的（第 28 轮）:
    `.BIN` 只有 42.75 MB，而机身 flash 更大；[firmup] 能更新 ARTFIL/BEAUTY/PIC/WAV/...
    ⇒ flash 里还有 `.BIN` 之外的数据分区。
    本脚本找出这些线索，好规划「拆机读 flash」的方案。
"""
import re
import struct

BIN = r"D:\0_Project\01Test\ep5-fw-reverse\decoded\00_0100_402c0020.decoded.bin"
BASE = 0x402C0000
d = open(BIN, "rb").read()

spans = [(m.start(), m.group().decode("latin-1"))
         for m in re.finditer(rb"[\x20-\x7e]{4,}", d)]


def show(title, pred, limit=60):
    sel = [(BASE + o, t) for o, t in spans if pred(t)]
    print("=== %s : %d 条 ===" % (title, len(sel)))
    for a, t in sel[:limit]:
        print("   0x%08X  %r" % (a, t))
    print()


show("flash / nor / spi / sfl",
     lambda t: re.search(r"flash|nor|spi|sfl|romdev|blockdev|parti", t, re.I))

show("分区 / 区域 / 块名",
     lambda t: re.search(r"partition|_part\b|partname|volume|vol_|region", t, re.I))

show("容量 / 大小单位",
     lambda t: re.search(r"flashsize|flash_size|capacity|total_size|MB\b|KB\b", t, re.I))

show("烧录 / 写入 flash",
     lambda t: re.search(r"write_flash|erase|program|burn|inject", t, re.I))

# u32 常量：可能的 flash 容量（字节）
print("=== 可能的容量常量（2 的幂，1MB..256MB）===")
caps = set()
for m in re.finditer(rb"\x00\x00\x00", d):
    pass
vals = collections_counter = {}
for off in range(0, len(d) - 3, 4):
    v = struct.unpack_from("<I", d, off)[0]
    if v in (1 << n for n in range(20, 29)):
        vals[v] = vals.get(v, 0) + 1
for v in sorted(vals):
    print("   0x%08X (%d MB)  出现 %d 次" % (v, v >> 20, vals[v]))
