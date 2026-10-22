#!/usr/bin/env python3
"""同机型"修复前/后"的全块差分：确定修复落在哪个块。

用法: python blockdiff.py <pre.BIN> <post.BIN> <tagA> <tagB>
"""
import sys, os, json, subprocess, hashlib

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


def main():
    a_img, b_img, ta, tb = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    ra = decode(a_img, os.path.join(ROOT, ta))
    rb = decode(b_img, os.path.join(ROOT, tb))
    print(f"A {os.path.basename(a_img)}  sha={ra['source_sha256'][:16]}  往返={ra['roundtrip_identical']}")
    print(f"B {os.path.basename(b_img)}  sha={rb['source_sha256'][:16]}  往返={rb['roundtrip_identical']}\n")
    print(f"{'块':<4}{'flags':<8}{'大小A':>12}{'大小B':>12}{'不同字节':>12}{'跨度':>10}   备注")
    for ba, bb in zip(ra["blocks"], rb["blocks"]):
        i = ba["index"]
        if bb["index"] != i:
            print("块序不同，终止"); break
        pa = os.path.join(ROOT, ta, ba["decoded_file"])
        pb = os.path.join(ROOT, tb, bb["decoded_file"])
        da, db = open(pa, "rb").read(), open(pb, "rb").read()
        if len(da) != len(db):
            print(f"{i:<4}{ba['kind']:<8}{len(da):>12}{len(db):>12}{'-':>12}{'-':>10}   长度不同")
            continue
        diffs = [k for k in range(len(da)) if da[k] != db[k]]
        spans = 0
        if diffs:
            spans = 1
            for a, b in zip(diffs, diffs[1:]):
                if b != a + 1:
                    spans += 1
        same = "完全相同" if not diffs else ""
        pct = 100.0 * len(diffs) / max(1, len(da))
        print(f"{i:<4}{ba['kind']:<8}{len(da):>12}{len(db):>12}{len(diffs):>12}{spans:>10}   "
              f"{same}{'' if diffs else ''}{f'{pct:.2f}% 变化' if diffs else ''}")


if __name__ == "__main__":
    main()
