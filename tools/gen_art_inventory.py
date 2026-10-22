#!/usr/bin/env python3
"""生成 E-P5/E-PM2 艺术（创意）滤镜子系统的完整清单（JSON + 文本）。

从块 0 中提取五类互相印证的静态证据：

  1. `art_effect_<NN>_<name>` 模块族   —— 效果 ID 空间 A（10/20/30/40/50）
  2. `art_filter_<HH>_<name>` 模块族   —— 效果 ID 空间 B（06/09/0E/14/19/1C/1D/21）
  3. `art_*.c` 源文件名                —— 每个模块的字符串块边界
  4. `MODE_EXPOSE_<name>` 名字表       —— 曝光/创意模式枚举（每项带 _MOVIE 孪生）
  5. `COLORTONE_<name>` 定宽名字表    —— 色彩色调列表（26 字节定宽记录）

用法:
    python gen_art_inventory.py --blk0 <blk0.bin> [--base 0x402C0000] [--out inv.json]
"""
import argparse
import json
import re
from collections import defaultdict


def printable_spans(d, lo, hi, minlen=4):
    spans = []
    i = lo
    n = min(hi, len(d))
    while i < n:
        j = i
        while j < n and 32 <= d[j] < 127:
            j += 1
        if j - i >= minlen:
            spans.append((i, d[i:j].decode("ascii")))
        while j < n and not (32 <= d[j] < 127):
            j += 1
        i = j
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    N = len(d)

    rx_effect = re.compile(r"art_effect_([0-9a-fA-F]{2})_([A-Za-z0-9_]+)")
    rx_filter = re.compile(r"art_filter_([0-9a-fA-F]{2})_([A-Za-z0-9_]+)")
    rx_src = re.compile(r"(art_[A-Za-z0-9_]+\.c)")
    rx_mode = re.compile(r"MODE_EXPOSE_([A-Z0-9_]+)")
    rx_tone = re.compile(r"COLORTONE_([A-Z0-9_]+)")

    eff = defaultdict(list)
    flt = defaultdict(list)
    srcs = []
    modes = []
    tones = []

    i = 0
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= 4:
            s = d[i:j].decode("ascii")
            for m in rx_effect.finditer(s):
                eff[int(m.group(1), 16)].append((base + i, m.group(0)))
            for m in rx_filter.finditer(s):
                flt[int(m.group(1), 16)].append((base + i, m.group(0)))
            for m in rx_src.finditer(s):
                srcs.append((base + i, m.group(1)))
            for m in rx_mode.finditer(s):
                modes.append((base + i, m.group(1)))
            for m in rx_tone.finditer(s):
                tones.append((base + i, m.group(1)))
            i = j + 1
        else:
            i = j + 1 if j > i else i + 1

    # 去重
    def uniq(lst):
        seen = set()
        out = []
        for a, b in lst:
            if (a, b) in seen:
                continue
            seen.add((a, b))
            out.append((a, b))
        return out

    eff = {k: uniq(v) for k, v in eff.items()}
    flt = {k: uniq(v) for k, v in flt.items()}
    srcs = uniq(srcs)
    modes = uniq(modes)
    tones = uniq(tones)

    res = {
        "source": {"file": args.blk0, "block0_base": "0x%08X" % base, "size": N},
        "namespace_A_art_effect_NN": {},
        "namespace_B_art_filter_HH": {},
        "source_modules": [],
        "mode_expose_names": [],
        "colortone_names": [],
    }

    print("=" * 84)
    print("命名空间 A —— art_effect_<NN>_<name>（效果 ID 空间 A）")
    print("=" * 84)
    for k in sorted(eff):
        names = sorted(set(x[1].split("_", 2)[2] for x in eff[k]))
        res["namespace_A_art_effect_NN"]["0x%02X" % k] = {
            "id": k, "names": names,
            "string_offsets": ["0x%08X" % a for a, _ in eff[k]]}
        print("  ID %3d (0x%02X)  %-16s  strings: %s" % (
            k, k, "/".join(names), ", ".join("0x%08X" % a for a, _ in eff[k][:3])))

    print()
    print("=" * 84)
    print("命名空间 B —— art_filter_<HH>_<name>（效果 ID 空间 B）")
    print("=" * 84)
    for k in sorted(flt):
        names = sorted(set(x[1].split("_", 2)[2] for x in flt[k]))
        res["namespace_B_art_filter_HH"]["0x%02X" % k] = {
            "id": k, "names": names,
            "string_offsets": ["0x%08X" % a for a, _ in flt[k]]}
        print("  ID %3d (0x%02X)  %-16s  strings: %s" % (
            k, k, "/".join(names), ", ".join("0x%08X" % a for a, _ in flt[k][:3])))

    print()
    print("=" * 84)
    print("源文件字符串（= 每个编译单元的字符串块边界）")
    print("=" * 84)
    for a, s in sorted(srcs):
        res["source_modules"].append({"offset": "0x%08X" % a, "name": s})
        print("  0x%08X  %s" % (a, s))

    print()
    print("=" * 84)
    print("MODE_EXPOSE_<name>（曝光/创意模式枚举，每项有 _MOVIE 孪生）")
    print("=" * 84)
    photo = [n for _, n in modes if not n.endswith("_MOVIE")]
    movie = [n for _, n in modes if n.endswith("_MOVIE")]
    res["mode_expose_names"] = {
        "photo": photo, "movie": movie,
        "photo_string_offsets": ["0x%08X" % a for a, n in modes if not n.endswith("_MOVIE")],
    }
    print("  拍照变体 %d 项: %s" % (len(photo), ", ".join(photo)))
    print("  录像变体 %d 项: %s" % (len(movie), ", ".join(x[:-6] for x in movie)))

    print()
    print("=" * 84)
    print("COLORTONE_<name>（色彩色调列表）")
    print("=" * 84)
    res["colortone_names"] = {
        "names": [n for _, n in tones],
        "string_offsets": ["0x%08X" % a for a, _ in tones],
    }
    print("  %d 项: %s" % (len(tones), ", ".join(n for _, n in tones)))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.out)


if __name__ == "__main__":
    main()
