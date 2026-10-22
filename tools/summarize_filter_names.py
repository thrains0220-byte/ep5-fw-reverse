#!/usr/bin/env python3
"""把 block1_filter_names.json 汇总成「滤镜名 → 资源 ID 集合」的紧凑表。

用途:
  1. 列出 E-P5 照片模式下所有艺术滤镜的 UI 名字及其字符串资源 ID;
  2. 识别「同名多 ID」= 拍照 / 录像 双形态已被固件准备好的证据;
  3. 找出只有单一 ID 或完全没有 ID 的滤镜（= 未暴露 / 未接线）。

用法:
    python summarize_filter_names.py <block1_filter_names.json>
"""
import json
import sys
from collections import defaultdict


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    fn = d.get("filter_names", {})
    print("共 %d 个滤镜名\n" % len(fn))

    name2ids = defaultdict(set)
    for name, items in fn.items():
        for it in items:
            rid = it.get("resource_id")
            if rid:
                name2ids[name].add(rid)

    ids2names = defaultdict(set)
    for name, ids in name2ids.items():
        for i in ids:
            ids2names[i].add(name)

    print("%-22s %-10s %s" % ("FILTER", "IDs", "备注"))
    print("-" * 78)
    for name in sorted(fn):
        ids = sorted(name2ids.get(name, ()))
        note = ""
        if len(ids) >= 2:
            note = "★ 多形态(%d 个 ID)" % len(ids)
        elif not ids:
            note = "无资源 ID"
        print("%-22s %-10s %s" % (name, ",".join(ids) if ids else "-", note))

    print()
    print("=== 按资源 ID 归组 ===")
    for i in sorted(ids2names):
        print("  %s : %s" % (i, ", ".join(sorted(ids2names[i]))))

    allids = sorted(ids2names)
    print()
    print("用到的资源 ID 总数: %d" % len(allids))
    # 找 A03F..A060 区间的空缺
    print("=== A03F..A060 占用情况 ===")
    used = set(ids2names)
    for x in range(0x3F, 0x61):
        rid = "A%03X" % x
        state = ",".join(sorted(used & {rid})) or "-"
        mark = "" if rid in used else "   ← 空闲"
        print("  %s : %-24s%s" % (rid, state, mark))


if __name__ == "__main__":
    main()
