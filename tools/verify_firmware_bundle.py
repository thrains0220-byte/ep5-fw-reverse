#!/usr/bin/env python3
"""校验 firmware/ 固件资料包的完整性。

两项检查：
  1. **归档段**：MANIFEST 里列出的每个实际文件，其 SHA-256 必须与清单一致；
  2. **ORIG 段**：每个 `X.BIN.lzma` 解压后（LZMA 无损）必须还原出与
     ORIG 清单同名的原始 `X.BIN`，且 SHA-256 一致 —— 证明压缩未损坏固件本体。

用法:
    python tools/verify_firmware_bundle.py [--pkg firmware] [--deep]
"""
import argparse
import hashlib
import lzma
import os
import sys


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path, chunk=1 << 20):
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
    ap.add_argument("--pkg", default=None)
    ap.add_argument("--deep", action="store_true",
                    help="逐个解压 .lzma 还原原始 .BIN 并比对（较慢）")
    args = ap.parse_args()

    pkg = args.pkg or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
    man = os.path.join(pkg, "MANIFEST.sha256")
    arch, orig = [], []
    section = None
    with open(man, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if ln.startswith("# --- ARCHIVE"):
                section = "a"; continue
            if ln.startswith("# --- ORIG"):
                section = "o"; continue
            if not ln or ln.startswith("#"):
                continue
            h, p = ln.split("  ", 1)
            (arch if section == "a" else orig).append((h, p))

    print("MANIFEST: 归档 %d 条, ORIG %d 条" % (len(arch), len(orig)))

    bad = 0
    for h, p in arch:
        fp = os.path.join(pkg, p.replace("/", os.sep))
        if not os.path.exists(fp):
            print("  缺失: %s" % p); bad += 1; continue
        got = sha256_file(fp)
        if got != h:
            print("  哈希不符: %s" % p); bad += 1
    print("归档段校验: %d 个文件, %d 个异常" % (len(arch), bad))

    obad = 0
    ochecked = 0
    for h, p in orig:
        lz = p + ".lzma"
        lzp = os.path.join(pkg, lz.replace("/", os.sep))
        if not os.path.exists(lzp):
            print("  缺压缩件: %s" % lz); obad += 1; continue
        if not args.deep:
            continue
        ochecked += 1
        with lzma.open(lzp, "rb") as f:
            raw = f.read()
        got = sha256_bytes(raw)
        if got != h:
            print("  解压后哈希不符: %s -> %s" % (p, lz)); obad += 1
    if args.deep:
        print("ORIG 段深校验: %d 个固件, %d 个异常" % (ochecked, obad))
    else:
        print("ORIG 段: 加 --deep 做解压还原比对")

    total = sum(os.path.getsize(os.path.join(pkg, p.replace("/", os.sep)))
                for _, p in arch if os.path.exists(os.path.join(pkg, p.replace("/", os.sep))))
    print("资料包体积: %.1f MB" % (total / 1048576.0))

    sys.exit(1 if (bad or obad) else 0)


if __name__ == "__main__":
    main()
