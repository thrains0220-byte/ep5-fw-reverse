#!/usr/bin/env python3
"""批量分析 xdel 的社区 patched 固件归档：解包 -> 解混淆 -> 与原版逐字节差分。

同时输出两种偏移：
  - decoded file offset : 解混淆后的块内偏移（便于反汇编）
  - raw container offset: 原始 .BIN 文件内偏移（与社区 fc 补丁配方格式一致）

用法: python patched_batch.py
"""
import sys, os, json, zipfile, subprocess, shutil

OLY = r"D:\0_Project\01Test\ep5-fw-reverse\tools\oly_container.py"
WORK = r"D:\0_Project\01Test\fw-work\patched"
X = r"D:\0_Project\01Test\fw-work\fw2_xdel"
# 完整版 7-Zip（含 RAR 解码器）。7zr.exe 只有 7z 格式支持，不能解 RAR。
SEVEN_ZIP = r"D:\0_Project\01Test\fw-work\xdel_notes\tools\7z_full\7z.exe"

DECODE_ORDER = (1, 3, 0, 2, 6, 4, 7, 5, 11, 10, 9, 8, 13, 14, 12, 15)

PAIRS = [
    ("e-m5ii_v41.zip",     "em5mk2/OLY_E_118_4100_0000_0000.BIN",   "E-M5 II v4.1"),
    ("e-m1-ii-v34.zip",    "em1mk2/OLY_E_125_3400_0000_0000.BIN",   "E-M1 II v3.4"),
    ("e-m1-ii-v36.zip",    "em1mk2/OLY_E_125_3600_0000_0000.BIN",   "E-M1 II v3.6"),
    ("e-m1-iii-v12.zip",   "em1mk3/OLY_E_139_1201_0000_0000.BIN",   "E-M1 III v1.2"),
    ("e-m5-iii-v14.zip",   "em5mk3/OLY_E_137_1400_0000_0000.BIN",   "E-M5 III v1.4"),
    ("pen_f_v31.zip",      "penf/OLY_E_122_3100_0000_0000.BIN",     "PEN-F v3.1"),
    ("e-m10ii_v13.rar",    "em10mk2/OLY_E_120_1300_0000_0000.BIN",  "E-M10 II v1.3"),
    ("e_m10ii_v14.rar",    "em10mk2/OLY_E_120_1400_0000_0000.BIN",  "E-M10 II v1.4"),
    ("e-m1ii_v30.rar",     "em1mk2/OLY_E_125_3001_0000_0000.BIN",   "E-M1 II v3.0"),
    ("e-m1_v46.rar",       "em1/OLY_E_109_4600_0000_0000.BIN",      "E-M1 v4.6"),
    ("e_m10iii_v12.rar",   "em10mk3/OLY_E_130_1200_0000_0000.BIN",  "E-M10 III v1.2"),
    ("pen-e-pl9_v11.rar",  "penepl9/OLY_E_133_1101_0000_0000.BIN",  "E-PL9 v1.1"),
]


def _payload_start(b):
    """块 payload 在原始 .BIN 文件中的起点（文件偏移，不是 flash 地址）。"""
    v = b.get("container_offset")
    if v is not None:
        return (int(v, 0) if isinstance(v, str) else int(v)) + 32
    return int(b["header_address"], 0) + 32


def _flash_start(b):
    """块在 flash 中的起始地址（= container header 的 address 字段）。"""
    return int(b["header_address"], 0)


def raw_offset(dec_off, payload_start):
    """解混淆块内偏移 -> 原始 .BIN 文件内偏移（经 16 列置换）。"""
    o = dec_off % 16
    k = dec_off // 16
    return payload_start + DECODE_ORDER[o] + 16 * k


def decode(img, outdir):
    mf = os.path.join(outdir, "manifest.json")
    if os.path.exists(mf):
        return json.load(open(mf, encoding="utf-8"))
    r = subprocess.run([sys.executable, OLY, img, "--out", outdir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "?")[:200])
    return json.loads(r.stdout)


