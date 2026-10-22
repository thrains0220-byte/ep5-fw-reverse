#!/usr/bin/env python3
"""从块 1（UTF-16LE 多语言字符串池）抽取「字符串资源 ID → 文本」映射。

块 1 的 UI 字符串形如 "@A042@Grainy Film"：
    "@Axxx@" 是**内嵌在字符串里的资源 ID 标记**，
    同一 ID 在不同语言分区各出现一次。

用法:
    python block1_res_id_map.py --blk1 <block1.bin> [--base 0x43C40020]
                                [--id-regex 'A[0-9A-F]{2,4}'] [--out map.json]
"""
import argparse
import json
import re
import sys
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk1", required=True)
    ap.add_argument("--base", default="0x43C40020")
    ap.add_argument("--id-regex", default=r"@[A-Z][0-9A-F]{2,4}@")
    ap.add_argument("--out", default=None)
    ap.add_argument("--focus", default=None, help="只显示匹配此正则的 ID")
    args = ap.parse_args()

    base = int(args.base, 0)
    raw = open(args.blk1, "rb").read()
    # UTF-16LE 尝试解码（忽略无法解码的字节）
    txt = raw.decode("utf-16-le", errors="ignore")

    rx = re.compile(args.id_regex)
    m = defaultdict(list)
    for mo in rx.finditer(txt):
        rid = mo.group(0)[1:-1]
        # 文本 = 标记之后到 NUL 为止
        j = mo.end()
        k = txt.find("\x00", j)
        if k < 0:
            k = min(j + 200, len(txt))
        s = txt[j:k]
        if not s:
            continue
        m[rid].append((mo.start() * 2, s))

    print("块 1 %s  共抽出 %d 个资源 ID" % (args.blk1, len(m)))
    focus = re.compile(args.focus) if args.focus else None
    out = {}
    for rid in sorted(m):
        if focus and not focus.search(rid):
            continue
        vals = sorted(set(s for _, s in m[rid]))
        out[rid] = {"offsets": [hex(o) for o, _ in sorted(m[rid])][:8],
                    "texts": vals}
        if len(vals) == 1:
            print("  %-8s %s" % (rid, vals[0]))
        else:
            print("  %-8s %d 种: %s" % (rid, len(vals), " | ".join(vals[:6])))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.out)


if __name__ == "__main__":
    main()
