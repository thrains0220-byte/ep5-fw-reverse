#!/usr/bin/env python3
"""在块 1（UTF-16LE 多语言字符串池）里查找各艺术效果的 UI 名字。

目的：判断"未暴露的滤镜（artclearline / pastel_art / star_light / white_edge）"
      在块 1 里是否**已经有名字资源**（有 ⇒ 只需挂菜单；没有 ⇒ 还要在块 1 里加名字）。

用法: python block1_filter_names.py [block1.bin]
"""
import sys, re, collections

path = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\0_Project\01Test\ep5-fw-reverse\decoded\01_0101_427c0020.decoded.bin"
d = open(path, "rb").read()
N = len(d)
print(f"块 1: {N} B\n")

# 效果实现名 -> 可能出现在 UI 上的名字
CANDS = {
    "art_star_light":  ["Star Light", "Starlight", "StarLight"],
    "art_pinhole":     ["Pin Hole", "Pinhole", "PinHole"],
    "art_frame":       ["Frame"],
    "art_soft_focus":  ["Soft Focus", "SoftFocus"],
    "art_white_edge":  ["White Edge", "WhiteEdge"],
    "art_artclearline":["Clear Line", "ClearLine", "Clearline", "Clear Line Art",
                        "Line Art", "LineArt", "Clear Art"],
    "art_pastel_art":  ["Pastel", "Pastel Art", "PastelArt"],
    "art_filter_rough_monochrome": ["Grainy Film", "GrainyFilm", "Rough Monochrome",
                                    "RoughMono", "Monochrome", "B&W"],
    "art_filter_dramatic_tone":   ["Dramatic Tone", "DramaticTone", "Dramatic"],
    "art_diorama":     ["Diorama"],
    "art_filter_gentle_sepia":    ["Gentle Sepia", "GentleSepia"],
    "art_composite":   ["Pop Art", "PopArt", "Pop"],
    "art_mirror":      ["Cross Process", "CrossProcess"],
    "art_stl2ycc":     ["Pale&Light Color", "Pale & Light", "Light Tone"],
}

print("=== 效果 UI 名字在块 1 的检索 ===")
for eff, names in CANDS.items():
    found = []
    for nm in names:
        for enc, label in ((nm.encode("utf-16-le"), "utf16"), (nm.encode("ascii"), "ascii")):
            i = 0
            while True:
                k = d.find(enc, i)
                if k < 0:
                    break
                found.append((k, nm, label))
                i = k + 1
                if len(found) > 40:
                    break
    if found:
        seen = set()
        uniq = []
        for k, nm, lab in sorted(found):
            if (nm, lab) in seen:
                continue
            seen.add((nm, lab))
            uniq.append((k, nm, lab))
        print(f"\n  {eff}")
        for k, nm, lab in uniq[:8]:
            print(f"      0x{k:08X}  {lab:6s} {nm!r}")
    else:
        print(f"\n  {eff}\n      —— 块 1 中未找到 UI 名字")

# 反向：块 1 里所有含 "Art" 或常见滤镜词的 UTF-16 串
print("\n=== 块 1 中含 'Art' 的 UTF-16 串（抽样）===")
pat = re.compile((b"(?:[ -~]\x00){0,40}").__class__ and
                 rb"(?:[ -~]\x00){0,40}", re.I)
cnt = 0
for m in re.finditer(rb"(?:[ -~]\x00){6,60}", d):
    try:
        t = m.group().decode("utf-16-le")
    except Exception:
        continue
    if re.search(r"(?i)\b(art|pastel|clear ?line|grainy|diorama|pop art|soft focus|white edge|star light|monochrome)\b", t):
        cnt += 1
        if cnt <= 40:
            print(f"   0x{m.start():08X}  {t!r}")
print(f"   共 {cnt} 条")
