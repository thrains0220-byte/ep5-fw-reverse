#!/usr/bin/env python3
"""提取块 1 的「@A0xx@ 资源 ID 菜单项」全表，按语言分区列出。

Olympus 块 1 的菜单项文本形如  '@A03F@Pop-Art'  —— 前缀是字符串资源 ID，
后面是实际显示文本。同一菜单在不同语言分区会有不同的 ID。
本脚本按"分区"（连续区间）切分，输出每个分区的菜单项序列。

用法: python block1_menu.py [block1.bin]
"""
import sys, re, collections

path = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\01_0101_427c0020.decoded.bin"
d = open(path, "rb").read()
N = len(d)

# 找所有 UTF-16LE 串
strs = []
for m in re.finditer(rb"(?:[ -~]\x00){3,80}", d):
    try:
        t = m.group().decode("utf-16-le")
    except Exception:
        continue
    strs.append((m.start(), t))
print(f"块 1 UTF-16 串: {len(strs)} 条\n")

ITEM = re.compile(r"^@?(A0[0-9A-F]{2})@(.*)$", re.S)
items = [(off, ITEM.match(t).group(1), ITEM.match(t).group(2))
         for off, t in strs if ITEM.match(t)]
print(f"带 @A0xx@ 前缀的菜单项: {len(items)} 条\n")

# 按地址聚类成"分区"（间距 < 0x400 视为同一组）
groups = []
cur = []
for it in items:
    if cur and it[0] - cur[-1][0] > 0x400:
        groups.append(cur); cur = []
    cur.append(it)
if cur:
    groups.append(cur)
groups.sort(key=lambda g: -len(g))
print(f"分区分组（按间距<0x400 聚合）: {len(groups)} 个\n")

for gi, g in enumerate(groups[:6]):
    print("=" * 74)
    print(f"### 分区 {gi}  0x{g[0][0]:08X}..0x{g[-1][0]:08X}   {len(g)} 项")
    for off, rid, txt in g:
        print(f"   @{rid}  {txt[:64]!r}")
    print()

# 关注：艺术滤镜相关名字在哪些分区出现
TARGETS = ["Pop-Art", "Pop Art", "Diorama", "Dramatic Tone", "Soft Focus",
           "Pin Hole", "Grainy Film", "Cross Process", "Gentle Sepia",
           "Light Tone", "Pale&Light Color", "Star Light", "White Edge",
           "Pastel", "Clear Line", "Monochrome", "B&W", "Frame"]
print("=" * 74)
print("=== 各目标名字出现的资源 ID 与分区 ===")
for t in TARGETS:
    hits = [(rid, txt, gi) for gi, g in enumerate(groups) for off, rid, txt in g
            if txt.strip() == t]
    if hits:
        s = ", ".join(f"@{rid}(区{gi})" for rid, txt, gi in hits[:8])
        print(f"  {t:20s} x{len(hits):<3d} {s}")
    else:
        print(f"  {t:20s} —— 未出现在 @A0xx@ 菜单项中")
