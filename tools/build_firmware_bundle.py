#!/usr/bin/env python3
"""构建 firmware/ 固件资料包（用于随仓库分发原始固件与社区归档）。

产出结构：
    firmware/
      README.md            来源 / 许可 / 校验说明
      MANIFEST.sha256      每个文件的 SHA-256（含解压缩后原始 .BIN 的哈希）
      stock/<model>/*.BIN.lzma      原版固件（LZMA 无损）
      pre_fix/*.BIN.lzma            修复前基线固件（本工具现压）
      community/*.zip|*.rar         社区改机归档
      notes/                        更新协议 / 服务器报文 / 站点索引等文本资料

设计要点：
  * 原版 .BIN 一律以 **LZMA** 存放（已抽样验证 SHA-256 完全一致）；
    MANIFEST 同时记录 **压缩件** 与 **原始 .BIN** 两个哈希，可随时校验。
  * 社区归档（ZIP/RAR）本身已压缩，原样存放。

用法:
    python tools/build_firmware_bundle.py [--dst firmware] [--lzma-preset 6]
"""
import argparse
import hashlib
import lzma
import os
import shutil
import sys

X = r"D:\0_Project\01Test\fw-work\fw2_xdel"
NOTES = r"D:\0_Project\01Test\fw-work\xdel_notes"
STOCK_DIRS = [
    "em1", "em10", "em10mk2", "em10mk3", "em10mk4", "em1mk2", "em1mk3",
    "em1x", "em5", "em5mk2", "em5mk3", "penepl1", "penepl1s", "penepl3",
    "penepl5", "penepl6", "penepl7", "penepl8", "penepl9", "penf",
]
NOTE_SUBDIRS = ["olyhttp", "omsrv", "orig_index", "web"]


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=None, help="输出目录（默认 <repo>/firmware）")
    ap.add_argument("--lzma-preset", type=int, default=6)
    ap.add_argument("--skip-pre-fix", action="store_true")
    args = ap.parse_args()

    dst = args.dst or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
    os.makedirs(dst, exist_ok=True)
    entries = []      # (relpath, sha256)
    orig_entries = []  # (relpath_of_original, sha256)

    # ---- 1. stock 原版（复用已有的 .BIN.lzma）----
    stock_root = os.path.join(dst, "stock")
    n = 0
    for d in STOCK_DIRS:
        src = os.path.join(X, d)
        if not os.path.isdir(src):
            continue
        out = os.path.join(stock_root, d)
        os.makedirs(out, exist_ok=True)
        for f in sorted(os.listdir(src)):
            fp = os.path.join(src, f)
            if not os.path.isfile(fp):
                continue
            if f.lower().endswith(".bin.lzma"):
                outp = os.path.join(out, f)
                if not os.path.exists(outp):
                    shutil.copy2(fp, outp)
                entries.append(("stock/%s/%s" % (d, f), sha256(outp)))
                n += 1
            elif f.lower().endswith(".bin"):
                lz = f + ".lzma"
                lp = os.path.join(src, lz)
                dstp = os.path.join(out, lz)
                if not os.path.exists(dstp):
                    if os.path.exists(lp):
                        shutil.copy2(lp, dstp)
                    else:
                        with open(fp, "rb") as fi, \
                             lzma.open(dstp, "wb", preset=args.lzma_preset) as fo:
                            shutil.copyfileobj(fi, fo, 1 << 20)
                entries.append(("stock/%s/%s" % (d, lz), sha256(dstp)))
                # 原始 .BIN 本体不入包，只在 ORIG 段记录哈希
                orig_entries.append(("stock/%s/%s" % (d, f), sha256(fp)))
                n += 1
    print("[stock] %d 个固件" % n, flush=True)

    # ---- 2. pre_fix 修复前基线 ----
    if not args.skip_pre_fix:
        src = os.path.join(X, "pre_fix")
        out = os.path.join(dst, "pre_fix")
        os.makedirs(out, exist_ok=True)
        n = 0
        for f in sorted(os.listdir(src)):
            fp = os.path.join(src, f)
            if not os.path.isfile(fp) or not f.lower().endswith(".bin"):
                continue
            if os.path.getsize(fp) == 0:
                continue
            lz = f + ".lzma"
            dstp = os.path.join(out, lz)
            if not os.path.exists(dstp):
                with open(fp, "rb") as fi, \
                     lzma.open(dstp, "wb", preset=args.lzma_preset) as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)
            entries.append(("pre_fix/%s" % lz, sha256(dstp)))
            orig_entries.append(("pre_fix/%s" % f, sha256(fp)))
            n += 1
            print("  [pre_fix] %s" % f, flush=True)
        print("[pre_fix] %d 个固件" % n, flush=True)

    # ---- 3. community 社区改机归档 ----
    com_root = os.path.join(dst, "community")
    os.makedirs(com_root, exist_ok=True)
    seen = {}
    n = 0
    for sub in ("patched", "patched_yandex"):
        src = os.path.join(X, sub)
        if not os.path.isdir(src):
            continue
        for f in sorted(os.listdir(src)):
            fp = os.path.join(src, f)
            if not os.path.isfile(fp) or not f.lower().endswith((".zip", ".rar")):
                continue
            h = sha256(fp)
            if h in seen:
                print("  [dup] %s 与 %s 同内容，跳过" % (f, seen[h]), flush=True)
                continue
            seen[h] = f
            shutil.copy2(fp, os.path.join(com_root, f))
            entries.append(("community/%s" % f, h))
            n += 1
    print("[community] %d 个归档" % n, flush=True)

    # ---- 4. notes 文本资料 ----
    note_root = os.path.join(dst, "notes")
    n = 0
    for sub in NOTE_SUBDIRS:
        src = os.path.join(NOTES, sub)
        if not os.path.isdir(src):
            continue
        for root, _, files in os.walk(src):
            for f in sorted(files):
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, src).replace(os.sep, "/")
                outp = os.path.join(note_root, sub, rel)
                os.makedirs(os.path.dirname(outp), exist_ok=True)
                shutil.copy2(fp, outp)
                entries.append(("notes/%s/%s" % (sub, rel), sha256(outp)))
                n += 1
    # 7-Zip 许可与版本信息（工具本身不随包分发）
    for extra in ("tools/7z_hash.txt",):
        fp = os.path.join(NOTES, extra)
        if os.path.isfile(fp):
            outp = os.path.join(note_root, extra.replace("/", os.sep))
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            shutil.copy2(fp, outp)
            entries.append(("notes/%s" % extra, sha256(outp)))
            n += 1
    print("[notes] %d 个文件" % n, flush=True)

    # ---- 5. MANIFEST ----
    # 去重: 同一路径可能被登记两次（.BIN.lzma 既被 .BIN.lzma 分支、又被 .BIN 分支登记）
    uniq = {}
    for rel, h in entries:
        uniq[rel] = h
    entries = sorted(uniq.items())

    man = os.path.join(dst, "MANIFEST.sha256")
    with open(man, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Olympus firmware corpus - SHA-256 manifest\n")
        f.write("# paths are relative to firmware/\n")
        f.write("# ARCHIVE section: files actually stored in this repository\n")
        f.write("# ORIG    section: SHA-256 of the ORIGINAL .BIN recovered from the .BIN.lzma\n")
        f.write("#\n# --- ARCHIVE ---\n")
        for rel, h in entries:
            f.write("%s  %s\n" % (h, rel))
        f.write("#\n# --- ORIG ---\n")
        for rel, h in sorted(orig_entries):
            f.write("%s  %s\n" % (h, rel))
    print("[manifest] %d 条归档 + %d 条原始哈希 -> %s" % (
        len(entries), len(orig_entries), man), flush=True)
    print("完成。")


if __name__ == "__main__":
    main()
