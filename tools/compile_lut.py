#!/usr/bin/env python3
"""Build a 17^3 red-fastest RGB16LE LUT for the experimental colour kernel.

With no .cube input, creates an original, uncalibrated warm-negative look.
This file is kernel data, not a camera-loadable firmware/plugin package.
"""
import argparse
import math
from pathlib import Path
import shlex
import struct

SIDE = 17
VALUES = SIDE ** 3 * 3


def compile_cube(text):
    if len(text) > 1_000_000:
        raise ValueError("LUT text exceeds 1 MB")
    headers, values = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        key = fields[0]
        if key in ("TITLE", "LUT_3D_SIZE", "DOMAIN_MIN", "DOMAIN_MAX"):
            if key in headers or values:
                raise ValueError(f"line {number}: duplicate or late header {key}")
            headers.add(key)
            if key == "TITLE":
                if len(fields) != 2:
                    raise ValueError("TITLE must be one quoted string")
            elif key == "LUT_3D_SIZE":
                if fields != [key, "17"]:
                    raise ValueError("only LUT_3D_SIZE 17 is supported")
            else:
                expected = 0.0 if key == "DOMAIN_MIN" else 1.0
                if len(fields) != 4 or any(float(v) != expected for v in fields[1:]):
                    raise ValueError("only normalized DOMAIN_MIN 0 0 0 / DOMAIN_MAX 1 1 1 are supported")
            continue
        if "LUT_3D_SIZE" not in headers or len(fields) != 3:
            raise ValueError(f"line {number}: expected three RGB values after LUT_3D_SIZE")
        for field in fields:
            value = float(field)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"line {number}: values must be finite and within [0,1]")
            values.append(round(value * 65535))
        if len(values) > VALUES:
            raise ValueError("too many LUT entries")
    if len(values) != VALUES:
        raise ValueError(f"expected {SIDE ** 3} RGB entries, got {len(values) // 3}")
    return struct.pack(f"<{VALUES}H", *values)


def warm_negative():
    values = []
    for bi in range(SIDE):
        for gi in range(SIDE):
            for ri in range(SIDE):
                rgb = (ri / 16, gi / 16, bi / 16)
                y = sum(c * w for c, w in zip(rgb, (0.2126, 0.7152, 0.0722)))
                for channel, colour in enumerate(rgb):
                    x = y + (colour - y) * 0.90
                    x = 0.025 + 0.95 * (x + 0.12 * (x - 0.5) * (1 - abs(2 * x - 1)))
                    x += (0.008, 0.0, -0.010)[channel] * (1 - abs(2 * y - 1))
                    values.append(round(max(0, min(1, x)) * 65535))
    return struct.pack(f"<{VALUES}H", *values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cube", nargs="?", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.cube:
        with args.cube.open(encoding="utf-8-sig") as stream:
            text = stream.read(1_000_001)
        data = compile_cube(text)
    else:
        data = warm_negative()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as stream:
        stream.write(data)
    print(f"{args.out}: {len(data)} bytes; RGB16LE, 17^3, red fastest; camera adapter not implemented")


if __name__ == "__main__":
    main()
