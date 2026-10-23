#!/usr/bin/env python3
"""mask ROM 指针表差分：定位「改用哪一组参数」的索引改动。

动机
----
2018-12-18 松下镜头 AF 修复已被证明：
  * 不在镜头 ID 两字节前缀比较链（E-M5/E-PM2 双机型同机型差分复核，链逐项相同）
  * 不在 LENS_INFO 镜头主表（106 条记录完全相同）
  * 每镜头 AF 调校参数本体在机身 mask ROM（0x7Exxxxxx），固件改不了
⇒ 剩下的可能是：**块 0 内的指针/索引表内容变了**（即「用哪一组参数」的开关）。

本脚本：
  1. 在两个版本的块 0 里扫出所有指向 mask ROM（0x7D–0x7F）的 32 位指针
  2. 用唯一字符串锚点把 A 的偏移对齐到 B 的偏移
  3. 逐个比较对齐后同一位置上的指针值 ⇒ 列出「指针值变了」的位置

用法::

    python rom_ptr_diff.py --a A_block0.bin --b B_block0.bin [--json out.json]
"""
import argparse
import bisect
import collections
import json
import re
import struct

STR_RE = re.compile(rb"[\x20-\x7e]{16,}")
ROM_LO, ROM_HI = 0x7D000000, 0x80000000


def unique_strings(d):
    cnt = collections.Counter()
    first = {}
    for m in STR_RE.finditer(d):
        s = m.group()
        cnt[s] += 1
        first.setdefault(s, m.start())
    return {s: off for s, off in first.items() if cnt[s] == 1}


class SegmentMap:
    def __init__(self, anchors):
        self.a_pts = [a for a, _, _ in anchors]
        self.b_pts = [b for _, b, _ in anchors]
        self.lo_a = self.a_pts[0] if anchors else 0
        self.hi_a = self.a_pts[-1] if anchors else 0

    def map(self, oa):
        if not self.anchors_ok():
            return None
        if oa < self.lo_a or oa > self.hi_a:
            return None
        i = bisect.bisect_right(self.a_pts, oa) - 1
        if i < 0:
            i = 0
        if i >= len(self.a_pts) - 1:
            if len(self.a_pts) < 2:
                return self.b_pts[0] + (oa - self.a_pts[0])
            a0, a1 = self.a_pts[-2], self.a_pts[-1]
            b0, b1 = self.b_pts[-2], self.b_pts[-1]
            return b0 if a1 == a0 else b0 + (oa - a0) * (b1 - b0) // (a1 - a0)
        a0, a1 = self.a_pts[i], self.a_pts[i + 1]
        b0, b1 = self.b_pts[i], self.b_pts[i + 1]
        return b0 if a1 == a0 else b0 + (oa - a0) * (b1 - b0) // (a1 - a0)

    def anchors_ok(self):
        return bool(self.a_pts)


def build_anchors(A, B):
    sa, sb = unique_strings(A), unique_strings(B)
    common = set(sa) & set(sb)
    return sorted((sa[s], sb[s], s) for s in common)


def rom_pointers(d, base):
    """返回 {文件偏移: (指针值, runtime地址)}，只取 4 字节对齐、落在 mask ROM 区间的值。"""
    out = {}
    n = len(d)
    for off in range(0, n - 3, 4):
        v = struct.unpack_from("<I", d, off)[0]
        if ROM_LO <= v < ROM_HI:
            out[off] = (v, base + off)
    return out


def runs(ptrs):
    """把连续偏移的指针聚成数组。"""
    keys = sorted(ptrs)
    groups = []
    cur = []
    prev = None
    for k in keys:
        if prev is not None and k == prev + 4:
            cur.append(k)
        else:
            if len(cur) >= 2:
                groups.append(cur)
            cur = [k]
        prev = k
    if len(cur) >= 2:
        groups.append(cur)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--base-a", type=lambda s: int(s, 0), default=0x402C0000)
    ap.add_argument("--base-b", type=lambda s: int(s, 0), default=0x402C0000)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    A = open(args.a, "rb").read()
    B = open(args.b, "rb").read()
    pa = rom_pointers(A, args.base_a)
    pb = rom_pointers(B, args.base_b)
    print(f"A {args.a}  {len(A)} B  maskROM指针 {len(pa)} 个 / {len(runs(pa))} 段")
    print(f"B {args.b}  {len(B)} B  maskROM指针 {len(pb)} 个 / {len(runs(pb))} 段")

    anchors = build_anchors(A, B)
    smap = SegmentMap(anchors)
    print(f"唯一锚点 {len(anchors)}  对齐区间 0x{smap.lo_a:X}..0x{smap.hi_a:X}\n")

    changed, same, unmatched = [], 0, 0
    for off, (va, ra) in pa.items():
        ob = smap.map(off)
        if ob is None or ob not in pb:
            unmatched += 1
            continue
        vb = pb[ob][0]
        if vb == va:
            same += 1
        else:
            changed.append({
                "a_off": off, "a_runtime": ra, "a_val": va,
                "b_off": ob, "b_runtime": pb[ob][1], "b_val": vb,
            })
    print(f"对齐后可比较指针 {same + len(changed)}  其中值不同 {len(changed)}  无对应 {unmatched}")

    if changed:
        # 按 4 字节连续聚成跨度
        changed.sort(key=lambda r: r["a_off"])
        spans = []
        for r in changed:
            if spans and r["a_off"] == spans[-1]["a_end"] + 4 \
               and r["b_off"] == spans[-1]["b_end"] + 4:
                spans[-1]["a_end"] = r["a_off"]
                spans[-1]["b_end"] = r["b_off"]
                spans[-1]["items"].append(r)
            else:
                spans.append({"a_start": r["a_off"], "a_end": r["a_off"],
                              "b_start": r["b_off"], "b_end": r["b_off"],
                              "items": [r]})
        print(f"\n=== 指针值发生变化的连续跨度: {len(spans)} ===")
        for s in spans:
            n = len(s["items"])
            print(f"  A file 0x{s['a_start']:08X} runtime 0x{s['items'][0]['a_runtime']:08X}"
                  f"  ->  B file 0x{s['b_start']:08X} runtime 0x{s['items'][0]['b_runtime']:08X}"
                  f"   ({n} 项)")
            for it in s["items"][:12]:
                print(f"      0x{it['a_runtime']:08X}: 0x{it['a_val']:08X}  ->  0x{it['b_val']:08X}")
            if n > 12:
                print(f"      ... 共 {n} 项")
        if args.json:
            json.dump({"spans": spans, "changed": changed},
                      open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"\n[JSON] {args.json}")


if __name__ == "__main__":
    main()
