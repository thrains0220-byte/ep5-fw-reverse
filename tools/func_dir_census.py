#!/usr/bin/env python3
"""普查 E-P5 块 0 里的「函数目录」，建立全固件函数名索引。

机制（第 20 轮发现）:
    固件里存在 `<前缀><十六进制编号>/` + `**函数名(...)` 的目录结构，
    真正的绑定靠**编号**，所以字符串是「哑引用」。
    第 20 轮只在 `sx` 这一个目录上找到 AF 模块，
    本脚本把**所有**前缀的目录都找出来 ⇒ 得到一份可按名字检索的函数清单。

注意：必须直接扫原始块（`strings.jsonl` 只收 >=6 字符的串，
      而 `sx5/` 只有 4 字符，会被漏掉）。

用法:
    python tools/func_dir_census.py
    python tools/func_dir_census.py --grep burst --grep iso
"""
import argparse
import collections
import json
import re

BIN = r"D:\0_Project\01Test\ep5-fw-reverse\decoded\00_0100_402c0020.decoded.bin"
BASE = 0x402C0000

RX_DIR = re.compile(r"^([A-Za-z][A-Za-z0-9_]{0,5})([0-9a-fA-F]{1,4})/$")
RX_FN = re.compile(r"^\*\*([A-Za-z0-9_]+)\(")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grep", action="append", default=[])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    d = open(BIN, "rb").read()
    spans = [(m.start(), m.group().decode("latin-1"))
             for m in re.finditer(rb"[\x20-\x7e]{3,}", d)]

    entries = []
    for i, (off, text) in enumerate(spans):
        m = RX_DIR.match(text)
        if not m:
            continue
        prefix, num = m.group(1), int(m.group(2), 16)
        fn = None
        for k in range(i + 1, min(i + 6, len(spans))):
            fm = RX_FN.match(spans[k][1])
            if fm:
                fn = fm.group(1)
                break
        entries.append({"addr": "0x%08X" % (BASE + off), "prefix": prefix,
                        "num": num, "num_hex": m.group(2), "fn": fn,
                        "text": text})

    pref = collections.Counter(e["prefix"] for e in entries)
    print("=== 目录项总数: %d ===" % len(entries))
    print("前缀分布:")
    for p, c in pref.most_common():
        print("   %-10s %4d" % (p, c))
    print()

    named = [e for e in entries if e["fn"]]
    print("=== 带函数名的项: %d ===" % len(named))
    for e in named:
        print("   %-10s #%-5s 0x%08X  %s" % (e["prefix"], e["num_hex"],
                                              int(e["addr"], 16), e["fn"]))
    print()

    if args.grep:
        print("=== 过滤 %s ===" % args.grep)
        for e in entries:
            if e["fn"] and any(g.lower() in e["fn"].lower() for g in args.grep):
                print("   %-10s #%-5s 0x%08X  %s" % (e["prefix"], e["num_hex"],
                                                      int(e["addr"], 16), e["fn"]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
        print("[written] %s" % args.json)


if __name__ == "__main__":
    main()
