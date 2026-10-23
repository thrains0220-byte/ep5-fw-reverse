#!/usr/bin/env python3
"""三点对齐差分：把「修复前一步」当作控制组，隔离出只在修复那一步出现的改动。

背景
----
同机型的跨版本差分被整体重编译噪声淹没（E-M5 v2.2→v2.3：块 0 变化 23.45%）。
本脚本用**只出现一次的长字符串**作锚点，把两个版本做**分段线性对齐**，
再把「变化」按「是否也在控制组那一步出现」分类，从而把真正的补丁从噪声里抬出来。

三点设计（同一机型、按发布时间排序）::

    C (控制) ──v1.4→v1.5──> A (基准) ──v1.5→v1.6(修复)──> B (处理)

对 A 的每个偏移 o：
  ob = 对齐到 B 的偏移,  oc = 对齐到 C 的偏移
  changed_B = A[o] != B[ob]        ← 这一步变了
  changed_C = A[o] != C[oc]        ← 上一步就变了（属于常规演进）
  ⇒ changed_B and not changed_C  = **只在这一步出现的改动**（补丁候选）

用法::

    # 单对差分（只做 A→B 残差）
    python align_diff3.py --pair A=A.bin B=B.bin

    # 三点差分
    python align_diff3.py --triple C=C.bin A=A.bin B=B.bin [--json out.json]
"""
import argparse
import collections
import json
import re
import sys

STR_RE = re.compile(rb"[\x20-\x7e]{16,}")


def unique_strings(d, minlen=16):
    """返回 {内容: 偏移}，只保留在二进制中恰好出现一次的串（无歧义锚点）。"""
    cnt = collections.Counter()
    first = {}
    for m in STR_RE.finditer(d):
        s = m.group()
        cnt[s] += 1
        first.setdefault(s, m.start())
    return {s: off for s, off in first.items() if cnt[s] == 1}


def build_anchors(A, B, minlen=16):
    """建立 (a_off, b_off) 锚点对，内容在两版中都唯一。"""
    sa = unique_strings(A, minlen)
    sb = unique_strings(B, minlen)
    common = set(sa) & set(sb)
    anchors = sorted((sa[s], sb[s], s) for s in common)
    return anchors, len(sa), len(sb)


class SegmentMap:
    """分段线性映射：锚点之间用线性插值，锚点之外用最近段的 delta。"""

    def __init__(self, anchors):
        self.anchors = anchors  # [(a_off, b_off, s)]
        self.a_pts = [a for a, _, _ in anchors]
        self.b_pts = [b for _, b, _ in anchors]
        self.lo_a = self.a_pts[0] if anchors else 0
        self.hi_a = self.a_pts[-1] if anchors else 0

    def map(self, oa):
        """A 偏移 -> B 偏移。超出锚点覆盖范围返回 None。"""
        import bisect
        if not self.anchors:
            return None
        if oa < self.lo_a or oa > self.hi_a:
            return None
        i = bisect.bisect_right(self.a_pts, oa) - 1
        if i < 0:
            i = 0
        if i >= len(self.a_pts) - 1:
            # 最后一段：用最后两个锚点外推
            if len(self.a_pts) < 2:
                return self.b_pts[0] + (oa - self.a_pts[0])
            a0, a1 = self.a_pts[-2], self.a_pts[-1]
            b0, b1 = self.b_pts[-2], self.b_pts[-1]
            if a1 == a0:
                return b1 + (oa - a1)
            return b0 + (oa - a0) * (b1 - b0) // (a1 - a0)
        a0, a1 = self.a_pts[i], self.a_pts[i + 1]
        b0, b1 = self.b_pts[i], self.b_pts[i + 1]
        if a1 == a0:
            return b0
        return b0 + (oa - a0) * (b1 - b0) // (a1 - a0)


def group_spans(flags):
    """flags: [(offset, payload)] -> 连续跨度列表。"""
    spans = []
    for off, payload in flags:
        if spans and off == spans[-1][1] + 1:
            spans[-1][1] = off
            spans[-1][2].append(payload)
        else:
            spans.append([off, off, [payload]])
    return spans


def aligned_diff(A, B, smap):
    """返回 [(a_off, b_off)] 的不同字节列表（仅在锚点覆盖区间内）。"""
    out = []
    for oa in range(smap.lo_a, smap.hi_a + 1):
        ob = smap.map(oa)
        if ob is None or ob < 0 or ob >= len(B):
            continue
        if A[oa] != B[ob]:
            out.append((oa, ob))
    return out


