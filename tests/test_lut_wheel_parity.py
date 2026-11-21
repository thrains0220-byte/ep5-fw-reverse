"""Compare every C wheel grid node with the Studio float wheel.

python tests/test_lut_wheel_parity.py /tmp/ep5-wheel-test
python tests/test_lut_wheel_parity.py wsl -e /tmp/ep5-wheel-test
"""
from pathlib import Path
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ep5studio.cube import compile_rgb17
from tools.caduceus_to_ep5 import wheel_cube


def main(binary):
    if not binary:
        raise SystemExit("expected test_lut_wheel executable command")
    rng = np.random.default_rng(20261121)
    cases = [np.zeros((3, 12), dtype="i1")]
    for axis, bound in enumerate((15, 5, 15)):
        for sign in (1, -1):
            edit = np.zeros((3, 12), dtype="i1")
            edit[axis, 3] = sign * bound
            cases.append(edit)
    for _ in range(16):
        cases.append(np.stack([rng.integers(-n, n+1, 12, dtype="i1") for n in (15, 5, 15)]))
    worst = 0
    for i, edit in enumerate(cases):
        recipe = dict(zip(("hue", "sat", "light"), edit.tolist()))
        ideal = compile_rgb17(wheel_cube(recipe))
        packed = subprocess.check_output([*binary, "--rgb16le"], input=edit.tobytes())
        if len(packed) != len(ideal):
            raise ValueError(f"case {i}: expected {len(ideal)} bytes, got {len(packed)}")
        if i == 0 and packed != ideal:
            raise ValueError("neutral C wheel differs from Studio")
        diff = np.abs(np.frombuffer(ideal, "<u2").astype("i4") - np.frombuffer(packed, "<u2"))
        error = int(diff.max())
        if error > 257:
            raise ValueError(f"case {i}: {error}/65535 at word {diff.argmax()}")
        worst = max(worst, error)
    print(f"{len(cases)} recipes x 4913 nodes, neutral bit-exact, max error {worst}/65535")


if __name__ == "__main__":
    main(sys.argv[1:])
