#!/usr/bin/env python3
"""跨版本「归一化函数集合」差分 —— 无需函数对齐。

输入：两份 Ghidra 导出的 normalized.txt（每行 <entry>|<归一化反汇编>）
做法：
  1. 把每个函数的归一化文本作为其「语义指纹」
  2. 统计两版指纹的多重集合
  3. 只在修复前出现 / 只在修复后出现的函数 = 候选改动
  4. 输出指纹差 + 原始函数入口 + 反汇编片段

用法: python semdiff.py <pre.normalized.txt> <post.normalized.txt>
"""
import sys, collections


def load(path):
    funcs = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "|" not in line:
            continue
        entry, body = line.split("|", 1)
        funcs[entry.strip()] = body.strip()
    return funcs


def main():
    pre = load(sys.argv[1])
    post = load(sys.argv[2])
    print(f"修复前函数 {len(pre)}  修复后函数 {len(post)}\n")

    ca = collections.Counter(pre.values())
    cb = collections.Counter(post.values())
    only_pre = ca - cb
    only_post = cb - ca
    print(f"只在修复前出现的指纹: {sum(only_pre.values())} 个函数")
    print(f"只在修复后出现的指纹: {sum(only_post.values())} 个函数")
    print(f"两版共有指纹        : {sum((ca & cb).values())} 个函数\n")

    def dump(title, diffmap, funcs):
        print("=" * 78)
        print(f"### {title}")
        for fp, cnt in diffmap.most_common(40):
            entries = [e for e, b in funcs.items() if b == fp]
            body = fp.split()
            print(f"\n  [{cnt} 个函数] 入口: {', '.join(entries[:6])}")
            print(f"    长度 {len(body)} 条指令")
            print("    " + " | ".join(body[:40]))

    dump("只在修复前出现的函数（修复后被删除/改写）", only_pre, pre)
    dump("只在修复后出现的函数（修复新增/改写）", only_post, post)


if __name__ == "__main__":
    main()