def extract(arc, tag):
    ex = os.path.join(WORK, tag + "_ex")
    os.makedirs(ex, exist_ok=True)
    try:
        if arc.lower().endswith(".zip"):
            with zipfile.ZipFile(arc) as z:
                z.extractall(ex)
        elif SEVEN_ZIP and os.path.exists(SEVEN_ZIP):
            # 完整版 7-Zip（含 RAR 解码器）；7zr.exe 不含 RAR 过滤器，不可用
            subprocess.run([SEVEN_ZIP, "x", "-y", "-o" + ex, arc],
                           capture_output=True)
        else:
            # 退路：bsdtar 解 RAR 时可能因不支持过滤器而返回非零，但文件已解出
            subprocess.run(["tar.exe", "-xf", arc, "-C", ex],
                           capture_output=True)
    except Exception as e:
        return None, str(e)
    bins = []
    for root, _, files in os.walk(ex):
        for f in files:
            if f.lower().endswith(".bin"):
                p = os.path.join(root, f)
                bins.append((p, os.path.getsize(p)))
    if not bins:
        return None, "归档内无 .BIN"
    return max(bins, key=lambda t: t[1])[0], None


def main():
    os.makedirs(WORK, exist_ok=True)
    summary = []
    for arc, stockrel, label in PAIRS:
        arc_path = os.path.join(X, "patched", arc)
        stock = os.path.join(X, stockrel.replace("/", os.sep))
        tag = arc.rsplit(".", 1)[0]
        print("=" * 78)
        print(f"### {label}   归档={arc}")
        if not os.path.exists(arc_path):
            print("  归档缺失，跳过\n"); continue
        if not os.path.exists(stock):
            print("  原版固件缺失，跳过\n"); continue
        pbin, err = extract(arc_path, tag)
        if pbin is None:
            print(f"  解包失败: {err}\n"); continue
        print(f"  patched: {os.path.basename(pbin)} ({os.path.getsize(pbin)} B)")
        try:
            rp = decode(pbin, os.path.join(WORK, tag + "_pdec"))
            rs = decode(stock, os.path.join(WORK, tag + "_sdec"))
        except Exception as e:
            print(f"  解混淆失败: {e}\n"); continue
        print(f"  patched sha256={rp['source_sha256'][:16]}  stock sha256={rs['source_sha256'][:16]}"
              f"  往返一致 p/s={rp['roundtrip_identical']}/{rs['roundtrip_identical']}")
        rec = {"label": label, "archive": arc, "patched_bin": os.path.basename(pbin),
               "patched_sha256": rp["source_sha256"], "stock_sha256": rs["source_sha256"],
               "patches": []}
        for b in rp["blocks"]:
            i = b["index"]
            sb = next((x for x in rs["blocks"] if x["index"] == i), None)
            if not sb:
                continue
            dp = open(os.path.join(WORK, tag + "_pdec", b["decoded_file"]), "rb").read()
            ds = open(os.path.join(WORK, tag + "_sdec", sb["decoded_file"]), "rb").read()
            if len(dp) != len(ds):
                continue
            diffs = [k for k in range(len(dp)) if dp[k] != ds[k]]
            if not diffs:
                continue
            spans = []
            for k in diffs:
                if spans and k == spans[-1][1] + 1:
                    spans[-1][1] = k
                else:
                    spans.append([k, k])
            pstart = _payload_start(b)
            sstart = _payload_start(sb)
            pflash = _flash_start(b)
            print(f"  块{i}: {len(diffs)} 字节不同, {len(spans)} 跨度"
                  f"   (flash base 0x{pflash:08X}, .BIN 文件 payload 起点 0x{pstart:08X})")
            for s, e in spans:
                ro = raw_offset(s, pstart)
                print(f"    decoded 0x{s:08X}..0x{e:08X} | flash 0x{pflash+s:08X}"
                      f" | .BIN文件 0x{ro:08X}..0x{ro+(e-s):08X}"
                      f"  stock={ds[s:e+1].hex(' ')}  patched={dp[s:e+1].hex(' ')}")
                rec["patches"].append({
                    "block": i, "decoded_start": hex(s), "decoded_end": hex(e),
                    "flash_start": hex(pflash + s),
                    "bin_file_start": hex(ro), "bin_file_end": hex(ro + (e - s)),
                    "stock": ds[s:e + 1].hex(" "), "patched": dp[s:e + 1].hex(" "),
                    "stock_bytes": list(ds[s:e + 1]), "patched_bytes": list(dp[s:e + 1]),
                })
        summary.append(rec)
        print()
    out = os.path.join(WORK, "patched_summary.json")
    json.dump(summary, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("汇总已写入", out)


if __name__ == "__main__":
    main()
