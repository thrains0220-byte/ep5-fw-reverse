#!/usr/bin/env python3
"""跨版本语义差分 v3：按「引用的 RAM/ROM 地址集合」索引做快速配对。

思路
----
把每个函数归一化反汇编里出现的 **RAM 全局 (0x60xxxxxx)** 与 **mask ROM (0x7Exxxxxx)**
地址抽出来，组成该函数的「地址指纹」。
- 两版都存在且地址指纹相同的函数 => 同一功能的同一函数（改动前后）
- 只在修复后出现、且其地址指纹与某个只在修复前出现的函数一致 => **同一函数的改写**

这比 difflib 全量配对快几个数量级，且天然把 AF / 镜头相关函数挑出来
（它们的地址指纹与普通函数不同）。

用法: python semdiff3.py <pre.norm2.txt> <post.norm2.txt> [topN]
"""
import sys, re, collections

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


def addrsig(body):
    """抽取 RAM/ROM 地址集合（保持稳定地址，排除镜像内地址）。"""
    s = set()
    for m in ADDR.finditer(body):
        v = int(m.group(1), 16)
        top = v >> 24
        if top in (0x60, 0x7E, 0x7D, 0x7F):
            s.add(v)
    return frozenset(s)


def main():
    pre, post = load(sys.argv[1]), load(sys.argv[2])
    topn = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    # 1) 完全相同的函数（跨版本）
    same = set(pre.values()) & set(post.values())
    print(f"函数数: 前 {len(pre)}  后 {len(post)}")
    print(f"归一化后完全相同的函数指纹: {len(same)} "
          f"({100.0*len(same)/max(1,len(pre)):.1f}%)\n")

    # 2) 按地址指纹分组
    pre_by_sig = collections.defaultdict(list)
    post_by_sig = collections.defaultdict(list)
    for e, b in pre.items():
        pre_by_sig[addrsig(b)].append((e, b))
    for e, b in post.items():
        post_by_sig[addrsig(b)].append((e, b))

    # 3) 同地址指纹、但反汇编不同的 = 改写过的函数
    changed = []
    for sig, plist in pre_by_sig.items():
        if not sig:
            continue
        qlist = post_by_sig.get(sig)
        if not qlist:
            continue
        pset = collections.Counter(b for _, b in plist)
        qset = collections.Counter(b for _, b in qlist)
        onlyp = pset - qset
        onlyq = qset - pset
        if onlyp and onlyq:
            changed.append((len(sig), onlyp, onlyq, plist, qlist))

    changed.sort(key=lambda t: -t[0])
    print(f"=== 地址指纹相同但代码不同的函数组: {len(changed)} 组 ===")
    print("（按指纹里的稳定地址数量降序；地址越多 => 越可能是核心功能函数）\n")

    import difflib
    shown = 0
    for nsig, onlyp, onlyq, plist, qlist in changed:
        # 找出 pre 侧只在前的函数体，以及它在 plist 里的入口
        premap = {}
        for e, b in plist:
            premap.setdefault(b, []).append(e)
        for pb, cntp in onlyp.most_common():
            pe = premap[pb][0]
            # 在 onlyq 里找最佳配对（按 token 序列比较，而不是字符）
            pa = pb.split()
            best, bestr, bestsm = None, 0.0, None
            for qb, cntq in onlyq.most_common():
                qa = qb.split()
                sm = difflib.SequenceMatcher(None, pa, qa, autojunk=False)
                if sm.quick_ratio() < 0.5:
                    continue
                r = sm.ratio()
                if r > bestr:
                    bestr, best, bestsm = r, (qb, qa), sm
            if best is None or bestr < 0.60:
                continue
            qe = next(e for e, b in qlist if b == best[0])
            ops = [o for o in bestsm.get_opcodes() if o[0] != "equal"]
            nchg = sum(max(o[2] - o[1], o[4] - o[3]) for o in ops)
            if nchg > 40:
                continue
            a = pa
            b = best[1]
            print("-" * 78)
            print(f"函数 前@{pe} -> 后@{best[0]}   相似度 {bestr:.3f}  改动 {nchg} token  "
                  f"稳定地址 {nsig} 个")
            for tag, i1, i2, j1, j2 in ops:
                if tag == "insert":
                    print(f"   + {' '.join(b[j1:j2])}")
                elif tag == "delete":
                    print(f"   - {' '.join(a[i1:i2])}")
                else:
                    print(f"   ~ {' '.join(a[i1:i2])}  ->  {' '.join(b[j1:j2])}")
            shown += 1
            if shown >= topn:
                return
            break


if __name__ == "__main__":
    main()
