#!/usr/bin/env python3
"""对齐后残差差异的页级分布 —— 快速定位补丁所在的代码/数据页。

同时对比"同一偏移在两版中的内容差异"与"对齐后差异"，找出真正的改动点。
用法: python align_pages.py <pre.BIN> <post.BIN> <tagA> <tagB> [topN]
"""
import sys, os, json, subprocess, collections, re

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
ROOT = r"D:\0_Project\01Test\fw-work\dec"
CHUNK = 4096
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


def strs(d):
    out = collections.defaultdict(list)
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % MINLEN, d):
        out[m.group()].append(m.start())
    return out


def main():
    a_img, b_img, ta, tb = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    topn = int(sys.argv[5]) if len(sys.argv) > 5 else 25
    A, B = block0(a_img, ta), block0(b_img, tb)
    sa, sb = strs(A), strs(B)
    common = set(sa) & set(sb)

    bydelta = collections.defaultdict(list)
    for s in common:
        for oa in sa[s]:
            for ob in sb[s]:
                bydelta[ob - oa].append(oa)

    npages = (len(A) + CHUNK - 1) // CHUNK
    page_delta = collections.defaultdict(collections.Counter)
    for dl, lst in bydelta.items():
        for oa in lst:
            page_delta[oa // CHUNK][dl] += 1
    best = {}
    for p in range(npages):
        c = collections.Counter()
        for q in range(max(0, p - 2), min(npages, p + 3)):
            for dl, n in page_delta.get(q, {}).items():
                c[dl] += n
        if c:
            best[p] = c.most_common(1)[0][0]

    hits = collections.Counter()
    samples = collections.defaultdict(list)
    for p in range(npages):
        dl = best.get(p)
        if dl is None:
            continue
        oa, ob = p * CHUNK, p * CHUNK + dl
        if ob < 0 or ob + CHUNK > len(B):
            continue
        n = 0
        for k in range(CHUNK):
            if A[oa + k] != B[ob + k]:
                n += 1
                if len(samples[p]) < 6:
                    samples[p].append((oa + k, ob + k))
        if n:
            hits[p] = n

    print(f"总残差差异字节: {sum(hits.values())}")
    print(f"有差异的页: {len(hits)} / {npages}\n")
    print(f"=== 差异字节最多的 {topn} 个页（4KB）===")
    for p, n in hits.most_common(topn):
        dl = best.get(p)
        # 该页内的字符串上下文（判断是代码区还是数据区）
        ctx = []
        for s, offs in sa.items():
            for o in offs:
                if p * CHUNK <= o < (p + 1) * CHUNK:
                    ctx.append(s[:40].decode("ascii", "replace"))
                    break
        print(f"  page 0x{p:05X} (rt 0x{p*CHUNK:08X})  差异 {n:4d} B  delta={dl:+d}")
        print(f"      页内字符串: {ctx[:4]}")
        for a, b in samples[p][:3]:
            print(f"      A 0x{a:08X}={A[a]:02X}  B 0x{b:08X}={B[b]:02X}")


if __name__ == "__main__":
    main()
