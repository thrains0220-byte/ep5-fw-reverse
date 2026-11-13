#!/usr/bin/env python3
"""Report E-P5 1.8 PTP code and tables from its decoded MAIN; no device access."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from inspect_ep5 import CPU_BASE


MAIN_SHA256 = "dfe255e4d5a43329712c1fdfd6861ee1f3ef54a268b6096628bf045d8cc590df"
DEFAULT = Path(__file__).resolve().parents[1] / "data/ep5-decoded/00_0100_402c0020.decoded.bin"


def inspect(image):
    if hashlib.sha256(image).hexdigest() != MAIN_SHA256:
        raise ValueError("requires the exact decoded stock E-P5 1.8 MAIN, not a full update")

    def u16(pc):
        return struct.unpack_from("<H", image, pc - CPU_BASE)[0]

    def u32(pc):
        return struct.unpack_from("<I", image, pc - CPU_BASE)[0]

    def byte(pc):
        return image[pc - CPU_BASE]

    def require(pc, expected):
        if not image.startswith(bytes.fromhex(expected), pc - CPU_BASE):
            raise ValueError(f"unexpected instruction at {pc:#x}")

    # Branches in the native list selector load a count into D0 and a pointer
    # into D1. Read both directly rather than assuming consecutive table ends.
    def table(pc):
        require(pc, "80")
        require(pc + 2, "fc cd")
        count, ptr = byte(pc + 1), u32(pc + 4)
        return ptr, [f"{u16(ptr + i * 2):04x}" for i in range(count)]

    profiles = {}
    for numbers, pc in [((0, 5), 0x7ee8d56e), ((1,), 0x7ee8d578),
                         ((2, 3), 0x7ee8d582), ((4,), 0x7ee8d58c), ((6,), 0x7ee8d596)]:
        ptr, ops = table(pc)
        for n in numbers:
            profiles[n] = {"table": hex(ptr), "operations": ops}

    # Each registration in this specific profile loads D0=operation, D1=phase,
    # A1=gate, A0=callback, then CALLs the registry. Decode the complete block.
    registered = {}
    pc = 0x7ee81d82
    while pc != 0x7ee81ef1:
        start = pc
        if byte(pc) == 0x2c:
            opcode = u16(pc + 1)
            pc += 3
        else:
            require(pc, "fc cc")
            opcode = u32(pc + 2)
            pc += 6
        if byte(pc) == 0x04:
            pc += 1
        else:
            require(pc, "85")
            pc += 2
        require(pc, "95")
        pc += 2
        require(pc, "fc dc")
        callback = u32(pc + 2)
        pc += 6
        require(pc, "cd")
        delta = struct.unpack_from("<h", image, pc + 1 - CPU_BASE)[0]
        if pc + delta != 0x7ee86db6:
            raise ValueError(f"not a registration call at {pc:#x}")
        require(pc + 3, "f0 14")
        key = f"{opcode:04x}"
        if key in registered:
            raise ValueError(f"duplicate registration: {key}")
        registered[key] = {"site": hex(start), "handler": hex(callback)}
        pc += 5
    require(pc, "df 00 04")
    if set(registered) != set(profiles[4]["operations"]):
        raise ValueError("profile 4 registration and advertised list disagree")
    literals = {}
    for field, pc in (("Manufacturer", 0x7ee8ba77), ("DeviceVersion", 0x7ee8ba8f)):
        require(pc, "fc dd")  # mov imm32,A1
        require(pc + 6, "cd")
        if pc + 6 + struct.unpack_from("<h", image, pc + 7 - CPU_BASE)[0] != 0x7ee8dfba:
            raise ValueError(f"unexpected GetDeviceInfo string encoder at {pc:#x}")
        start = u32(pc + 2) - CPU_BASE
        literals[field] = image[start:image.index(b"\0", start, start + 32)].decode("ascii")
    # Profile 1 stores D2=1 directly, profile 4 stores D0=4 at their common
    # mode global. Both load the same D1 payload for the VID/PID serializer.
    require(0x7ee819f0, "8a 01")
    require(0x7ee81a18, "fc 8b 96 77 80 a0")
    require(0x7ee81a2a, "80 04 ca 10")
    require(0x7ee81a3c, "fc 83 96 77 80 a0")
    pids = {}
    for profile, pc in ((1, 0x7ee81a15), (4, 0x7ee81a27)):
        require(pc, "2d")
        pids[profile] = f"{u16(pc+1):04x}"
    return {"source_sha256": MAIN_SHA256, "source": "decoded official image only",
            "physical_camera_test": False, "advertised_profiles": profiles,
            "get_device_info_rom_literals": literals,
            "usb_pid_profiles_1_and_4": pids,
            "profile_4_registered": registered, "profile_4_events": table(0x7ee8d5e3)[1],
            "profile_4_device_properties": table(0x7ee8d630)[1],
            "raw_vendor_or_memory_reads_tested": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main", type=Path, nargs="?", default=DEFAULT)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.main.read_bytes()), indent=2))
    except (ValueError, OSError) as err:
        parser.exit(1, f"{err}\n")
