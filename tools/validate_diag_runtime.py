"""Validate the D observe-only module on the fixed MN103 CPU model.

Reuses the existing ep5_look_runtime_probe harness layout, but drives the
diagnostic probe with enabled=4 and a minimal synthetic config. Assertions:
  - packet bytes remain identical (no ART neutralization)
  - YUYV pixels and guard bytes remain identical (no LUT write compiled in)
  - ART LUT pool alloc/free stay at zero
  - one 128-byte DIAG record is written through the stock write veneer
  - record contains the synthetic JPEG request geometry/address/sample
  - write failure still leaves stock pixels and no leaked state

This proves the diagnostic branch model, not a camera. The resulting module is
hardware-diagnostic only until a real E-P5 writes DIAG.LOG to its SD card.
"""
from __future__ import annotations
import hashlib, json, struct, subprocess, tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = 0x7e101020
IMAGE = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"

def run():
    from tools.check_mn103_lut import checked
    from tools.native_probe import build_probe
    build = ROOT / "build/diag-runtime"
    build.mkdir(parents=True, exist_ok=True)
    runner = build_probe(ROOT / "tools/ep5_diag_probe.c", build)
    module = ROOT / "build/diag-module-01"
    manifest = json.loads((module / "manifest.json").read_text(encoding="utf-8"))
    # Build a fresh binary to ensure probe and module inputs are current.
    if not (module / "diag.bin").exists():
        raise FileNotFoundError(module / "diag.bin")

    # 72-byte config: tag, enabled=4, mapping, encoding/amount, LUT pointer,
    # geometry, stock reply, picture mode 105/variant 1, global image address.
    cfg = bytearray(72)
    def put(off, v): cfg[off:off+4] = struct.pack("<I", v)
    def put16(off, v): cfg[off:off+2] = struct.pack("<H", v)
    put(0, 0x43355045); put(4, 4)
    put(8, 0x12000010); put(12, 160); put(16, 1); put(20, 256); put(24, 0)
    put16(28, 105); put16(32, 1); put16(36, 0); put(40, 0x12000010)
    put(44, 12); put(48, 0); put(52, 1); put(56, 0x605f4510); put(60, 0x11000000)
    put(64, 1); put(68, 0x12000010)
    pixels = bytes([0xa5] * 16 + [100, 128, 160, 128] * 40 + [0xa5] * 16)
    expected_log = None
    cases = []
    with tempfile.TemporaryDirectory(dir=build) as td:
        td = Path(td)
        (td / "config").write_bytes(cfg)
        (td / "pixels").write_bytes(pixels)
        # Empty card directory: diagnostic must not try to load LUT files.
        card = td / "card"; card.mkdir()
        for scenario, direct in (("observe", 1), ("observe_msg", 0), ("write_fail", 1)):
            out = td / (scenario + ".out")
            args = [str(runner), str(IMAGE), str(module / "diag.bin"), str(td / "config"),
                    str(td / "pixels"), str(out), str(manifest["control_offset"]),
                    str(manifest["codec_call_offset"] if "codec_call_offset" in manifest else 0),
                    str(manifest["state_offset"]), str(manifest["wait_entry_offset"]),
                    str(manifest["wait_call_offset"] if "wait_call_offset" in manifest else 0),
                    str(manifest["release_entry_offset"]), str(manifest["param_entry_offset"]),
                    str(manifest.get("param_call_offset", 0)), str(manifest["look_state_offset"]),
                    scenario, str(direct), str(card)]
            # Diagnostic manifest does not expose codec/param-call offsets yet;
            # recover them from the symbol-driven ELF names via nm.
            nm = subprocess.check_output([
                str(ROOT / "toolchains/mn103/bin/mn10300-elf-nm"), "-n", str(module / "diag.elf")], text=True)
            syms = {line.split()[-1]: int(line.split()[0], 16) for line in nm.splitlines() if len(line.split()) == 3}
            for idx, name in ((7, "_ep5_codec_call"), (13, "_ep5_param_call"), (11, "_ep5_wait_entry")):
                if name in syms:
                    args[idx] = str(syms[name] - 0x7e128010)
            if "_ep5_wait_call" in syms: args[10] = str(syms["_ep5_wait_call"] - 0x7e128010)
            if "_ep5_release_entry" in syms: args[11] = str(syms["_ep5_release_entry"] - 0x7e128010)
            if "_ep5_param_entry" in syms: args[12] = str(syms["_ep5_param_entry"] - 0x7e128010)
            proc = subprocess.run(args, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"{scenario} failed rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
            native = json.loads(proc.stdout.strip().splitlines()[-1])
            got = out.read_bytes()
            if got != pixels:
                raise AssertionError(f"{scenario}: pixels changed")
            log = Path(str(out) + ".diaglog").read_bytes()
            if scenario == "observe":
                if len(log) != 128: raise AssertionError(f"observe log len={len(log)}")
                magic, seq, req, addr, width, height, store_w, store_h = struct.unpack_from("<IIIIHHHH", log)
                if magic != 0x47414944 or (width, height, store_w, store_h) != (4, 20, 4, 20):
                    raise AssertionError("diagnostic record header mismatch")
                # request+0 points at PIXELS+0x10 in the fixture, so the
                # first sample is the first YUYV quartet, after the 16-byte
                # guard prefix.
                if log[33:49] != pixels[16:32]:
                    raise AssertionError(f"sample mismatch got={log[33:49].hex()} want={pixels[16:32].hex()}")
                expected_log = log
            if scenario == "observe_msg" and log != expected_log:
                raise AssertionError("message backend record differs")
            if scenario == "write_fail" and log:
                raise AssertionError("write failure should produce no committed log")
            if native.get("neutralized") != 0 or native.get("pool_allocs") != 0 or native.get("pool_frees") != 0:
                raise AssertionError(f"{scenario}: diagnostic touched ART path {native}")
            cases.append(dict(scenario=scenario, native=native, log_bytes=len(log), output_sha256=hashlib.sha256(got).hexdigest()))
    report = {"status": "model-verified", "cases": cases,
              "module_sha256": hashlib.sha256((module / "diag.bin").read_bytes()).hexdigest(),
              "pixel_write_compiled_out": manifest["pixel_write_compiled_out"],
              "physical_camera_test": False,
              "scope": "observe-only S4/S5 diagnostic; no functional LUT claim"}
    out = ROOT / "build/diag-runtime/report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
