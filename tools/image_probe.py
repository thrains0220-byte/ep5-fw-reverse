#!/usr/bin/env python3
"""Execute the stock descriptor debug reader, never image hardware or camera I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe


def run_image_probe(image):
    image = Path(image).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError("decoded E-P5 main SHA-256 mismatch")
    build = ROOT / "build/image-probe"
    runner = build_probe(ROOT / "tools/ep5_image_probe.c", build)
    result = subprocess.run([str(runner), str(image)], capture_output=True, text=True, timeout=10, check=True)
    report = json.loads(result.stdout)
    for entry, offset in zip(report["fields"], [0, 4, *range(8, 28, 2), 28], strict=True):
        entry["label"] = entry["label"].strip()
        entry["offset"] = offset
    paths = [ROOT / "tools/ep5_image_probe.c", ROOT / "tools/image_probe.py",
             ROOT / "tools/native_probe.py", build / "cpu.c", build / "isa.inc", runner]
    report.update(main_sha256=MAIN_SHA256, cpu_source_revision=REVISION, entry="0x7e40fba4",
                  frame=dict(register_mask=32, bytes=8), physical_camera_test=False,
                  models=["log header/value sinks return using native frame [a2],16", "synthetic descriptor, read-only"],
                  not_tested=["actual pixel buffer", "0x302 byte order", "YCbCr colour matrix/range", "cache", "residency"],
                  dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run_image_probe(args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
