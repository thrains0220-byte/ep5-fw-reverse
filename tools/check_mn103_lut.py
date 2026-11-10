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


def compile_target(build, fixture, sources):
    build.mkdir(parents=True, exist_ok=True)
    compiler = X / "mn10300-elf-gcc"
    if not compiler.exists():
        raise FileNotFoundError("build the local MN103 GCC toolchain first")
    elf, binary = build / "lut.elf", build / "lut.bin"
    flags = ["-std=c99", "-O2", "-mno-am33", "-ffreestanding", "-fno-builtin",
             "-fno-tree-loop-distribute-patterns", "-fno-pic", "-fno-common",
             "-Wall", "-Wextra", "-Werror", "-nostdlib"]
    flags += ["-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections"]
    checked([compiler, *flags, "-I", ROOT / "firmware", fixture,
             *sources, "-T", ROOT / "tests/fixtures/lut_target.ld", "-lgcc", "-o", elf])
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
    return compiler, flags, elf, binary


def validate_target():
    build = ROOT / "build/mn103-lut"
    compiler, flags, elf, binary = compile_target(build, ROOT / "tests/fixtures/lut_target.c",
                                                  [ROOT / "firmware/lut.c"])
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


class Image(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)), ("capacity", ctypes.c_size_t),
                ("width", ctypes.c_uint32), ("height", ctypes.c_uint32), ("stride", ctypes.c_size_t)]


def validate_film_target():
    build = ROOT / "build/mn103-film"
    sources = [ROOT / "firmware/lut.c", ROOT / "firmware/film.c"]
    compiler, flags, elf, binary = compile_target(build, ROOT / "tests/fixtures/film_target.c", sources)
    runner = build_probe(ROOT / "tools/lut_mn103_probe.c", build)
    shared = build / "host-film.so"
    checked(["cc", "-std=c99", "-O2", "-shared", "-fPIC", *sources, "-o", shared])
    host = ctypes.CDLL(str(shared))
    bytep, wordp = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint16)
    callback = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
    host.ep5_film_apply.argtypes = [ctypes.POINTER(Image), wordp, ctypes.c_size_t,
                                   ctypes.c_uint, ctypes.c_uint, callback, ctypes.c_void_p]
    host.ep5_image_from_desc.argtypes = [ctypes.POINTER(Image), bytep, ctypes.c_size_t,
                                        ctypes.c_uint32, bytep, ctypes.c_size_t]
    identity = struct.pack("<14739H", *(round(c * 65535 / 16)
                           for b in range(17) for g in range(17) for r in range(17) for c in (r, g, b)))
    specs = [("identity", {}), ("warm_negative", {}), ("half", {"amount": 128}), ("off", {"amount": 0}),
             ("encoding", {"encoding": 0}), ("amount", {"amount": 257}),
             ("capacity", {"capacity": 311}), ("stride", {"stride": 7}),
             ("odd_width", {"width": 3}), ("lut_count", {"values": 1}),
             ("width_overflow", {"width": 0x80000000}),
             ("extent_overflow", {"height": 0xffffffff, "stride": 0xfffffff0}),
             ("cancel_before", {"cancel": 0}), ("cancel_partial", {"cancel": 16}),
             ("descriptor", {"desc": 1}), ("descriptor_crop", {"desc": 1, "x": 2, "y": 1}),
             ("bad_descriptor", {"desc": 1, "format": 0x107})]
    cases = []
    for name, overrides in specs:
        s = dict(capacity=448, width=4, height=20, stride=16, values=14739,
                 encoding=1, amount=256, cancel=0xffffffff, desc=0, x=0, y=0, format=0x302)
        s.update(overrides)
        lut = identity if name == "identity" else warm_negative()
        table = (ctypes.c_uint16 * 14739).from_buffer_copy(lut)
        original = bytearray((i * 73 + 17) % 256 for i in range(512))
        original[:16] = struct.pack("<4I", s["encoding"], s["amount"], s["cancel"], s["desc"])
        original[16:48] = struct.pack("<II12H", 0x12000040, 0, s["format"], 8, 4, 20,
                                      4, 20, s["x"], s["y"], 2, 10, 0, 0)
        expected = bytearray(original)
        array = (ctypes.c_uint8 * len(expected)).from_buffer(expected)
        pointer = ctypes.cast(ctypes.byref(array, 64), bytep)
        image = Image(pointer, s["capacity"], s["width"], s["height"], s["stride"])
        result = 0
        if s["desc"]:
            result = host.ep5_image_from_desc(ctypes.byref(image), ctypes.cast(ctypes.byref(array, 16), bytep),
                                               32, 0x12000040, pointer, s["capacity"])
        valid_view = result == 0 and s["width"] <= 4 and s["height"] <= 20 and s["stride"] <= 16
        changed_indices = set()
        if valid_view:
            offset = ctypes.cast(image.data, ctypes.c_void_p).value - ctypes.addressof(array)
            changed_indices = {offset + y * image.stride + x for y in range(image.height) for x in range(image.width * 2)}
        cb = callback(lambda ctx, done, total: int(done < s["cancel"]))
        if not result:
            result = host.ep5_film_apply(ctypes.byref(image), table, s["values"], s["encoding"], s["amount"], cb, None)
        if name in ("width_overflow", "extent_overflow"):
            result, expected = -1, bytearray(original)
        request = struct.pack("<8I", 0x12000040, s["capacity"], s["width"], s["height"],
                              s["stride"], 0x13000000, s["values"], 0xabababab)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for filename, data in [("lut", lut), ("pixels", original), ("request", request)]:
                (directory / filename).write_bytes(data)
            native = json.loads(checked([runner, binary, directory / "lut", directory / "pixels",
                                         directory / "request", directory / "output"]))
            output = (directory / "output").read_bytes()
        code = ctypes.c_int32(native["result_u32"]).value
        matched = code == result and output == expected
        guards = all(value == original[i] for i, value in enumerate(output) if i not in changed_indices)
        if name == "identity" and output != original:
            raise AssertionError("native identity changed YCC bytes")
        if not matched or not guards:
            raise AssertionError(f"film native/host mismatch or guard change: {name}, {code} != {result}")
        cases.append(dict(name=name, result=code, instructions=native["instructions"], matches_host=matched,
                          guard_bytes_preserved=guards, output_sha256=hashlib.sha256(output).hexdigest()))
    paths = [*sources, ROOT / "firmware/lut.h", ROOT / "firmware/film.h", ROOT / "tests/fixtures/film_target.c",
             ROOT / "tests/fixtures/lut_target.ld", ROOT / "tools/check_mn103_lut.py", ROOT / "tools/native_probe.py",
             ROOT / "tools/lut_mn103_probe.c", elf, binary, runner, build / "cpu.c", build / "isa.inc"]
    return dict(compiler=checked([compiler, "--version"]).splitlines()[0], flags=flags,
                code_bytes=binary.stat().st_size, lut_bytes=29478, cases=cases, cpu_source_revision=REVISION,
                plain_mn103_instruction_set=True, physical_camera_test=False,
                scope="Production YUYV engine and descriptor normalizer, executed as MN103 instructions with a synthetic GCC caller.",
                not_tested=["camera YCC encoding", "vendor hook", "cache/ownership", "watchdog timing", "code residency", "ORF/JPEG save"],
                dependencies_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--film", action="store_true", help="validate the YUYV engine instead of RGB8")
    args = parser.parse_args()
    report = validate_film_target() if args.film else validate_target()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
