#!/usr/bin/env python3
"""比较各机型块 0 内的 art_effect_<ID>_<name> 符号名集合。

名字表虽无引用，但它**忠实记录了该机型的效果 ID 空间**。
若新机型的 ID 空间更大 ⇒ 多出来的就是"该机型有、而 E-P5 没有"的滤镜。

用法: python art_id_space.py <decoded_block0.bin> [decoded_block0.bin ...]
"""
import sys, re, os, collections

PAT = re.compile(rb"art_effect_(\d+)_([A-Za-z0-9_]+)")

for path in sys.argv[1:]:
    d = open(path, "rb").read()
    found = collections.defaultdict(set)
    for m in PAT.finditer(d):
        found[int(m.group(1))].add(m.group(2).decode("ascii"))
    tag = os.path.basename(path)
    print(f"=== {tag}  ({len(d)} B) ===")
    if not found:
        print("    未找到 art_effect_* 名字")
        continue
    ids = sorted(found)
    print(f"    效果 ID 空间: {ids}   共 {len(ids)} 个")
    for i in ids:
        print(f"      {i:3d}  {' '.join(sorted(found[i]))}")
    print()
