#!/usr/bin/env python3
"""只做镜头识别结构对照（链 + LENS_INFO 表），用于跨版本比较。"""
import sys, os, json, subprocess

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
sys.path.insert(0, r"D:\0_Project\01Test\fw-work")
import ep5_lens


def decode(img, outdir):
    if os.path.isdir(outdir):
        return json.load(open(os.path.join(outdir, "manifest.json"), encoding="utf-8"))
    os.makedirs(outdir, exist_ok=True)
    r = subprocess.run([sys.executable, OLY, img, "--out", outdir],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:300])
    return json.loads(r.stdout)


def analyse(img, tag, root):
    out = os.path.join(root, tag)
    rep = decode(img, out)
    b0 = next(b for b in rep["blocks"] if b["index"] == 0)
    path = os.path.join(out, b0["decoded_file"])
    base = int(b0["header_address"], 0)
    d = open(path, "rb").read()
    chains = []
    for lo, hi, g in ep5_lens.find_chain_windows(d, base):
        p = ep5_lens.decode_chain(d, base, lo, hi)
        if len(p) >= 3:
            chains.append([(m, s) for _, m, s in p])
    _, recs = ep5_lens.find_lens_info_table(d, base)
    ids = {f"{mk:02X}:{mo:02X}" for _, _, _, mk, mo, _ in recs}
    makers = {}
    for _, c, s, mk, mo, _ in recs:
        makers.setdefault(f"{mk:02X}", set()).add(f"{mo:02X}")
    return {
        "tag": tag, "file": os.path.basename(img),
        "sha256": rep["source_sha256"][:16], "base": hex(base),
        "chains": chains, "lens_ids": ids, "recs": len(recs), "makers": makers,
        "chain_addr": hex(base + ep5_lens.find_chain_windows(d, base)[0][0]) if ep5_lens.find_chain_windows(d, base) else None,
    }


def main():
    root = r"D:\0_Project\01Test\fw-work\dec"
    specs = []
    for a in sys.argv[1:]:
        parts = a.split("=")
        specs.append((parts[0], parts[1]))
    res = []
    for tag, img in specs:
        try:
            r = analyse(img, tag, root)
            res.append(r)
            print(f"{tag:12s} {r['file']}")
            print(f"   块0 base={r['base']}  比较链窗口 @ {r['chain_addr']}")
            for i, c in enumerate(r["chains"]):
                print(f"   链#{i} ({len(c)} 项): " + " ".join(f"{m:02X}:{s:02X}" for m, s in c))
            print(f"   LENS_INFO 表 {r['recs']} 条 / {len(r['lens_ids'])} 个唯一 ID")
            print(f"   厂商码分组: " + " | ".join(
                f"{k}:{' '.join(sorted(v))}" for k, v in sorted(r["makers"].items())))
        except Exception as e:
            print(f"{tag}: 失败 {e}")
        print()

    if len(res) >= 2:
        a, b = res[0], res[1]
        print("=" * 78)
        print(f"结构差分 {a['tag']}  vs  {b['tag']}")
        if a["chains"] and b["chains"]:
            ca, cb = set(a["chains"][0]), set(b["chains"][0])
            print(f"  仅 {a['tag']} 链有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(ca - cb)))
            print(f"  仅 {b['tag']} 链有: " + " ".join(f"{m:02X}:{s:02X}" for m, s in sorted(cb - ca)))
        print(f"  仅 {a['tag']} 表有: " + " ".join(sorted(a["lens_ids"] - b["lens_ids"])))
        print(f"  仅 {b['tag']} 表有: " + " ".join(sorted(b["lens_ids"] - a["lens_ids"])))
        ma, mb = a["makers"], b["makers"]
        for k in sorted(set(ma) | set(mb)):
            va, vb = ma.get(k, set()), mb.get(k, set())
            if va != vb:
                print(f"  厂商码 {k}: {a['tag']}={sorted(va)}  {b['tag']}={sorted(vb)}"
                      f"   +{sorted(vb-va)} -{sorted(va-vb)}")


if __name__ == "__main__":
    main()
