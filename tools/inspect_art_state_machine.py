#!/usr/bin/env python3
"""Extract the E-P5 1.8 ART state descriptor and event matrix.

This is a read-only, hash-guarded inventory. It does not infer that a
descriptor is a screen, and it never writes firmware or accesses a camera.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256

BASE = 0x7E101020
DESCRIPTOR_TABLE = 0x7ED882B4
ART_DESCRIPTOR = 0x7EDC0284
ART_MATRIX = 0x7EDBFF6C
ART_CALLBACKS = 0x7EDBFC90
ART_EVENTS = 0x7EDBFA90
ART_ENTER = 0x7EDC022C
ART_EXIT = 0x7EDC0258


def u16(data: bytes, address: int) -> int:
    return struct.unpack_from("<H", data, address - BASE)[0]


def u32(data: bytes, address: int) -> int:
    return struct.unpack_from("<I", data, address - BASE)[0]


def pointer_list(data: bytes, address: int, count: int) -> list[int]:
    return [u32(data, address + 4 * index) for index in range(count)]


def check_address(data: bytes, address: int, length: int = 1) -> None:
    offset = address - BASE
    if offset < 0 or offset + length > len(data):
        raise ValueError(f"address outside MAIN: 0x{address:08x} + {length}")


def extract(data: bytes) -> dict:
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError("requires exact decoded E-P5 1.8 MAIN")
    for address in (DESCRIPTOR_TABLE, ART_DESCRIPTOR, ART_MATRIX, ART_CALLBACKS,
                    ART_EVENTS, ART_ENTER, ART_EXIT):
        check_address(data, address)

    descriptor = {
        "address": f"0x{ART_DESCRIPTOR:08x}",
        "state_columns": u16(data, ART_DESCRIPTOR),
        "event_rows": u16(data, ART_DESCRIPTOR + 2),
        "callback_count": u16(data, ART_DESCRIPTOR + 4),
        "event_count": u16(data, ART_DESCRIPTOR + 6),
        "matrix": f"0x{u32(data, ART_DESCRIPTOR + 8):08x}",
        "callbacks": f"0x{u32(data, ART_DESCRIPTOR + 12):08x}",
        "events": f"0x{u32(data, ART_DESCRIPTOR + 16):08x}",
        "enter": f"0x{u32(data, ART_DESCRIPTOR + 20):08x}",
        "exit": f"0x{u32(data, ART_DESCRIPTOR + 24):08x}",
    }
    if (descriptor["state_columns"], descriptor["event_rows"],
            descriptor["callback_count"], descriptor["event_count"]) != (11, 64, 183, 64):
        raise ValueError(f"unexpected ART descriptor counts: {descriptor}")

    callbacks = pointer_list(data, ART_CALLBACKS, descriptor["callback_count"])
    enters = pointer_list(data, ART_ENTER, descriptor["state_columns"])
    exits = pointer_list(data, ART_EXIT, descriptor["state_columns"])
    events = []
    for index in range(descriptor["event_count"]):
        event = u32(data, ART_EVENTS + 8 * index)
        row = u32(data, ART_EVENTS + 8 * index + 4)
        if row >= descriptor["event_rows"]:
            raise ValueError(f"event row out of range at {index}: {row}")
        events.append({"index": index, "event": f"0x{event:04x}", "row": row})

    matrix = []
    for row in range(descriptor["event_rows"]):
        values = [data[ART_MATRIX - BASE + row * descriptor["state_columns"] + column]
                  for column in range(descriptor["state_columns"])]
        if any(value >= descriptor["callback_count"] for value in values):
            raise ValueError(f"callback index out of range in matrix row {row}")
        matrix.append(values)

    def event_entry(code: int) -> dict:
        for entry in events:
            if int(entry["event"], 16) == code:
                row = entry["row"]
                return {"event": f"0x{code:04x}", "row": row,
                        "callbacks_by_state": matrix[row],
                        "callback_addresses": [f"0x{callbacks[index]:08x}"
                                               for index in matrix[row]]}
        raise ValueError(f"event not found: 0x{code:04x}")

    return {
        "main_sha256": MAIN_SHA256,
        "scope": "static descriptor, event table and callback matrix; no reachability or UI rendering claim",
        "physical_camera_test": False,
        "descriptor_table": {
            "address": f"0x{DESCRIPTOR_TABLE:08x}",
            "count": 18,
            "addresses": [f"0x{x:08x}" for x in pointer_list(data, DESCRIPTOR_TABLE, 18)],
        },
        "art": descriptor,
        "enter_callbacks": [f"0x{x:08x}" for x in enters],
        "exit_callbacks": [f"0x{x:08x}" for x in exits],
        "events": events,
        "matrix": matrix,
        "key_events": {"0x9031": event_entry(0x9031), "0x9032": event_entry(0x9032)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path,
                        default=ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = extract(args.image.read_bytes())
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
