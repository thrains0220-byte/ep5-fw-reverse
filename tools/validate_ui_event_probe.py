"""Run the original E-P5 ART event lookup in a bounded CPU model."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256, REVISION, build_probe


def main():
    image = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError("decoded E-P5 MAIN SHA-256 mismatch")
    with tempfile.TemporaryDirectory(prefix="ep5-ui-event-") as directory:
        binary = build_probe(ROOT / "tools/ep5_ui_event_probe.c", Path(directory))
        result = subprocess.run([str(binary), str(image)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"probe failed ({result.returncode}): {result.stderr}")
    report = {"result": json.loads(result.stdout), "main_sha256": MAIN_SHA256,
              "cpu_revision": REVISION, "physical_camera_test": False,
              "scope": "original event lookup plus two dial callback entry selections; synthetic state object",
              "not_tested": ["event generation", "callback execution or return", "state transitions", "drawing", "camera UI"]}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
