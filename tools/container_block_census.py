#!/usr/bin/env python3
"""列出官方 .BIN 容器里每个块的索引/kind/基址/大小，并按内容特征粗分类。

目的：确认「艺术滤镜数据（ARTFIL 分区）」是否随固件 .BIN 一起下发。
只读，不修改任何文件。
"""
import argparse
import hashlib
import lzma
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oly_container as oc

ART_HINT = re.compile(
    r"art_|artf|arteff|filter|dramatic|tone|lut|pastel|vignette|ghosting|cross.?process|grain|"
    r"sharpen|monochrome|popcolor|pinhole|film|retro|sepia|bloom|softfocus|high.?key|"
    r"water.?paint|color.?shift|courant|process|saturation|hue",
    re.I,
)
CODE_HINT = re.compile(r"[\x01-\x04]|__|abort|main|Error|assert", re.I)


def classify(payload: bytes) -> str:
    head = payload[:64]
    printable = sum(1 for b in head if 32 <= b < 127)
    if payload[:4] == b"\x7fELF":
        return "elf"
    if printable > 48:
        return "text"
    if payload[:2] in (b"PK", b"\x1f\x8b"):
        return "archive"
    if len(set(payload[:256])) <= 2:
        return "uniform"
    return "binary"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--art-hits", action="store_true", help="只列出命中艺术滤镜关键词的块")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    data = args.image.read_bytes()
    blocks = oc.parse(data)
    rows = []
    for b in blocks:
        strings = [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{5,}", b.payload)]
        art = [s for s in strings if ART_HINT.search(s)]
        rows.append(
            {
                "index": b.index,
                "kind": hex(b.kind),
                "header_address": hex(b.address),
                "size": len(b.payload),
                "class": classify(b.payload),
                "sha256_8": hashlib.sha256(b.payload).hexdigest()[:8],
                "n_strings": len(strings),
                "art_hits": art[:12],
                "first_strings": strings[:6],
            }
        )

    if args.art_hits:
        for r in rows:
            if r["art_hits"]:
                print(f"[{r['index']:3d}] kind={r['kind']} addr={r['header_address']} size={r['size']:9d} class={r['class']}")
                for s in r["art_hits"]:
                    print(f"        {s!r}")
    else:
        print(f"total blocks: {len(rows)}")
        for r in rows:
            print(
                f"[{r['index']:3d}] kind={r['kind']} addr={r['header_address']} "
                f"size={r['size']:9d} class={r['class']:8s} strings={r['n_strings']:5d} art={len(r['art_hits']):3d} {r['sha256_8']}"
            )

    if args.json:
        import json

        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
