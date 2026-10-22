#!/usr/bin/env python3
"""跨版本语义差分 v4：只挑出「比较常量（CMP 立即数）发生变化」的函数配对。

如果 2018-12-18 的 AF 修复新增了松下镜头的识别分支，
最直接的证据形态就是**某个 CMP 的立即数变了**（新增一个镜头 ID 前缀）。
本脚本用地址指纹做 O(n) 配对，再只报告含 CMP 常量变化的组。

用法: python semdiff4.py <pre.norm2.txt> <post.norm2.txt> [topN]
"""
import sys, re, collections, difflib

ADDR = re.compile(r"0x([0-9a-f]{8})")
CMP = re.compile(r"^CMP$")


def load(path):
    funcs = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "|" not in line:
            continue
        entry, body = line.split("|", 1)
        funcs[entry.strip()] = body.strip()
    return funcs


def addrsig(body):
    s = set()
    for m in ADDR.finditer(body):
        v = int(m.group(1), 16)
        if (v >> 24) in (0x60, 0x7E, 0x7D, 0x7F):
            s.add(v)
    return frozenset(s)


def cmp_consts(tokens):
    """抽出该函数里所有 CMP 的立即数。"""
    out = []
    for i, t in enumerate(tokens[:-1]):
        if CMP.match(t):
            nxt = tokens[i + 1]
            if nxt.startswith("0x"):
                try:
                    out.append(int(nxt, 16))
                except ValueError:
                    pass
    return out


def main():
    pre, post = load(sys.argv[1]), load(sys.argv[2])
    topn = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    pre_by = collections.defaultdict(list)
    post_by = collections.defaultdict(list)
    for e, b in pre.items():
        pre_by[addrsig(b)].append((e, b))
    for e, b in post.items():
        post_by[addrsig(b)].append((e, b))

    results = []
    for sig, plist in pre_by.items():
        if not sig:
            continue
        qlist = post_by.get(sig)
        if not qlist:
            continue
        premap = {}
        for e, b in plist:
            premap.setdefault(b, []).append(e)
        postmap = {}
        for e, b in qlist:
            postmap.setdefault(b, []).append(e)
        pset = collections.Counter(b for _, b in plist)
        qset = collections.Counter(b for _, b in qlist)
        onlyp = pset - qset
        onlyq = qset - pset
        for pb, _ in onlyp.items():
            pa = pb.split()
            cp = cmp_consts(pa)
            if not cp:
                continue
            for qb, _ in onlyq.items():
                qa = qb.split()
                cq = cmp_consts(qa)
                if not cq:
                    continue
                added = [v for v in cq if cq.count(v) > cp.count(v)]
                removed = [v for v in cp if cp.count(v) > cq.count(v)]
                if not added and not removed:
                    continue
                sm = difflib.SequenceMatcher(None, pa, qa, autojunk=False)
                if sm.quick_ratio() < 0.6:
                    continue
                results.append((len(added) + len(removed), len(sig),
                                premap[pb][0], postmap[qb][0], added, removed,
                                pa, qa, sm.ratio()))
                break

    results.sort(key=lambda t: (t[0], -t[1]))
    print(f"=== CMP 常量发生变化的函数配对: {len(results)} 组 ===")
    print("（改动的新增/移除比较常量往往就是镜头 ID 或模式 ID）\n")
    for n, nsig, pe, qe, added, removed, pa, qa, ratio in results[:topn]:
        print("-" * 78)
        print(f"前@{pe} -> 后@{qe}   相似度 {ratio:.3f}   稳定地址 {nsig}")
        print(f"   新增比较常量: " + " ".join(f"0x{v:02X}" for v in added))
        print(f"   移除比较常量: " + " ".join(f"0x{v:02X}" for v in removed))
        sm = difflib.SequenceMatcher(None, pa, qa, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("replace", "delete"):
                print(f"   ~ {' '.join(pa[i1:i2])}  ->  {' '.join(qa[j1:j2])}")
            else:
                print(f"   + {' '.join(qa[j1:j2])}")


if __name__ == "__main__":
    main()
