#!/usr/bin/env python3
"""Check the SD updater's LED branches in exact E-P5 1.8 MAIN. Offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import CPU_BASE

DEFAULT = ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin"
STOCK_MAIN = "dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df"
RC2 = "90a63cd0b191f0d0cfdf344b2129723af07f6969d1d6368b8e2216a2019c1229"
RC2_MAIN = "10fac02b381f8253b039cc0fd297d2947544111cdd48deb67f67458b36f34b01"

# Continuous intervals including instructions *between* inspected landmarks;
# ends are exclusive. They are not intended to cover every flash writer.
REGIONS = {
    "SD update task and file search": (0x7e206e4f, 0x7e208401),
    "success, failure, wait, LED dispatcher": (0x7e585b40, 0x7e5860e7),
    "timer driver": (0x7e1556dc, 0x7e155c00),
    "hardware inputs and shutdown sequence": (0x7e14adf1, 0x7e14af2a),
    "update strings": (0x7e432ef0, 0x7e433220),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit_flow(image):
    """Check specific MN103 branch edges, result checks and PWM record values."""
    def require(pc, expected):
        if not image.startswith(bytes.fromhex(expected), pc - CPU_BASE):
            raise ValueError(f"unexpected instruction/data at {pc:#010x}")

    def call(pc, target):
        off = pc - CPU_BASE
        fmt = {0xcd: "<h", 0xdd: "<i"}.get(image[off])
        if not fmt or pc + struct.unpack_from(fmt, image, off + 1)[0] != target:
            raise ValueError(f"expected call at {pc:#010x} to {target:#010x}")

    def literal(pc, op, value):
        require(pc, op)
        address = struct.unpack_from("<I", image, pc - CPU_BASE + 2)[0]
        if not image.startswith(value + b"\x00", address - CPU_BASE):
            raise ValueError(f"unexpected string reference at {pc:#010x}")

    led, success, failure, wait = 0x7e585e90, 0x7e585b40, 0x7e585c99, 0x7e585da2
    call(0x7e206f09, 0x7e2070ba)
    literal(0x7e2070cd, "fc cc", b"DCOLYMP    ")
    literal(0x7e206f22, "fc dc", b"[firmup]...Binary file Hakken !!!!!\n")
    require(0x7e206f54, "58 0c 40 42 0c")  # count accepted files
    require(0x7e206f86, "80 01")
    call(0x7e206f88, led)
    call(0x7e206fa2, 0x7e1312a1)  # submit the request
    call(0x7e206fc3, 0x7e131208)  # wait for the response
    require(0x7e206fca, "a0 00 c8 0c 80 03 81")
    call(0x7e206fd1, failure)
    require(0x7e206fd8, "f8 bc 8c a0 00 c8 0c 80 03 81")
    call(0x7e206fe2, failure)
    require(0x7e206fe9, "4c 22 1c af 0a c6 05 cc 03 ff 58 0c a0 00 c7 27")
    require(0x7e207011, "80 03 85 02")  # D0=3, D1=2
    call(0x7e207015, success)
    for entry, labelpc, label, dispatchpc in (
        (success, 0x7e585b4f, b"Seikou\n", 0x7e585b75),
        (failure, 0x7e585ca8, b"Shippai\n", 0x7e585cc7),
    ):
        require(entry, "86 83")  # D2=D1, D3=D0
        literal(labelpc, "fc de", label)
        require(dispatchpc, "af 03 c9 09 16 88")
        call(dispatchpc + 6, led)
    require(0x7e585b80, "58 04 a0 04 c8 05 cc c5 00")  # case 3 jumps to c4b
    require(0x7e585c4b, "58 04")
    call(0x7e585c4d, wait)
    require(0x7e585d98, "80 04")  # error uses wait case 4
    call(0x7e585d9a, wait)
    require(0x7e585db0, "16 aa 06 c8 18 88")
    call(0x7e585db6, 0x7e586077)
    require(0x7e585dbb, "14 a0 00 c8 0d 88")
    call(0x7e585dc1, 0x7e586077)
    require(0x7e585dc6, "14 a0 00 c9 f7 aa 04 c9 32")
    require(0x7e586077, "14 a0 03 c9 12")
    call(0x7e58607c, 0x7e14aed8)
    require(0x7e14aed8, "fc a4 58 00 e0 98 f8 c4 1f f8 e0 01")
    require(0x7e586083, "f8 e0 01 a0 01 c8 57 ca 58")
    require(0x7e5860df, "00 ca 04 80 01 df 00 04")
    require(0x7e585dff, "aa 03 c9 09 80 05")
    call(0x7e585e05, led)
    call(0x7e585e0a, 0x7e58606b)
    call(0x7e58606b, 0x7e14adf1)
    require(0x7e14ae55, "cb ca ff")
    require(0x7e585e0f, "ca 00")

    # Extract channel 0's parameters from each compare/branch destination.
    params = {}
    for mode, cmp_pc in enumerate(range(led + 1, led + 18, 4), 1):
        require(cmp_pc, f"a0 {mode:02x} c8")
        pc = cmp_pc + 2 + image[cmp_pc + 3 - CPU_BASE]
        require(pc, "00")
        op = image[pc + 1 - CPU_BASE]
        if op == 0x2d:
            params[mode] = struct.unpack_from("<H", image, pc + 2 - CPU_BASE)[0]
        elif op == 0x85:
            params[mode] = image[pc + 2 - CPU_BASE]
        elif op == 0x81:
            params[mode] = 0  # D1=D0 after D0 was cleared
        else:
            raise ValueError(f"unexpected LED parameter at {pc:#010x}")
    if params != {1: 255, 2: 250, 3: 100, 4: 50, 5: 0}:
        raise ValueError(f"unexpected LED mode map: {params}")
    call(0x7e585ebf, 0x7e585ed6)
    require(0x7e585ed8, "fa ca ff 00 c9 31")
    require(0x7e585ef0, "80 01 42 04 2c c1 3e 42 08 80 64 42 0c 00 42 10")
    call(0x7e585f03, 0x7e155743)
    require(0x7e585f0d, "fa ca fa 00 c8 0a aa 64 c8 06 aa 32 c9 57")
    require(0x7e585f31, "2d e8 03 f2 d1 f2 69 1d 2c 46 3d f2 d0 f2 64 81 80 04 f2 d1 f2 61 fb 01 ff 00 46 08 80 32 42 0c")
    call(0x7e585f5f, 0x7e155743)
    call(0x7e585f67, 0x7e155770)
    call(0x7e585f71, 0x7e15579d)
    pwm = {mode: (15686 // (1000 // params[mode]) // 4) * 255 for mode in (2, 3)}
    return {"channel": 0, "mode_parameters": params, "pwm_period_fields": pwm,
            "duty_fields": {1: 100, 2: 50, 3: 50}, "success_poll": "0x98e00058 bit 31",
            "success_loop": "0x7e585dc9 -> 0x7e585dc0"}


def compare_regions(stock, candidate):
    if len(stock) != len(candidate):
        raise ValueError("different MAIN sizes")
    compared = {}
    for name, (lo, hi) in REGIONS.items():
        a, b = lo - CPU_BASE, hi - CPU_BASE
        if b > len(stock) or stock[a:b] != candidate[a:b]:
            raise ValueError(f"different or missing bytes in {name}: [{lo:#x}, {hi:#x})")
        compared[name] = {"start": hex(lo), "end_exclusive": hex(hi), "sha256": sha(stock[a:b])}
    return compared


def inspect(stock, rc2=None):
    if sha(stock) != STOCK_MAIN:
        raise ValueError("requires exact decoded stock E-P5 1.8 MAIN")
    report = {"stock_main_sha256": STOCK_MAIN, "flow": audit_flow(stock)}
    if rc2 is not None:
        if sha(rc2) != RC2:
            raise ValueError("not the exact E-P5 RC2 container")
        from tools.film_update import _check_helper
        _check_helper()
        from external.oly_fw_analysis.tools.oly_container import parse
        main = parse(rc2)[0].payload
        if sha(main) != RC2_MAIN:
            raise ValueError("RC2 MAIN digest mismatch")
        report.update(rc2_sha256=RC2, rc2_main_sha256=RC2_MAIN,
                      identical_regions=compare_regions(stock, main),
                      different_main_bytes=sum(a != b for a, b in zip(stock, main)))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-main", type=Path, default=DEFAULT)
    parser.add_argument("--rc2", type=Path, help="optional actual RC2 E1089999.BIN file")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.stock_main.read_bytes(),
                                 args.rc2.read_bytes() if args.rc2 else None), indent=2))
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
