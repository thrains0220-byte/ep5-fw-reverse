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


def run_art_handoff(image):
    image = Path(image).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 main SHA-256 mismatch')
    build = ROOT / 'build/art-handoff'
    runner = build_probe(ROOT / 'tools/ep5_image_probe.c', build)
    cases = []
    for mode in ('art-full', 'art-small'):
        result = subprocess.run([str(runner), str(image), mode], capture_output=True, text=True, timeout=10, check=True)
        cases.append(dict(name=mode, **json.loads(result.stdout)))
    paths = [ROOT / 'tools/ep5_image_probe.c', ROOT / 'tools/image_probe.py',
             ROOT / 'tools/native_probe.py', build / 'cpu.c', build / 'isa.inc', runner]
    return dict(main_sha256=MAIN_SHA256, cpu_source_revision=REVISION, cases=cases,
                entry='0x7e3ed85c', frame=dict(register_mask=0xb0, bytes=56),
                codec='0x7e3f4884', codec_call='0x7e3ed8d1', codec_frame=dict(register_mask=0xf0, bytes=16),
                globals=dict(buffer='0x605f455c', geometry='0x605f4560'), physical_camera_test=False,
                models=['REC log returns with [d2,a2],12', 'codec captures request and returns 0x1234 with [d2,d3,a2,a3],16',
                        'ART context and existing buffer globals are synthetic read-only inputs'],
                not_tested=['actual image production', 'buffer format/colour', 'normal-still routing', 'cache',
                            'code residency', 'JPEG encoding', 'camera installation/recovery'],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument('--art-handoff', action='store_true', help='execute the original ART to JPEG request builder')
    args = parser.parse_args()
    report = run_art_handoff(args.image) if args.art_handoff else run_image_probe(args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
