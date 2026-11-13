#!/usr/bin/env python3
"""Read E-P5 stock MAIN, optionally execute its file wrappers in a bounded CPU model."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import CPU_BASE
from tools.native_probe import MAIN_SHA256, build_probe

DEFAULT = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


def inspect(image):
    if hashlib.sha256(image).hexdigest() != MAIN_SHA256:
        raise ValueError("requires exact decoded E-P5 stock 1.8 MAIN")

    def check(pc, prefix):
        if not image.startswith(bytes.fromhex(prefix), pc - CPU_BASE):
            raise ValueError(f"unexpected instruction at {pc:#x}")

    def ptr(pc, prefix):
        check(pc, prefix)
        return struct.unpack_from("<I", image, pc + 2 - CPU_BASE)[0]

    def string(pc, prefix):
        off = ptr(pc, prefix) - CPU_BASE
        return image[off:image.index(0, off, off + 120)].decode("ascii")

    def call(pc, target):
        off = pc - CPU_BASE
        typ = {0xcd: "<h", 0xdd: "<i"}.get(image[off])
        if typ is None or pc + struct.unpack_from(typ, image, off + 1)[0] != target:
            raise ValueError(f"unexpected call target at {pc:#x}")

    # PARAMDT file discovery -> type 2 service -> bounded record array -> installed index.
    directory = string(0x7e27c4c9, "fc cc")
    glob = string(0x7e27c4d2, "fc cc")
    check(0x7e27c4bf, "80 02 f0 72")
    call(0x7e27c4db, 0x7e141955)
    check(0x7e14195f, "a0 02 c8 16")
    call(0x7e141977, 0x7e13fe11)
    storage = ptr(0x7e13fe18, "fc cc")
    check(0x7e13fe1f, "2c")
    capacity = struct.unpack_from("<H", image, 0x7e13fe20 - CPU_BASE)[0]
    check(0x7e13fe22, "f8 13 28")
    call(0x7e13fe8f, 0x7e140c16)
    call(0x7e13ff90, 0x7e13ffa0)
    # N elements x type width + four bytes of header, rounded, must fit remaining.
    call(0x7e13fff1, 0x7e13fc54)
    check(0x7e13fff6, "59 0c f6 14 28 04")
    call(0x7e13fffc, 0x7e13fc63)
    check(0x7e140001, "76 a1 c6 12")
    check(0x7e140015, "f1 01 66")

    # Two independent callers. Do not treat the debug destination as a free buffer.
    operations = {"open": 0x7e291515, "read": 0x7e2915ea, "close": 0x7e291557}
    examples = []
    for name, openpc, readpc, closepc, modepc, countpc in (
            ("face_dbg_load", 0x7e3d2fa8, 0x7e3d2fc7, 0x7e3d2fd4, 0x7e3d2fa2, 0x7e3d2fc0),
            ("olis_ctrl_read_reserve_data", 0x7e41ad1b, 0x7e41ad42, 0x7e41ad4e, 0x7e41ad14, 0x7e41ad3e)):
        call(openpc, operations["open"])
        call(readpc, operations["read"])
        call(closepc, operations["close"])
        if image[countpc - CPU_BASE] == 0x2d:
            count = struct.unpack_from("<H", image, countpc + 1 - CPU_BASE)[0]
        else:
            count = ptr(countpc, "fc cd")
        mode = string(modepc, "fc dd")
        check(countpc - 2, "80 01")
        examples.append({"caller": name, "mode": mode, "requested_bytes": count,
                         "open_site": hex(openpc), "read_site": hex(readpc), "close_site": hex(closepc)})
    examples[0]["path"] = string(0x7e3d2f9c, "fc dc")
    for selector_call in (0x7e291517, 0x7e2915ee, 0x7e291558):
        call(selector_call, 0x7e2914f1)
    service_ids = {key: hex(ptr(pc, "fc cd")) for key, pc in
                   (("open", 0x7e29153c), ("read", 0x7e291614), ("close", 0x7e291575))}
    lut_bytes = 17 ** 3 * 3 * 2
    if (directory, glob, storage, capacity) != ("PARAMDT    ", "CP??????CSV", 0x603c9f28, 8188):
        raise ValueError("unexpected parameter import layout")
    return {"main_sha256": MAIN_SHA256,
            "csv": {"directory": directory, "pattern": glob, "record_store": hex(storage),
                    "available_bytes_including_headers": capacity},
            "rgb16_17_lut_bytes": lut_bytes, "raw_lut_fit_in_param_store": lut_bytes <= capacity,
            "file_operations": {k: hex(a) for k, a in operations.items()},
            "message_ids": service_ids, "native_examples": examples}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main", type=Path, default=DEFAULT)
    p.add_argument("--execute", action="store_true", help="requires native_probe's pinned CPU engine and cc")
    args = p.parse_args()
    report = inspect(args.main.read_bytes())
    if args.execute:
        probe = build_probe(ROOT / "tools/ep5_lut_file_probe.c", ROOT / "build/lut-file-api-probe")
        rows = []
        for direct in (0, 1):
            for index, case in enumerate(("full_read", "open_failed", "short_read_7")):
                r = subprocess.run([str(probe), str(args.main.resolve()), str(direct), str(index)],
                                   check=True, timeout=10, text=True, stdout=subprocess.PIPE)
                rows.append(dict(json.loads(r.stdout), scenario=case))
        report["cpu_file_cases"] = rows
        # Run the real stock selector, not a reimplementation of its dispatch table.
        def select(mode, variant):
            return int(subprocess.check_output([str(probe), str(args.main.resolve()),
                                                str(mode), str(variant), "selector"], timeout=10))
        crosscheck = {mode: [select(mode, v) for v in (1, 2, 3)] for mode in [1, *range(100, 112)]}
        if (crosscheck[105] != [73, 106, 108] or crosscheck[1] != [65535] * 3
                or crosscheck[102][1] != 145 or crosscheck[110][0] != 145):
            raise ValueError("stock slot cross-check failed")
        report["stock_art_filter_codes_for_variant_1_2_3"] = crosscheck
        report["modeled"] = "Backend task selection, direct backend or message responses, logs. No file I/O by emulated E-P5."
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