def triple(A, B, C, minlen=16):
    """A=基准(修复前一步末), B=处理(修复后), C=控制(修复前一步初)"""
    ab, na, nb = build_anchors(A, B, minlen)
    ac, _, _ = build_anchors(A, C, minlen)
    smap_b = SegmentMap(ab)
    smap_c = SegmentMap(ac)
    db = dict(aligned_diff(A, B, smap_b))
    dc = dict(aligned_diff(A, C, smap_c))
    only_b, also_c = [], []
    for oa, ob in db.items():
        oc = smap_c.map(oa)
        rec = {
            "a_off": oa, "b_off": ob, "c_off": oc,
            "a_hex": A[oa:oa + 1].hex(), "b_hex": B[ob:ob + 1].hex(),
            "c_hex": (C[oc:oc + 1].hex() if (oc is not None and 0 <= oc < len(C)) else None),
        }
        if oc is None or oc < 0 or oc >= len(C):
            only_b.append(rec)      # 控制组无覆盖：算「只在这一步」
        elif A[oa] != C[oc]:
            also_c.append(rec)      # 上一步也变了：常规演进
        else:
            only_b.append(rec)
    return {
        "anchors_ab": len(ab), "anchors_ac": len(ac),
        "uniq_A": na, "uniq_B": nb,
        "changed_by_B": len(db), "changed_by_C": len(dc),
        "only_in_B_step": only_b, "also_in_C_step": also_c,
        "smap_b": smap_b, "smap_c": smap_c,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs="+", metavar="TAG=FILE", required=False)
    ap.add_argument("--triple", nargs=3, metavar=("C=FILE", "A=FILE", "B=FILE"), required=False)
    ap.add_argument("--minlen", type=int, default=16)
    ap.add_argument("--json", default=None)
    ap.add_argument("--maxspans", type=int, default=60)
    args = ap.parse_args()

    def load(spec):
        tag, path = spec.split("=", 1)
        with open(path, "rb") as f:
            return tag, f.read()

    result = {}
    if args.triple:
        tc, A = load(args.triple[0])
        ta, B = load(args.triple[1])
        tb, C = load(args.triple[2])
        # 语义：C=控制，A=基准(与 B 比)，B=处理
        r = triple(A, B, C, args.minlen)
        result = {
            "mode": "triple",
            "tags": {"C_control": tc, "A_base": ta, "B_treat": tb},
            "anchors_ab": r["anchors_ab"], "anchors_ac": r["anchors_ac"],
            "uniq_A": r["uniq_A"], "uniq_B": r["uniq_B"],
            "changed_by_B": r["changed_by_B"], "changed_by_C": r["changed_by_C"],
            "only_in_B_step": len(r["only_in_B_step"]),
            "also_in_C_step": len(r["also_in_C_step"]),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        spans = group_spans([(x["a_off"], x) for x in r["only_in_B_step"]])
        print(f"\n=== 只在 {ta}→{tb} 这一步出现的改动跨度: {len(spans)} ===")
        for s, e, items in spans[: args.maxspans]:
            ob0 = items[0]["b_off"]; ob1 = items[-1]["b_off"]
            print(f"  A 0x{s:08X}..0x{e:08X}  B 0x{ob0:08X}..0x{ob1:08X}  (len {e-s+1})")
            print(f"      A: {A[s:e+1].hex(' ')}")
            print(f"      B: {B[ob0:ob1+1].hex(' ')}")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({
                    "summary": result,
                    "spans": [{"a_start": s, "a_end": e,
                               "b_start": items[0]["b_off"], "b_end": items[-1]["b_off"],
                               "a_hex": A[s:e+1].hex(),
                               "b_hex": B[items[0]["b_off"]:items[-1]["b_off"]+1].hex(),
                               "items": items} for s, e, items in spans],
                }, f, ensure_ascii=False, indent=2)
            print(f"\n[JSON] {args.json}")
        return

    if args.pair:
        ta, A = load(args.pair[0])
        tb, B = load(args.pair[1])
        anchors, na, nb = build_anchors(A, B, args.minlen)
        smap = SegmentMap(anchors)
        diffs = aligned_diff(A, B, smap)
        raw = sum(1 for k in range(min(len(A), len(B))) if A[k] != B[k])
        print(f"{ta} ({len(A)} B) vs {tb} ({len(B)} B)")
        print(f"唯一锚点 {len(anchors)}  对齐区间 0x{smap.lo_a:X}..0x{smap.hi_a:X}")
        print(f"对齐后仍不同: {len(diffs)}   (未对齐直接比: {raw})")
        spans = group_spans([(x[0], x) for x in diffs])
        print(f"连续跨度: {len(spans)}")
        for s, e, items in spans[: args.maxspans]:
            ob0 = items[0][1]; ob1 = items[-1][1]
            print(f"  A 0x{s:08X}..0x{e:08X}  B 0x{ob0:08X}..0x{ob1:08X}  (len {e-s+1})")
            print(f"      A: {A[s:e+1].hex(' ')}")
            print(f"      B: {B[ob0:ob1+1].hex(' ')}")


if __name__ == "__main__":
    main()
