#!/usr/bin/env python3
"""Compare actual MN103 LUT instructions with the host kernel; no camera access."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.compile_lut import warm_negative
from tools.native_probe import build_probe, REVISION

X = ROOT / "toolchains/mn103/bin"


def checked(command):
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stdout[-2000:]}\n{result.stderr[-6000:]}")
    return result.stdout


def validate_target():
    build = ROOT / "build/mn103-lut"
    build.mkdir(parents=True, exist_ok=True)
    compiler = X / "mn10300-elf-gcc"
    if not compiler.exists():
        raise FileNotFoundError("build the local MN103 GCC toolchain first")
    elf, binary = build / "lut.elf", build / "lut.bin"
    flags = ["-std=c99", "-O2", "-mno-am33", "-ffreestanding", "-fno-builtin",
             "-fno-tree-loop-distribute-patterns", "-fno-pic", "-fno-common",
             "-Wall", "-Wextra", "-Werror", "-nostdlib"]
    checked([compiler, *flags, "-I", ROOT / "firmware", ROOT / "tests/fixtures/lut_target.c",
             ROOT / "firmware/lut.c", "-T", ROOT / "tests/fixtures/lut_target.ld", "-lgcc", "-o", elf])
    symbols = checked([X / "mn10300-elf-nm", elf])
    entry = [line.split()[0] for line in symbols.splitlines() if line.split()[-1:] == ["_ep5_probe"]]
    if entry != ["20000000"]:
        raise ValueError("unexpected target fixture entry")
    plain = checked([X / "mn10300-elf-objdump", "-d", "-m", "mn10300", elf]).splitlines()[3:]
    extended = checked([X / "mn10300-elf-objdump", "-d", "-m", "am33-2", elf]).splitlines()[3:]
    if plain != extended:
        raise ValueError("target contains instructions that decode differently as AM33")
    (build / "lut.s").write_text("\n".join(plain) + "\n")
    checked([X / "mn10300-elf-objcopy", "-O", "binary", "-j", ".text", elf, binary])
    runner = build_probe(ROOT / "tools/lut_mn103_probe.c", build)
    shared = build / "host-lut.so"
    checked(["cc", "-std=c99", "-O2", "-shared", "-fPIC", ROOT / "firmware/lut.c", "-o", shared])
    function = ctypes.CDLL(str(shared)).ep5_lut_rgb8
    function.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_uint32,
                         ctypes.c_uint32, ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint16), ctypes.c_size_t]
    function.restype = ctypes.c_int
    identity = struct.pack("<14739H", *(round(c * 65535 / 16)
                           for b in range(17) for g in range(17) for r in range(17) for c in (r, g, b)))
    looks = {"identity": identity, "warm_negative": warm_negative()}
    cases = []
    # Two rows, 128 pixels each, with leading/trailing and per-row canaries.
    original = bytearray([0xa5] * 816)
    for y in range(2):
        for x in range(128):
            at, value = 16 + y * 392 + x * 3, y * 128 + x
            original[at:at + 3] = bytes((value, 255 - value, (value * 73) % 256))
    specifications = [("identity", {}), ("warm_negative", {}), ("capacity", {"capacity": 775}),
                      ("stride", {"stride": 383}), ("width_overflow", {"width": 0xaaaaaaab}),
                      ("extent_overflow", {"height": 0xffffffff, "stride": 0xfffffffc}),
                      ("lut_count", {"values": 1})]
    for name, overrides in specifications:
        settings = dict(capacity=800, width=128, height=2, stride=392, values=14739)
        settings.update(overrides)
        lut = looks.get(name, identity)
        table = (ctypes.c_uint16 * 14739).from_buffer_copy(lut)
        expected = bytearray(original)
        expected_array = (ctypes.c_uint8 * len(expected)).from_buffer(expected)
        pointer = ctypes.cast(ctypes.byref(expected_array, 16), ctypes.POINTER(ctypes.c_uint8))
        expected_result = function(pointer, settings["capacity"], settings["width"], settings["height"],
                                   settings["stride"], table, settings["values"])
        # The native ABI uses 32-bit size_t; pin overflow cases independently of host width.
        if name in ("width_overflow", "extent_overflow"):
            expected_result, expected = -1, original
        request = struct.pack("<8I", 0x12000010, settings["capacity"], settings["width"],
                              settings["height"], settings["stride"], 0x13000000,
                              settings["values"], 0xabababab)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for filename, data in [("lut", lut), ("pixels", original), ("request", request)]:
                (directory / filename).write_bytes(data)
            result = json.loads(checked([runner, binary, directory / "lut", directory / "pixels",
                                         directory / "request", directory / "output"]))
            output = (directory / "output").read_bytes()
        code = result["result_u32"]
        if code >= 0x80000000:
            code -= 0x100000000
        guard_indices = [*range(16), *range(400, 408), *range(792, 816)]
        matched = code == expected_result and output == expected
        guards = all(output[index] == original[index] for index in guard_indices)
        if not matched or not guards:
            raise AssertionError(f"native/host mismatch or guard change: {name}, return {code}, expected {expected_result}")
        cases.append(dict(name=name, result=code, instructions=result["instructions"],
                          matches_host=matched, guard_bytes_preserved=guards,
                          output_sha256=hashlib.sha256(output).hexdigest()))
    paths = [ROOT / "firmware/lut.c", ROOT / "firmware/lut.h", ROOT / "tests/fixtures/lut_target.c",
             ROOT / "tests/fixtures/lut_target.ld", ROOT / "tools/lut_mn103_probe.c",
             ROOT / "tools/check_mn103_lut.py", ROOT / "tools/native_probe.py", elf, binary,
             build / "cpu.c", build / "isa.inc", runner]
    return dict(compiler=checked([compiler, "--version"]).splitlines()[0], flags=flags,
                code_bytes=binary.stat().st_size, lut_bytes=29478, cpu_source_revision=REVISION,
                plain_mn103_instruction_set=True, physical_camera_test=False, cases=cases,
                scope="GCC-generated colour instructions execute on synthetic RGB buffers; no host service computes pixels.",
                not_tested=["vendor compiler ABI", "actual CPU/cache timing", "ISP buffer access", "colour calibration", "camera safety"],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = validate_target()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
