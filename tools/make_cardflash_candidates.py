#!/usr/bin/env python3
"""按 E-P5 固件里的文件名模板，生成卡刷候选文件名（供实机逐个试）。

固件证据：
  0x405F1EC4  12 字节定长模板表（通配符，非 printf 格式串）：
        S108????BIN  E108????BIN  G108????BIN  H108????BIN  W108????BIN
        A108????BIN  M108????BIN  V108????BIN  D108????BIN  T108????BIN
        I108????BIN  DATE????BIN
  0x405F21A9  'DCOLYMP'      ← 目录名
  0x40DF39B0  'C:\\WFDP0001.BIN' / 'C:\\WFCL0101.BIN' / 'C:\\WFCL0201.BIN'
  0x40DF39D0  'C:\\WFCL0%03d.BIN'   ← 卡根目录的另一套命名

⇒ 相机是「按模式扫描」文件名，模板里的 ???? 是 4 个任意字符。
  候选按「前缀（S=System / E=Extension）× 4 位版本写法（1800 / 9999 / 180 / 带点号）」
  组合。

用法:
    python tools/make_cardflash_candidates.py --out <目录> --bin <官方v1.8.BIN>
"""
import argparse
import hashlib
import os
import shutil

# (子目录, 文件名)
ALL_CANDIDATES = [
    ("DCOLYMP", "S1081800BIN"),
    ("DCOLYMP", "S1089999BIN"),
    ("DCOLYMP", "S108180.BIN"),
    ("DCOLYMP", "S1089999.BIN"),
    ("DCOLYMP", "S1080001BIN"),
    ("DCOLYMP", "S1081801BIN"),
    ("DCOLYMP", "E1081800BIN"),
    ("DCOLYMP", "E108180.BIN"),
    ("DCOLYMP", "E1089999BIN"),
    ("DCOLYMP", "E1089999.BIN"),
    ("DCOLYMP", "S1081800.BIN"),
    ("", "WFDP0001.BIN"),
    ("", "WFCL0101.BIN"),
    ("", "WFCL0201.BIN"),
]

# 固件里的模板（运行地址 0x405F1EC4 起，每项 12 字节，11 字符 + NUL）
TEMPLATES = ["S108????BIN", "E108????BIN", "G108????BIN", "H108????BIN",
             "W108????BIN", "A108????BIN", "M108????BIN", "V108????BIN",
             "D108????BIN", "T108????BIN", "I108????BIN", "DATE????BIN"]


def matches_template(name):
    """按固件模板做字面通配匹配（'?' 匹配任意单字符）。"""
    for t in TEMPLATES:
        if len(t) != len(name):
            continue
        if all(tc == "?" or tc == nc for tc, nc in zip(t, name)):
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--make-dirs", action="store_true",
                    help="为每个候选单独建一个目录（每个目录只放一个文件）")
    ap.add_argument("--only-matching", action="store_true",
                    help="只输出真正能匹配固件模板的候选")
    args = ap.parse_args()

    src = args.bin
    data = open(src, "rb").read()
    print("源固件 %s  %d B  sha256 %s"
          % (src, len(data), hashlib.sha256(data).hexdigest()))
    print()
    print("固件模板（11 字符，'?' 为字面通配）:")
    for t in TEMPLATES:
        print("   %s" % t)
    print()

    n = 0
    for i, (sub, name) in enumerate(ALL_CANDIDATES, 1):
        m = matches_template(name)
        if args.only_matching and m is None:
            print("  --  %-22s  不匹配任何模板（长度 %d），跳过"
                  % ((sub + "\\" + name) if sub else name, len(name)))
            continue
        n += 1
        if args.make_dirs:
            d = os.path.join(args.out, "%02d_%s" % (n, name.replace(".", "_")))
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, name)
        else:
            d = os.path.join(args.out, sub) if sub else args.out
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, name)
        shutil.copyfile(src, dst)
        print("  %2d  %-22s -> %s   %s"
              % (n, (sub + "\\" + name) if sub else name, dst,
                 ("[匹配 %s]" % m) if m else "[卡根目录命名]"))
    print()
    print("每次只放一个文件试；多个候选同时放可能让相机报错而不是识别。")
    print("（未加 --only-matching 时会一并生成不匹配的候选，仅供对照）")


if __name__ == "__main__":
    main()
