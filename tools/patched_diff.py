#!/usr/bin/env python3
"""分析 xdel 的社区 patched 固件归档：解包 -> 解混淆 -> 与原版逐字节差分。

这是"社区为了解锁功能到底改了哪几个字节"的直接证据。
用法: python patched_diff.py <patched.zip> <stock.BIN> <tag>
"""
import sys, os, json, zipfile, subprocess, shutil, tempfile

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
WORK = r"D:\0_Project\01Test\fw-work\patched"


def decode(img, outdir):
    mf = os.path.join(outdir, "manifest.json")
    if os.path.exists(mf):
        return json.load(open(mf, encoding="utf-8"))
    # oly_container.py 自己建目录（exist_ok=False），所以这里不要预建
    r = subprocess.run([sys.executable, OLY, img, "--out", outdir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "?")[:300])
    return json.loads(r.stdout)


def blocks_of(rep, outdir):
    return {b["index"]: os.path.join(outdir, b["decoded_file"]) for b in rep["blocks"]}


def main():
    zpath, stock, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(WORK, exist_ok=True)
    ex = os.path.join(WORK, tag + "_extracted")
    if not os.path.isdir(ex):
        os.makedirs(ex, exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            print(f"归档 {os.path.basename(zpath)} 内容:")
            for n in z.namelist():
                print(f"   {n}  ({z.getinfo(n).file_size} B)")
                z.extract(n, ex)
    cands = []
    for root, _, files in os.walk(ex):
        for f in files:
            p = os.path.join(root, f)
            if f.lower().endswith(".bin"):
                cands.append(p)
            else:
                print(f"   (非 .bin 成员: {f}, {os.path.getsize(p)} B)")
    if not cands:
        print("归档内无 .BIN")
        return
    patched_bin = max(cands, key=os.path.getsize)
    print(f"\npatched 固件: {patched_bin}  ({os.path.getsize(patched_bin)} B)")
    print(f"stock  固件: {stock}  ({os.path.getsize(stock)} B)\n")

    rep_p = decode(patched_bin, os.path.join(WORK, tag + "_patched_dec"))
    rep_s = decode(stock, os.path.join(WORK, tag + "_stock_dec"))
    print(f"patched 往返一致={rep_p['roundtrip_identical']}  sha256={rep_p['source_sha256'][:16]}")
    print(f"stock   往返一致={rep_s['roundtrip_identical']}  sha256={rep_s['source_sha256'][:16]}\n")

    bp = blocks_of(rep_p, os.path.join(WORK, tag + "_patched_dec"))
    bs = blocks_of(rep_s, os.path.join(WORK, tag + "_stock_dec"))
    for idx in sorted(set(bp) & set(bs)):
        dp = open(bp[idx], "rb").read()
        ds = open(bs[idx], "rb").read()
        if len(dp) != len(ds):
            print(f"块{idx}: 长度不同 ({len(dp)} vs {len(ds)}) —— 跳过")
            continue
        diffs = [i for i in range(len(dp)) if dp[i] != ds[i]]
        spans = []
        for i in diffs:
            if spans and i == spans[-1][1] + 1:
                spans[-1][1] = i
            else:
                spans.append([i, i])
        print(f"=== 块{idx}: {len(diffs)} 字节不同, {len(spans)} 个跨度 ===")
        if not spans:
            continue
        base = int(rep_p["blocks"][idx]["header_address"], 0)
        for s, e in spans:
            print(f"   file 0x{s:08X}..0x{e:08X} (len {e-s+1})   rt≈0x{base+s:08X}")
            print(f"      stock  : {ds[s:e+1].hex(' ')}")
            print(f"      patched: {dp[s:e+1].hex(' ')}")
        print()


if __name__ == "__main__":
    main()
