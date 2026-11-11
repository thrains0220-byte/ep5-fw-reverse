#!/usr/bin/env python3
"""Execute bounded stock boot/ART producer contracts; no firmware or device writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe


def run_contracts(image):
    image = Path(image).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 main SHA-256 mismatch')
    build = ROOT / 'build/native-contracts'
    runner = build_probe(ROOT / 'tools/ep5_contract_probe.c', build)
    cases = {}
    for name in ('boot', 'allocate', 'existing', 'failed', 'cropped', 'neutral', 'pinhole'):
        result = subprocess.run([str(runner), str(image), name], capture_output=True,
                                text=True, check=True, timeout=10)
        cases[name] = json.loads(result.stdout)
    boot = cases.pop('boot')
    start = (boot['destination'] & 0x3fffffff) | 0x40000000
    boot['covers_module'] = start <= 0x7e128010 and start + boot['bytes'] >= 0x7e130000
    paths = [ROOT / 'tools/ep5_contract_probe.c', ROOT / 'tools/native_contracts.py',
             ROOT / 'tools/native_probe.py', build / 'cpu.c', build / 'isa.inc', runner]
    return dict(main_sha256=MAIN_SHA256, cpu_source_revision=REVISION, boot=boot,
                allocation={name: cases[name] for name in ('allocate', 'existing', 'failed', 'cropped')},
                filters={name: cases[name] for name in ('neutral', 'pinhole')},
                physical_camera_test=False,
                models=['logging/trace/error sinks return with native frames',
                        'allocator returns a synthetic address or zero, never creates pixels',
                        'JPEG sink captures the original request and returns 0x1234 without encoding',
                        'boot stops at the flash reader entry; no flash read is modeled',
                        'packet/task/message fixtures are synthetic; original geometry and selection execute'],
                not_tested=['physical flash read/boot', 'later residency/overwrite', 'actual allocator/ISP execution',
                            'pixel format/range', 'cache/task timing', 'JPEG encoding', 'camera installation/recovery'],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = run_contracts(args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
