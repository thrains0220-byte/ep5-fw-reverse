#!/usr/bin/env python3
"""跨机型艺术滤镜 ID 空间图谱。

目的:
    第十四轮在 E-P5 上清点出 **13 个实现模块**（两套 ID 命名空间），
    但那是单机视角。本脚本对**所有可用的解码块 0**做同样的清点，
    产出「Olympus 全系艺术滤镜 ID 空间图谱」：
      * 每个 ID 在哪些机型上被实现、名字是什么
      * **E-P5 缺失、但别的机型实现了**的 ID 清单
        —— 这是「能不能从别的机型搬一个滤镜过来」的第一手依据

同时抽取每个机型的 `COLORTONE_*` / `MODE_EXPOSE_*` 名单，便于横向对照菜单体系。

用法:
    python tools/cross_model_art_map.py --roots <decoded块0目录> [...] --json out.json
    # 或直接扫一个目录树：
    python tools/cross_model_art_map.py --scan D:\\0_Project\\01Test --json out.json
"""
import argparse
import collections
import glob
import json
import os
import re
import struct

RX_EFFECT = re.compile(rb"art_effect_([0-9a-fA-F]{2})_([A-Za-z0-9_]+)")
RX_FILTER = re.compile(r"art_filter_([0-9a-fA-F]{2})_([A-Za-z0-9_]+)".encode())
RX_SRC = re.compile(rb"(art_[A-Za-z0-9_]+\.c)")
RX_TONE = re.compile(rb"COLORTONE_([A-Z0-9_]+)")
RX_MODE = re.compile(rb"MODE_EXPOSE_([A-Z0-9_]+)")


def scan(path):
    d = open(path, "rb").read()
    eff = collections.defaultdict(set)
    flt = collections.defaultdict(set)
    srcs = set()
    tones = []
    modes = []
    i = 0
    N = len(d)
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= 6:
            s = d[i:j]
            for m in RX_EFFECT.finditer(s):
                eff[int(m.group(1), 16)].add(m.group(2).decode())
            for m in RX_FILTER.finditer(s):
                flt[int(m.group(1), 16)].add(m.group(2).decode())
            for m in RX_SRC.finditer(s):
                srcs.add(m.group(1).decode())
            for m in RX_TONE.finditer(s):
                tones.append(m.group(1).decode())
            for m in RX_MODE.finditer(s):
                modes.append(m.group(1).decode())
            i = j + 1
        else:
            i = j + 1 if j > i else i + 1
    return {
        "file": path,
        "size": N,
        "namespace_A": {("0x%02X" % k): sorted(v) for k, v in sorted(eff.items())},
        "namespace_B": {("0x%02X" % k): sorted(v) for k, v in sorted(flt.items())},
        "source_modules": sorted(srcs),
        "colortone": sorted(set(tones)),
        "mode_expose": sorted(set(modes)),
    }


def label_for(path):
    b = os.path.basename(path)
    if "402c0020" in b:
        return "E-P5/E-PM2 (" + os.path.basename(os.path.dirname(path)) + ")"
    m = re.search(r"00_0100_([0-9a-f]{8})", b)
    tag = m.group(1) if m else "?"
    return "%s (%s)" % (tag, os.path.basename(os.path.dirname(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=None, help="递归扫描目录找解码块 0")
    ap.add_argument("--roots", nargs="*", default=[])
    ap.add_argument("--json", default=None)
    ap.add_argument("--ref", default=None, help="参考机型（用于算缺失清单）")
    args = ap.parse_args()

    files = []
    if args.scan:
        pat = os.path.join(args.scan, "**", "00_0100_*.decoded.bin")
        files = sorted(glob.glob(pat, recursive=True))
    for r in args.roots:
        files.extend(sorted(glob.glob(os.path.join(r, "**", "00_0100_*.decoded.bin"),
                                recursive=True)))
    # 去重：按完整路径（不同机型可能同名同尺寸，必须靠父目录区分）
    seen = set()
    uniq = []
    for f in files:
        k = os.path.abspath(f)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)
    print("扫描到 %d 个解码块 0\n" % len(uniq))

    rows = []
    for f in uniq:
        r = scan(f)
        r["label"] = label_for(f)
        rows.append(r)
        print("%-40s  A:%-2d B:%-2d  模块:%-3d COLORTONE:%-3d MODE_EXPOSE:%-3d" % (
            r["label"][:40], len(r["namespace_A"]), len(r["namespace_B"]),
            len(r["source_modules"]), len(r["colortone"]), len(r["mode_expose"])))

    # 全系 ID 空间
    id2name = collections.defaultdict(dict)
    id2models = collections.defaultdict(set)
    for r in rows:
        for ns, key in (("A", "namespace_A"), ("B", "namespace_B")):
            for kid, names in r[key].items():
                for nm in names:
                    id2name[ns][kid] = nm
                id2models[(ns, kid)].add(r["label"])

    print("\n=== 全系艺术滤镜 ID 空间 ===")
    for ns in ("A", "B"):
        print("  命名空间 %s:" % ns)
        for kid in sorted(id2name[ns]):
            ms = sorted(id2models[(ns, kid)])
            print("    %-6s %-20s  %d 个机型  %s" % (
                kid, id2name[ns][kid], len(ms),
                ", ".join(ms[:6]) + ("…" if len(ms) > 6 else "")))

    # 缺失分析
    if args.ref:
        ref = next((r for r in rows if r["label"] == args.ref), None)
        if ref:
            print("\n=== %s 缺失清单（别的机型有、它没有）===" % args.ref)
            for ns, key in (("A", "namespace_A"), ("B", "namespace_B")):
                have = set(ref[key])
                allids = set(id2name[ns])
                miss = sorted(allids - have)
                if miss:
                    print("  命名空间 %s 缺 %d 个: %s" % (
                        ns, len(miss),
                        ", ".join("%s(%s)" % (k, "/".join(id2name[ns][k])) for k in miss)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"models": rows,
                       "id_space": {ns: {k: {"names": id2name[ns][k],
                                            "models": sorted(id2models[(ns, k)])}
                                    for k in sorted(id2name[ns])} for ns in ("A", "B")}},
                      f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
