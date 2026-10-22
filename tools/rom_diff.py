#!/usr/bin/env python3
"""对比两个机型的 mask ROM 引用地址集合。

用途：E-P5 1.8（未解锁电影艺术滤镜） vs E-M5 II v4.1（官方已解锁）。
只被新机型引用、且落在 E-P5 也用过的同一 ROM 页里的地址
= 新机型多出来的资源 = E-P5 机身 ROM 里"有货但没启用"的候选。

用法: python rom_diff.py <invA.txt> <invB.txt> [pageHex]
"""
import sys, re, collections

def load(path):
    addrs = set()
    pages = collections.Counter()
    inrom = False
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("---- 每个被引用的 ROM 地址"):
            inrom = True
            continue
        if not inrom:
            continue
        m = re.match(r"\s+0x([0-9a-fA-F]{8})\s", line)
        if m:
            v = int(m.group(1), 16)
            addrs.add(v)
            pages[v & 0xFFFF0000] += 1
    return addrs, pages

A, pa = load(sys.argv[1])
B, pb = load(sys.argv[2])
pagefilter = int(sys.argv[3], 0) if len(sys.argv) > 3 else None

print(f"A = {sys.argv[1]}   ROM 地址 {len(A)} 个 / {len(pa)} 页")
print(f"B = {sys.argv[2]}   ROM 地址 {len(B)} 个 / {len(pb)} 页")

onlyB = B - A
onlyA = A - B
both = A & B
print(f"\n共有 {len(both)}   仅 A {len(onlyA)}   仅 B {len(onlyB)}")

if pagefilter is not None:
    m = pagefilter << 16
    onlyB = {v for v in onlyB if (v & 0xFFFF0000) == m}
    onlyA = {v for v in onlyA if (v & 0xFFFF0000) == m}
    print(f"\n=== 限定页 0x{pagefilter:06X}xxxx ===")
    print(f"仅 B(E-M5 II) {len(onlyB)} 个，仅 A(E-P5) {len(onlyA)} 个")
    for v in sorted(onlyB)[:60]:
        print(f"   仅 B  0x{v:08X}")
    for v in sorted(onlyA)[:60]:
        print(f"   仅 A  0x{v:08X}")
else:
    print("\n=== 仅 B(E-M5 II) 的 ROM 页（按地址数降序）===")
    cp = collections.Counter(v & 0xFFFF0000 for v in onlyB)
    for p, n in cp.most_common(25):
        extra = ""
        if p in pa:
            extra = f"   (A 也用了该页，共 {pa[p]} 个地址)"
        print(f"   页 0x{p:08X}  仅 B {n} 个{extra}")
    print("\n=== 仅 A(E-P5) 的 ROM 页 ===")
    cp = collections.Counter(v & 0xFFFF0000 for v in onlyA)
    for p, n in cp.most_common(15):
        print(f"   页 0x{p:08X}  仅 A {n} 个")
