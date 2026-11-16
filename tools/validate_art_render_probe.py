"""Execute stock ART page assembly using synthetic bounded GUI services."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe
from tools.inspect_art_object import extract


def run_probe():
    image = ROOT / 'data/ep5-decoded/00_0100_402c0020.decoded.bin'
    data = image.read_bytes()
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('decoded E-P5 MAIN SHA-256 mismatch')
    gui = extract(data)['gui_service']
    with tempfile.TemporaryDirectory(prefix='ep5-art-render-') as directory:
        binary = build_probe(ROOT / 'tools/ep5_art_render_probe.c', Path(directory))
        result = subprocess.run([str(binary), str(image)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'probe failed ({result.returncode}): {result.stderr}')
    return {'result': json.loads(result.stdout), 'main_sha256': MAIN_SHA256,
            'cpu_revision': REVISION, 'physical_camera_test': False,
            'scope': 'stock ART page assembly, GUI read/update, bounded copy and observer dirty bits in synthetic RAM',
            'gui_service': gui,
            'modeled': ['manager and one observer initialized in synthetic RAM',
                        'three stock payload buffers mapped with guards and synthetic initial contents',
                        'lock/unlock callbacks, final notification, settings and auxiliary service'],
            'not_tested': ['OS lock implementation or contention', 'notification delivery or rendering',
                           'runtime table mutations or nonzero slot callbacks', 'full GUI lifecycle',
                           'text rendering', 'physical controls', 'task lifetime', 'camera screen',
                           'non-default settings'],
            'dependencies_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in (ROOT / 'tools/ep5_art_render_probe.c', Path(__file__),
                                                 ROOT / 'tools/inspect_art_object.py')}}


if __name__ == '__main__':
    print(json.dumps(run_probe(), indent=2))
