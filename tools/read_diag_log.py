"""Decode EP5LUT/DIAG.LOG records pulled from an E-P5 SD card."""
from __future__ import annotations
import argparse, json, struct
from pathlib import Path

RECORD = 128
MAGIC = 0x47414944

def decode(data: bytes):
    if len(data) % RECORD:
        raise ValueError(f"length {len(data)} is not a multiple of {RECORD}")
    rows = []
    for off in range(0, len(data), RECORD):
        p = data[off:off + RECORD]
        magic, seq, req, buf, w, h, sw, sh, glob, ctx = struct.unpack_from("<IIIIHHHHII", p)
        if magic != MAGIC:
            raise ValueError(f"record {off // RECORD}: bad magic {magic:#x}")
        rows.append({
            "index": off // RECORD, "sequence": seq,
            "jpeg_request": hex(req), "buffer_addr": hex(buf),
            "width": w, "height": h, "store_w": sw, "store_h": sh,
            "global_addr": hex(glob), "context": hex(ctx),
            "fmt_byte36": p[32], "sample_hex": p[33:49].hex(),
            "pool_ptr": hex(struct.unpack_from("<I", p, 52)[0]),
            "flags": struct.unpack_from("<I", p, 56)[0],
        })
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    rows = decode(args.log.read_bytes())
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
