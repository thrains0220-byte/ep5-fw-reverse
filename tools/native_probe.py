#!/usr/bin/env python3
"""Execute a bounded original E-P5 debug-start branch; no physical device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "external/em10-fw"
REVISION = "6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1"
MAIN_SHA256 = "dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df"


def build_probe(source, build):
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("unexpected CPU emulator revision")
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--exit-code", "HEAD", "--",
                    "emu/cpu.c", "emu/emu.h", "emu/gen.py", "emu/isa"], check=True,
                   stdout=subprocess.DEVNULL)
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(UPSTREAM / "emu/gen.py"), str(build / "isa.inc")],
                   check=True, capture_output=True, text=True, timeout=30)
    # Quoted includes must select this generated decoder, not an ignored upstream build.
    cpu_source = build / "cpu.c"
    cpu_source.write_bytes((UPSTREAM / "emu/cpu.c").read_bytes())
    binary = build / source.stem.replace("_", "-")
    subprocess.run(["cc", "-std=gnu99", "-O1", "-I", str(UPSTREAM / "emu"),
                    "-I", str(build), str(source),
                    str(cpu_source), "-lm", "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=120)
    return binary


def run_probes(image):
    image = Path(image).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError("decoded E-P5 main SHA-256 mismatch")
    build = ROOT / "build/native-probe"
    binary = build_probe(ROOT / "tools/ep5_gate_probe.c", build)
    cpu_source = build / "cpu.c"
    cases = []
    csv_cases = []
    for value in (0, 1):
        result = subprocess.run([str(binary), str(image), str(value)], check=True,
                                capture_output=True, text=True, timeout=10)
        cases.append(json.loads(result.stdout))
        result = subprocess.run([str(binary), str(image), str(value), "csv"], check=True,
                                capture_output=True, text=True, timeout=10)
        csv_cases.append(json.loads(result.stdout))
    dependencies = [ROOT / "tools/ep5_gate_probe.c", ROOT / "tools/native_probe.py",
                    UPSTREAM / "emu/cpu.c", UPSTREAM / "emu/emu.h", UPSTREAM / "emu/gen.py",
                    *sorted((UPSTREAM / "emu/isa").glob("*.igen")),
                    cpu_source, build / "isa.inc", binary]
    return {"main_sha256": MAIN_SHA256, "cpu_source_revision": REVISION,
            "scope": "Original E-P5 startup branch and CSV parse/overlay install/get/clear, including native call/return frames.",
            "models": ["5000-unit delay returns immediately", "direct gate cases model F971; CSV cases execute the real getter",
                       "Wi-Fi initialization is counted, not executed", "only bounded stack and parameter RAM are writable",
                       "CSV fixture has a synthetic zero-valued base parameter; file discovery is separate"],
            "not_tested": ["filesystem discovery/import scheduling", "radio", "sockets", "concurrent boot", "ISP", "firmware recovery"],
            "physical_camera_test": False, "cases": cases, "csv_cases": csv_cases,
            "dependencies_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in dependencies}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run_probes(args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
