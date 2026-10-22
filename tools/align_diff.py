#!/usr/bin/env python3
"""字符串锚点对齐差分：抵消固件重编译造成的整体重排，提取真实改动。

原理
----
两块固件由同源代码重编译而来，链接顺序大体保持 ⇒ 同一函数/同一数据在文件里的
位置发生**分段常量位移**。而块 0 里大量可打印字符串（调试名、字段名、格式串）
在两版之间**内容不变**，可用作锚点：
  1. 抽出两版全部可打印字符串（≥ minlen）
  2. 用内容匹配建立锚点对，求出每个锚点处的位移 delta
  3. 按 delta 把 A 的区间映射到 B 的对应区间
  4. 在对齐后的区间上逐字节比较 ⇒ 剩下的差异才是"真实改动"

输出：
  - 位移直方图（说明重排是分段常量的）
  - 对齐后仍然不同的字节跨度（候选补丁）
"""
import sys, os, json, subprocess, collections, re, hashlib

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
ROOT = r"D:\0_Project\01Test\fw-work\dec"
MINLEN = 12


def decode(img, outdir):
    mf = os.path.join(outdir, "manifest.json")
    if os.path.exists(mf):
        return json.load(open(mf, encoding="utf-8"))
    r = subprocess.run([sys.executable, OLY, img, "--out", outdir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "?")[:200])
    return json.loads(r.stdout)


def block0(img, tag):
    out = os.path.join(ROOT, tag)
    rep = decode(img, out)
    b0 = next(b for b in rep["blocks"] if b["index"] == 0)
    return open(os.path.join(out, b0["decoded_file"]), "rb").read()


def strings(d, minlen=MINLEN):
    """返回 {内容: [偏移,...]}，只取可打印 ASCII 且足够长的串。"""
    out = collections.defaultdict(list)
    pat = re.compile(rb"[\x20-\x7e]{%d,}" % minlen)
    for m in pat.finditer(d):
        out[m.group()].append(m.start())
    return out


def main():
    a_img, b_img, ta, tb = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    A = block0(a_img, ta)
    B = block0(b_img, tb)
    print(f"A {os.path.basename(a_img)}  {len(A)} B")
    print(f"B {os.path.basename(b_img)}  {len(B)} B\n")

    sa, sb = strings(A), strings(B)
    common = set(sa) & set(sb)
    print(f"唯一串 A={len(sa)} B={len(sb)} 共有={len(common)}")

    # 建立锚点对：(a_off, b_off)
    anchors = []
    for s in common:
        for oa in sa[s]:
            for ob in sb[s]:
                anchors.append((oa, ob, s))
    # 若同一内容有多处出现，取 delta 众数配对
    bydelta = collections.defaultdict(list)
    for oa, ob, s in anchors:
        bydelta[ob - oa].append((oa, ob, s))
    print(f"候选锚点对 {len(anchors)}，不同 delta {len(bydelta)} 个\n")

    print("=== 位移直方图（top 15）===")
    for delta, lst in sorted(bydelta.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"  delta={delta:+#10d} ({delta/1024:+8.1f} KB)  锚点 {len(lst)}")

    # 选主 delta 作为基准，但允许分段：用每个 delta 的锚点做覆盖
    # 用 (delta -> 锚点集合) 构建分段映射：对 A 的每个 4KB 页，取覆盖最多的 delta
    CHUNK = 4096
    npages = (len(A) + CHUNK - 1) // CHUNK
    page_delta = collections.defaultdict(collections.Counter)
    for delta, lst in bydelta.items():
        for oa, ob, s in lst:
            page_delta[oa // CHUNK][delta] += 1

    # 平滑：每页取邻域众数
    best = {}
    for p in range(npages):
        c = collections.Counter()
        for q in range(max(0, p - 2), min(npages, p + 3)):
            for dl, n in page_delta.get(q, {}).items():
                c[dl] += n
        if c:
            best[p] = c.most_common(1)[0][0]
    deltas = collections.Counter(best.values())
    print("\n=== 页级 delta 分布（top 10）===")
    for dl, n in deltas.most_common(10):
        print(f"  delta={dl:+#10d}  覆盖 {n} 页 ({n*CHUNK//1024} KB)")

    # 逐页对齐比较
    diffs = []
    for p in range(npages):
        dl = best.get(p)
        if dl is None:
            continue
        oa = p * CHUNK
        ob = oa + dl
        if ob < 0 or ob + CHUNK > len(B):
            continue
        for k in range(CHUNK):
            if oa + k >= len(A) or ob + k >= len(B):
                break
            if A[oa + k] != B[ob + k]:
                diffs.append((oa + k, ob + k))
    print(f"\n=== 对齐后仍不同的字节: {len(diffs)} "
          f"(对齐前为 {sum(1 for k in range(min(len(A),len(B))) if A[k]!=B[k])}) ===")

    if diffs:
        spans = []
        for x, y in diffs:
            if spans and x == spans[-1][1] + 1 and y == spans[-1][3] + 1:
                spans[-1][1] = x; spans[-1][3] = y
            else:
                spans.append([x, x, y, y])
        print(f"连续跨度: {len(spans)}\n")
        for s, e, bs, be in spans[:80]:
            print(f"  A 0x{s:08X}..0x{e:08X}  <->  B 0x{bs:08X}..0x{be:08X}  (len {e-s+1})")
            print(f"      A: {A[s:e+1].hex(' ')}")
            print(f"      B: {B[bs:be+1].hex(' ')}")


if __name__ == "__main__":
    main()
