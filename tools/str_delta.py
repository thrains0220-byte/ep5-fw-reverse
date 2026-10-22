#!/usr/bin/env python3
"""列出两版块 0 之间**新增/消失**的字符串（修复的语义线索往往就在新字符串里）。"""
import sys, os, json, subprocess, collections, re

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
ROOT = r"D:\0_Project\01Test\fw-work\dec"


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


def strs(d, minlen=6):
    out = collections.defaultdict(list)
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minlen, d):
        out[m.group()].append(m.start())
    return out


def main():
    A = block0(sys.argv[1], sys.argv[3])
    B = block0(sys.argv[2], sys.argv[4])
    sa, sb = strs(A), strs(B)
    onlyA = set(sa) - set(sb)
    onlyB = set(sb) - set(sa)
    print(f"修复前唯一串 {len(sa)}   修复后唯一串 {len(sb)}")
    print(f"只在修复前出现: {len(onlyA)}   只在修复后出现: {len(onlyB)}\n")
    print("=== 只在修复后出现（v2.3 新增）===")
    for s in sorted(onlyB, key=lambda x: sb[x][0]):
        print(f"  0x{sb[s][0]:08X}  {s[:100].decode('ascii','replace')!r}")
    print("\n=== 只在修复前出现（v2.3 消失）===")
    for s in sorted(onlyA, key=lambda x: sa[x][0]):
        print(f"  0x{sa[s][0]:08X}  {s[:100].decode('ascii','replace')!r}")


if __name__ == "__main__":
    main()
