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
from tools.check_mn103_lut import X, checked


def run_contracts(image):
    image = Path(image).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 main SHA-256 mismatch')
    build = ROOT / 'build/native-contracts'
    runner = build_probe(ROOT / 'tools/ep5_contract_probe.c', build)
    finish_source = ROOT / 'tests/fixtures/ep5_art_neutral_finish.S'
    finish_object, finish_code = build / 'art-neutral-finish.o', build / 'art-neutral-finish.bin'
    finish_elf = build / 'art-neutral-finish.elf'
    checked([X / 'mn10300-elf-as', '-o', finish_object, finish_source])
    checked([X / 'mn10300-elf-ld', '-e', 'ep5_art_neutral_finish', '-Ttext=0x10000290',
             '-o', finish_elf, finish_object])
    checked([X / 'mn10300-elf-objcopy', '-O', 'binary', '-j', '.text', finish_elf, finish_code])
    cases = {}
    allocations = ('allocate', 'existing', 'failed', 'cropped')
    filters = ('neutral', 'pinhole')
    replies = ('reply-ready', 'reply-pending', 'reply-failed', 'reply-ready-custom-token')
    isp_results = ('isp-matched', 'isp-failed', 'isp-unknown', 'isp-pinhole',
                   'isp-neutral-finish', 'isp-neutral-empty-buffer')
    for name in ('boot', *allocations, *filters, *replies, *isp_results):
        command = [str(runner), str(image), name]
        if name.startswith('isp-neutral-'):
            command.append(str(finish_code))
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(f'{name}: probe exited {result.returncode}\n{result.stderr}')
        cases[name] = json.loads(result.stdout)
    boot = cases.pop('boot')
    start = (boot['destination'] & 0x3fffffff) | 0x40000000
    boot['covers_module'] = start <= 0x7e128010 and start + boot['bytes'] >= 0x7e130000
    paths = [ROOT / 'tools/ep5_contract_probe.c', ROOT / 'tools/native_contracts.py',
             ROOT / 'tools/native_probe.py', ROOT / 'tools/check_mn103_lut.py', finish_source,
             finish_code, build / 'cpu.c', build / 'isa.inc', runner]
    return dict(main_sha256=MAIN_SHA256, cpu_source_revision=REVISION, boot=boot,
                allocation={name: cases[name] for name in allocations},
                filters={name: cases[name] for name in filters},
                art_reply={name: cases[name] for name in replies},
                isp_results={name: cases[name] for name in isp_results},
                physical_camera_test=False,
                models=['logging/trace/error sinks return with native frames',
                        'allocator returns a synthetic address or zero, never creates pixels',
                        'JPEG sink captures the original request and returns 0x1234 without encoding',
                        'boot stops at the flash reader entry; no flash read is modeled',
                        'effect callback returns synthetic statuses; stock task initialization, reply assembly and cleanup execute',
                        'ISP neutral cases execute the stock list builder and initializer, then supply synthetic RAW pass 6 completion state; original lookup, pass 7 and error reply execute',
                        'ISP pinhole case executes the stock list builder and initializer, then starts at the assumed pass 3 completion state with zero scratch pointers; remaining stages are native',
                        'neutral finish cases execute an assembled MN103 test-only second callback which validates the recorded image address and returns the status to the stock worker',
                        'after the matched ISP reply, the stock ART dispatcher selects the active worker; other task groups are idle in the fixture',
                        'the neutral finish cases execute the stock REC send and receive tail on a separate stack; a modeled queue transports the original request and reply bytes',
                        'after a successful finish test reply, the fixture directly invokes the stock JPEG request constructor with the same packet still in memory; task dispatch is not modeled',
                        'completion lookup executes the original slot clear, including the byte-fill routine at 0x7e10652b',
                        'ART reply sink captures arguments without sending a queue message',
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
