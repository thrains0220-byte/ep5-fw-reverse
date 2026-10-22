#!/usr/bin/env python3
"""跨版本「比较常量频次」差分 —— 直接检验是否新增了镜头 ID 之类的判定。

思路
----
把每个函数里所有 `CMP <立即数>` 的立即数收集起来，统计**每个常量出现在多少个函数里**。
若 2018-12-18 的 AF 修复新增了松下镜头的识别分支，
那么某个镜头 ID 字节（0x80-0xFF）或厂商码（0xC0/0xC1/0x80/0x81）的出现频次会上升。

用法: python cmp_hist.py <pre.norm2.txt> <post.norm2.txt> [topN]
"""
import sys, re, collections

CMP = re.compile(r"\bCMP\s+0x([0-9a-f]+)")
ADDR = re.compile(r"0x([0-9a-f]{8})")


def load(path):
    funcs = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "|" not in line:
            continue
        entry, body = line.split("|", 1)
        funcs[entry.strip()] = body.strip()
    return funcs


def consts(body):
    out = []
    for m in CMP.finditer(body):
        try:
            out.append(int(m.group(1), 16))
        except ValueError:
            pass
    return out


def hist(funcs):
    """常量 -> 出现该常量的函数数；并记录函数入口。"""
    h = collections.Counter()
    where = collections.defaultdict(list)
    for e, b in funcs.items():
        seen = set(consts(b))
        for v in seen:
            h[v] += 1
            where[v].append(e)
    return h, where


def main():
    pre, post = load(sys.argv[1]), load(sys.argv[2])
    topn = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    hp, wp = hist(pre)
    hq, wq = hist(post)

    print(f"修复前函数 {len(pre)}   修复后函数 {len(post)}")
    print(f"不同比较常量: 前 {len(hp)}  后 {len(hq)}\n")

    up = [(hq[v] - hp[v], v) for v in set(hp) | set(hq) if hq[v] > hp[v]]
    dn = [(hp[v] - hq[v], v) for v in set(hp) | set(hq) if hp[v] > hq[v]]
    up.sort(reverse=True)
    dn.sort(reverse=True)

    print("=== 出现频次**上升**的比较常量（= 新增判定）===")
    for d, v in up[:topn]:
        newf = [e for e in wq[v] if e not in set(wp[v])]
        print(f"  0x{v:02X}  频次 {hp[v]} -> {hq[v]}  (+{d})   新出现的函数: {newf[:6]}")

    print("\n=== 出现频次**下降**的比较常量（= 判定被移除/合并）===")
    for d, v in dn[:topn]:
        gone = [e for e in wp[v] if e not in set(wq[v])]
        print(f"  0x{v:02X}  频次 {hp[v]} -> {hq[v]}  (-{d})   消失的函数: {gone[:6]}")

    # 特别关注：镜头 ID 风格的高字节（0x80-0xFF）与厂商码
    print("\n=== 镜头 ID 风格常量（0x80-0xFF）的频次变化 ===")
    for v in sorted(set(hp) | set(hq)):
        if 0x80 <= v <= 0xFF and hq[v] != hp[v]:
            print(f"  0x{v:02X}  {hp[v]} -> {hq[v]}   ({'新增' if hq[v]>hp[v] else '减少'})")


if __name__ == "__main__":
    main()
