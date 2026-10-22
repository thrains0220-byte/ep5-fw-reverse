#!/usr/bin/env python3
"""跨版本语义差分 v2：配对"只在修复前/后出现"的函数，找出最小改动。

1. 计算两版归一化函数指纹的多重集合差
2. 用 difflib 在差集之间做最优配对（相似度高 => 同一函数的新旧版本）
3. 报告改动最小的配对 —— 这就是补丁所在
4. 对配对结果按"是否触碰 RAM 全局 (0x60xxxxxx) / mask ROM (0x7Exxxxxx)"排序
   —— AF / 镜头相关函数会引用它们

用法: python semdiff2.py <pre.norm2.txt> <post.norm2.txt> [topN]
"""
import sys, collections, re, difflib

RAM = re.compile(r"0x60[0-9a-f]{6}")
ROM = re.compile(r"0x7e[0-9a-f]{6}")


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
    pre, post = load(sys.argv[1]), load(sys.argv[2])
    topn = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    ca = collections.Counter(pre.values())
    cb = collections.Counter(post.values())
    only_pre = list((ca - cb).elements())
    only_post = list((cb - ca).elements())
    common = sum((ca & cb).values())
    print(f"修复前函数 {len(pre)}  修复后函数 {len(post)}")
    print(f"共有指纹 {common}   仅前 {len(only_pre)}   仅后 {len(only_post)}\n")

    # 快速索引：按长度分桶，避免 O(n^2)
    by_len_pre = collections.defaultdict(list)
    for f in only_pre:
        by_len_pre[len(f)].append(f)
    by_len_post = collections.defaultdict(list)
    for f in only_post:
        by_len_post[len(f)].append(f)

    pairs = []
    used_post = set()
    for fpre in only_pre:
        L = len(fpre)
        best = None
        best_ratio = 0.0
        best_diff = None
        # 在长度相近的桶里找最佳匹配
        for dl in (-8, -4, -2, -1, 0, 1, 2, 4, 8):
            for g in by_len_post.get(L + dl, ()):
                if g in used_post:
                    continue
                sm = difflib.SequenceMatcher(None, fpre, g, autojunk=False)
                r = sm.quick_ratio()
                if r < 0.55:
                    continue
                ratio = sm.ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = g
                    best_diff = sm
        if best is not None and best_ratio >= 0.70:
            used_post.add(best)
            pairs.append((best_ratio, best_diff, fpre, best))

    pairs.sort(key=lambda t: -t[0])
    print(f"=== 配对 {len(pairs)} 对（相似度 >= 0.70），按相似度升序列出改动最小的 ===\n")

    scored = []
    for ratio, sm, fpre, fpost in pairs:
        ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
        nchange = sum(max(o[2] - o[1], o[4] - o[3]) for o in ops)
        tags = []
        if RAM.search(fpre) or RAM.search(fpost):
            tags.append("RAM")
        if ROM.search(fpre) or ROM.search(fpost):
            tags.append("ROM")
        scored.append((nchange, ratio, ops, fpre, fpost, tags))

    scored.sort(key=lambda t: t[0])
    for nchange, ratio, ops, fpre, fpost, tags in scored[:topn]:
        print("-" * 78)
        print(f"改动 {nchange} 个 token / 相似度 {ratio:.3f}  {' '.join(tags)}")
        for tag, i1, i2, j1, j2 in ops:
            a = fpre.split()[i1:i2]
            b = fpost.split()[j1:j2]
            if tag == "insert":
                print(f"   + 新增: {' '.join(b)}")
            elif tag == "delete":
                print(f"   - 删除: {' '.join(a)}")
            else:
                print(f"   ~ 替换: {' '.join(a)}  ->  {' '.join(b)}")
        print()


if __name__ == "__main__":
    main()
