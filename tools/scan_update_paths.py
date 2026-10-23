#!/usr/bin/env python3
"""把 E-P5 块 0 字符串池里所有「路径 / 文件名 / 更新相关」的串捞出来。

用途（第 26 轮）:
    搞清楚「卡刷到底是怎么做的」—— 相机在卡上找的文件名、目录、
    以及 [firmup] 子系统的全部提示串。
"""
import json
import re

STR = r"D:\0_Project\01Test\ep5-fw-reverse\decoded\strings.jsonl"
rows = [json.loads(l) for l in open(STR, encoding="utf-8")]


def rt(r):
    return int(r["container_address"], 16) - 0x20


def show(title, pred, limit=200):
    sel = [(rt(r), r["text"]) for r in rows if pred(r["text"])]
    sel.sort()
    print("=== %s : %d 条 ===" % (title, len(sel)))
    for a, t in sel[:limit]:
        print("  0x%08X  %r" % (a, t))
    print()


show("带 .BIN / .bin 的文件名",
     lambda t: re.search(r"\.bin", t, re.I))

show("含 WFDP / WFCL",
     lambda t: "WFDP" in t or "WFCL" in t)

show("含 DCOLYMP",
     lambda t: "DCOLYMP" in t)

show("形如路径（含反斜杠且有盘符或目录）",
     lambda t: len(t) > 3 and ("\\" in t) and (re.match(r"^[A-Z]:\\", t) or "/" in t))

show("firmup / firmware 相关",
     lambda t: re.search(r"firmup|firm.?ware", t, re.I))

show("E108 / 机型码",
     lambda t: re.search(r"E108|E1[0-9]{2}9999", t, re.I))
