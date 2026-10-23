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
CANDIDATES = [
    ("DCOLYMP", "S1081800BIN"),
    ("DCOLYMP", "S1089999BIN"),
    ("DCOLYMP", "S108180.BIN"),
    ("DCOLYMP", "S1089999.BIN"),
    ("DCOLYMP", "E1081800BIN"),
    ("DCOLYMP", "E108180.BIN"),
    ("DCOLYMP", "E1089999BIN"),
    ("DCOLYMP", "E1089999.BIN"),
    ("DCOLYMP", "S1081800.BIN"),
    ("", "WFDP0001.BIN"),
    ("", "WFCL0101.BIN"),
    ("", "WFCL0201.BIN"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--make-dirs", action="store_true",
                    help="为每个候选单独建一个目录（每个目录只放一个文件）")
    args = ap.parse_args()

    src = args.bin
    data = open(src, "rb").read()
    print("源固件 %s  %d B  sha256 %s"
          % (src, len(data), hashlib.sha256(data).hexdigest()))
    print()
    for i, (sub, name) in enumerate(CANDIDATES, 1):
        if args.make_dirs:
            d = os.path.join(args.out, "%02d_%s" % (i, name.replace(".", "_")))
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, name)
        else:
            d = os.path.join(args.out, sub) if sub else args.out
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, name)
        shutil.copyfile(src, dst)
        print("  %2d  %-22s -> %s" % (i, (sub + "\\" + name) if sub else name, dst))
    print()
    print("每次只放一个文件试；多个候选同时放可能让相机报错而不是识别。")


if __name__ == "__main__":
    main()
