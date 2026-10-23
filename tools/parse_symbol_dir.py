#!/usr/bin/env python3
"""解析固件里的「函数目录」（`sx<编号>/` + `**函数名()*`），并与代码里的
`cmp <编号>,d0` 分派链对照。

发现（第二十轮）:
    E-PM2 v1.5（AF 修复前）的块 0 里存在一个**函数名目录**：
        sx5/   **fcs_lens_mfts_scan_lens(2Rm)*
        sx6/   **fcs_lens_mfts_scan_only_lens()*
        ...
        sxc/   **fcs_lens_mfts_move_lens()*
        sxd/   **fcs_lens_mfts_move_lens_ofset_target()*
    而 **修复后的 v1.6 里 `fcs_lens_mfts_move_lens_ofset_target` 消失**
    （其余同族函数仍在）。

    ⇒ 字符串**不被任何指针引用**（"哑引用"），
      真正的绑定是「**编号**」：`sx<编号>/` 是目录项，代码用 `cmp <编号>,d0` 分派。
    ⇒ 社区补丁模式 A 的 `1c a0 06 c8 14 a0 03 c8 10 a0 08 c8`
      正是「比较编号 6 / 3 / 8」的链！

本脚本:
    1. 从块 0 的字符串池抽出全部 `sx<hex>/` 标记及其后紧跟的 `**name(...)*`；
    2. 统计编号集合与函数名；
    3. 在块 0 里找「比较这些编号」的 `cmp` 链（Ghidra 反汇编层面另做）。

用法:
    python tools/parse_symbol_dir.py --blk0 <块0> [--base 0x402C0000] [--grep move_lens]
"""
import argparse
import re


def spans(d, minlen=3):
    out = []
    i = 0
    N = len(d)
    while i < N:
        j = i
        while j < N and 32 <= d[j] < 127:
            j += 1
        if j - i >= minlen:
            out.append((i, d[i:j].decode("ascii")))
        i = j + 1 if j > i else i + 1
    return out


RX_MARK = re.compile(r"^sx([0-9a-fA-F]{1,4})/$")
RX_FN = re.compile(r"^\*\*([A-Za-z0-9_]+)\(")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--base", default="0x402C0000")
    ap.add_argument("--grep", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    base = int(args.base, 0)
    d = open(args.blk0, "rb").read()
    sp = spans(d)

    entries = []
    for i, (off, s) in enumerate(sp):
        m = RX_MARK.match(s)
        if not m:
            continue
        num = int(m.group(1), 16)
        fn = None
        for k in range(i + 1, min(i + 4, len(sp))):
            fm = RX_FN.match(sp[k][1])
            if fm:
                fn = fm.group(1)
                break
        entries.append({"num": num, "num_hex": m.group(1).lower(),
                        "fn": fn, "addr": base + off, "str": s})

    print("块 0 %s" % args.blk0)
    print("目录项 %d 条（sx<编号>/），其中带函数名的 %d 条\n" % (
        len(entries), sum(1 for e in entries if e["fn"])))
    if entries:
        nums = sorted(e["num"] for e in entries)
        print("编号范围 0x%X..0x%X  (%d 个不同编号)" % (min(nums), max(nums), len(set(nums))))
        print()

    show = entries
    if args.grep:
        show = [e for e in entries if e["fn"] and args.grep in e["fn"]]
        print("=== 过滤 `%s` ===" % args.grep)
    for e in show:
        print("  #%-6d sx%-5s  0x%08X  %s" % (
            e["num"], e["num_hex"], e["addr"], e["fn"] or "(无函数名)"))

    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.json)


if __name__ == "__main__":
    main()
