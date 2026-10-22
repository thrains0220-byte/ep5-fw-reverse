#!/usr/bin/env python3
"""两个固件块 0 的字节级差分 + 镜头结构差分（跨机型 AF 修复定位）。"""
import sys, os, json, subprocess, hashlib, struct

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
sys.path.insert(0, r"D:\0_Project\01Test\fw-work")
import ep5_lens


def decode(img, outdir):
    if os.path.isdir(outdir):
        return json.load(open(os.path.join(outdir, "manifest.json"), encoding="utf-8"))
    r = subprocess.run([sys.executable, OLY, img, "--out", outdir],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:300])
    return json.loads(r.stdout)


def block0(rep, outdir):
    b0 = next(b for b in rep["blocks"] if b["index"] == 0)
    return os.path.join(outdir, b0["decoded_file"]), int(b0["header_address"], 0), b0


def main():
    a_img, b_img = sys.argv[1], sys.argv[2]
    a_tag, b_tag = sys.argv[3], sys.argv[4]
    root = r"D:\0_Project\01Test\fw-work\dec"

    out_a = os.path.join(root, a_tag)
    out_b = os.path.join(root, b_tag)
    ra = decode(a_img, out_a)
    rb = decode(b_img, out_b)
    pa, ba, ba_meta = block0(ra, out_a)
    pb, bb, bb_meta = block0(rb, out_b)

    print(f"A {a_tag}: {os.path.basename(a_img)}  size={ra['source_size']}  "
          f"sha256={ra['source_sha256'][:16]}  block0 base=0x{ba:08X} len={ba_meta['payload_size']}")
    print(f"B {b_tag}: {os.path.basename(b_img)}  size={rb['source_size']}  "
          f"sha256={rb['source_sha256'][:16]}  block0 base=0x{bb:08X} len={bb_meta['payload_size']}")
    print(f"往返一致: A={ra['roundtrip_identical']} B={rb['roundtrip_identical']}\n")

    da = open(pa, "rb").read()
    db = open(pb, "rb").read()
    n = min(len(da), len(db))
    diffs = [i for i in range(n) if da[i] != db[i]]
    print(f"=== 块 0 字节差分（A={len(da)} B={len(db)}）===")
    print(f"  不同字节数: {len(diffs)}")

    # 合并成连续跨度
    spans = []
    for i in diffs:
        if spans and i == spans[-1][1] + 1:
            spans[-1][1] = i
        else:
            spans.append([i, i])
    print(f"  连续跨度数: {len(spans)}")
    if spans:
        print(f"  首个跨度: file 0x{spans[0][0]:08X} .. 0x{spans[0][1]:08X}")
        print(f"  末个跨度: file 0x{spans[-1][0]:08X} .. 0x{spans[-1][1]:08X}")
        print("  --- 前 60 个跨度 ---")
        for s, e in spans[:60]:
            A = da[s:e + 1]
            B = db[s:e + 1]
            print(f"    file 0x{s:08X}..0x{e:08X} (len {e-s+1})")
            print(f"        A(rt 0x{ba+s:08X}): {A.hex(' ')}")
            print(f"        B(rt 0x{bb+s:08X}): {B.hex(' ')}")

    # 镜头结构对照
    print("\n=== 镜头识别结构对照 ===")
    for tag, path, base in ((a_tag, pa, ba), (b_tag, pb, bb)):
        d = open(path, "rb").read()
        chains = []
        for lo, hi, g in ep5_lens.find_chain_windows(d, base):
            p = ep5_lens.decode_chain(d, base, lo, hi)
            if len(p) >= 3:
                chains.append([(m, s) for _, m, s in p])
        _, recs = ep5_lens.find_lens_info_table(d, base)
        ids = {f"{mk:02X}:{mo:02X}" for _, _, _, mk, mo, _ in recs}
        print(f"  {tag}: 链={chains[:1]}  LENS_INFO={len(recs)} 条 / {len(ids)} 个唯一 ID")
        globals().setdefault("_res", {})[tag] = (chains, ids)

    A = globals()["_res"][a_tag]
    B = globals()["_res"][b_tag]
    if A[0] and B[0]:
        print(f"  仅 {a_tag} 链有: {sorted(set(A[0][0]) - set(B[0][0]))}")
        print(f"  仅 {b_tag} 链有: {sorted(set(B[0][0]) - set(A[0][0]))}")
    print(f"  仅 {a_tag} LENS_INFO 有: {sorted(A[1] - B[1])}")
    print(f"  仅 {b_tag} LENS_INFO 有: {sorted(B[1] - A[1])}")


if __name__ == "__main__":
    main()
