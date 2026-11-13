#!/usr/bin/env python3
"""Execute stock E-P5 pixel writers and still-photo ISP / heap call setup. Offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe


def reference(r, g, b):
    """Exact signed integer coefficients in both E-P5 routines; no rounding-to-nearest."""
    y = (0x4C8B*r + 0x9646*g + 0x1D2F*b) >> 16
    cb = 128 + ((-0x2B30*r - 0x54D0*g + 0x8000*b) >> 16)
    cr = 128 + ((0x8000*r - 0x6B30*g - 0x14D0*b) >> 16)
    return bytes([y, cb, y, cr])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, default=ROOT/"data/ep5-decoded/00_0100_402c0020.decoded.bin")
    args = parser.parse_args()
    if hashlib.sha256(args.main.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError("requires exact decoded stock E-P5 1.8 MAIN")
    exe = build_probe(ROOT/"tools/ep5_lut_pixel_probe.c", ROOT/"build/lut-pixel-probe")

    def run(*params):
        return subprocess.check_output([str(exe), str(args.main), *map(str, params)], text=True, timeout=15).strip()

    rows = []
    for rgb in [(0, 0, 0), (255, 255, 255), (128, 128, 128), (255, 0, 0), (0, 255, 0),
                (0, 0, 255), (254, 7, 113), (17, 222, 61), (53, 9, 210)]:
        expected = reference(*rgb)
        for path in ("mov", "play"):
            result = int(run(path, *rgb), 16).to_bytes(4, "little")
            if result != expected:
                raise ValueError(f"{path} {rgb}: {result.hex()} != {expected.hex()}")
        rows.append({"rgb": rgb, "two_pixel_bytes": expected.hex(" ")})
    if run("pinhole") != "pinhole 4608 3456 21":
        raise ValueError("pinhole descriptor mismatch")
    if run("pool", 0) != "pool 2 2" or run("pool", 1) != "pool 2 1":
        raise ValueError("heap backend contract mismatch")
    print(json.dumps({"main_sha256": MAIN_SHA256, "cpu_revision": REVISION, "native_color_pairs": rows,
                      "native_pinhole": "packet+76 forwarded, 4608x3456; request+194 = 21. ISP not executed.",
                      "native_art_pool": "mode 3; 29478-byte requests, 2 successes / second failure, matching releases. Backend modeled.",
                      "still_pixel_encoding_proven": False, "available_heap_bytes_proven": False}, indent=2))


if __name__ == "__main__":
    main()
