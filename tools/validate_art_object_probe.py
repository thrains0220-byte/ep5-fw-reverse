"""Run stock E-P5 ART object event code with bounded synthetic dependencies."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe


def run_probe():
    image = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 MAIN SHA-256 mismatch')
    with tempfile.TemporaryDirectory(prefix='ep5-art-object-') as directory:
        binary = build_probe(ROOT / 'tools/ep5_art_object_probe.c', Path(directory))
        result = subprocess.run([str(binary), str(image)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'probe failed ({result.returncode}): {result.stderr}')
    return {'result': json.loads(result.stdout), 'main_sha256': MAIN_SHA256,
            'cpu_revision': REVISION, 'physical_camera_test': False,
            'scope': 'stock ART object events 0 and 1, synthetic object and availability; draw and log are modeled returns',
            'not_tested': ['physical button mapping', 'drawing', 'thread scheduling', 'camera integration', 'invalid pointers or list length']}


if __name__ == '__main__':
    print(json.dumps(run_probe(), indent=2))
