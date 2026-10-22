#!/usr/bin/env python3
"""通用固件区域转储器。

把固件块的任意 file-offset 区域同时以多种宽度解释打印出来，
用于人工判读"这张表到底是什么"。

用法:
    python dump_region.py --blk0 <block0.decoded.bin> \
        --at 0x43030C --len 0xC0 [--base 0x402C0000] [--modes hex,u16,u32]

坐标系:
  --at / --len 是 file offset (十六进制, 0x 前缀);
  --base 是该块的运行时加载基址, 用于同时打印 runtime 地址。
"""
import argparse
import json
import os
import sys


def hexdump(data, base_off, width=16, annotate=None):
    out = []
    annotate = annotate or {}
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hexpart = " ".join("%02X" % b for b in chunk)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        off = base_off + i
        note = ""
        if off in annotate:
            note = "  <- %s" % annotate[off]
        out.append("%08X  %-*s  |%s|%s" % (off, width * 3 - 1, hexpart, txt, note))
    return "\n".join(out)


def interp_u8(data, off):
    return list(data)


def interp_u16(data, off, be=False):
    fmt = "big" if be else "little"
    return [int.from_bytes(data[i:i + 2], fmt) for i in range(off, len(data) - 1, 2)]


def interp_u32(data, off, be=False):
    fmt = "big" if be else "little"
    return [int.from_bytes(data[i:i + 4], fmt) for i in range(off, len(data) - 3, 4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blk0", required=True)
    ap.add_argument("--at", required=True, help="file offset, hex")
    ap.add_argument("--len", dest="length", default="0x100")
    ap.add_argument("--base", default=None, help="runtime base of this block")
    ap.add_argument("--modes", default="hex,u16,u32")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    off = int(args.at, 0)
    length = int(args.length, 0)
    with open(args.blk0, "rb") as f:
        size = os.path.getsize(args.blk0)
        f.seek(max(0, off))
        data = f.read(length)
    if len(data) < length:
        sys.stderr.write("[warn] short read %d/%d (file size %d)\n" % (len(data), length, size))

    base = int(args.base, 0) if args.base else None
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    res = {"file": args.blk0, "file_offset": off, "length": len(data), "file_size": size}

    text = []
    text.append("=" * 100)
    text.append("FILE  : %s" % args.blk0)
    text.append("OFFSET: 0x%X  (+0x%X)   LEN: 0x%X" % (off, off, len(data)))
    if base is not None:
        text.append("RUNTIME: 0x%X  (base 0x%X)" % (base + off, base))
    text.append("=" * 100)

    if "hex" in modes:
        text.append("--- HEX ---")
        text.append(hexdump(data, off))
        text.append("")

    for m in modes:
        if m == "hex":
            continue
        step = {"u16": 2, "u16be": 2, "u32": 4, "u32be": 4, "u8": 1}.get(m, 1)
        if m == "u16":
            vals = interp_u16(data, 0)
        elif m == "u32":
            vals = interp_u32(data, 0)
        elif m == "u16be":
            vals = interp_u16(data, 0, be=True)
        elif m == "u32be":
            vals = interp_u32(data, 0, be=True)
        elif m == "u8":
            vals = interp_u8(data, 0)
        else:
            continue
        text.append("--- %s ---" % m)
        # 16 per line
        for i in range(0, len(vals), 16):
            text.append("  %08X: %s" % (off + i * step, " ".join("%d" % v for v in vals[i:i + 16])))
        text.append("")

    out_txt = "\n".join(text)
    print(out_txt)
    res["text"] = out_txt
    res["u16"] = interp_u16(data, 0)
    res["u32"] = interp_u32(data, 0)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_txt)
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
        print("[written] %s" % args.out)


if __name__ == "__main__":
    main()
