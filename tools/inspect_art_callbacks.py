#!/usr/bin/env python3
"""Report the statically recovered E-P5 ART callback call graph.

The report is intentionally conservative.  The edges below were read from the
exact E-P5 1.8 MN103 disassembly and are checked against the input hash.  They
describe direct calls and the object/vtable dispatch used by the ART enter
callbacks; they do not execute code, infer an OSD ABI, or create firmware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.native_probe import MAIN_SHA256

CPU_BASE = 0x7E101020

# The source addresses and targets are taken from the bundled MN103 objdump
# output in build/art-enter-full.txt.  Indirect calls are represented explicitly
# so a later ABI audit cannot accidentally treat them as ordinary functions.
CALLBACKS = {
    "art_enter_state_5": {
        "start": 0x7EAF19B7,
        "end": 0x7EAF1A46,
        "event_id": 0x91,
        "object_global": 0x602C0D1C,
        "direct_calls": [
            {"site": 0x7EAF19BF, "target": 0x7EB1B07D},
            {"site": 0x7EAF19CC, "target": 0x7EB1E5B5},
            {"site": 0x7EAF19D5, "target": 0x7E8901F3},
            {"site": 0x7EAF19F7, "target": 0x7EB1EF19},
            {"site": 0x7EAF1A02, "target": 0x7EB1F0D0},
            {"site": 0x7EAF1A33, "target": 0x7EB2C694},
            {"site": 0x7EAF1A3C, "target": 0x7EB2C69F},
        ],
        "indirect_calls": [
            {"site": 0x7EAF19EF, "kind": "object_vtable_slot_0"},
            {"site": 0x7EAF1A10, "kind": "object_vtable_slot_8"},
        ],
    },
    "art_enter_state_6": {
        "start": 0x7EAF1A46,
        "end": 0x7EAF1AC8,
        "event_id": 0x9D,
        "object_global": 0x602C0D1C,
        "direct_calls": [
            {"site": 0x7EAF1A4E, "target": 0x7EB1B07D},
            {"site": 0x7EAF1A57, "target": 0x7E8901F3},
            {"site": 0x7EAF1A73, "target": 0x7EB1E5B5},
            {"site": 0x7EAF1A79, "target": 0x7EB1EF19},
            {"site": 0x7EAF1A84, "target": 0x7EB1F0D0},
            {"site": 0x7EAF1AB5, "target": 0x7EB2C694},
            {"site": 0x7EAF1ABE, "target": 0x7EB2C69F},
        ],
        "indirect_calls": [
            {"site": 0x7EAF1A6F, "kind": "object_vtable_slot_0"},
            {"site": 0x7EAF1A91, "kind": "object_vtable_slot_8"},
        ],
    },
}


def _within(address: int, data: bytes) -> bool:
    return CPU_BASE <= address < CPU_BASE + len(data)


def inventory(data: bytes) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    if digest != MAIN_SHA256:
        raise ValueError("requires exact decoded E-P5 1.8 MAIN")

    callbacks = {}
    for name, spec in CALLBACKS.items():
        if not (_within(spec["start"], data) and _within(spec["end"] - 1, data)):
            raise ValueError(f"callback range outside image: {name}")
        for edge in spec["direct_calls"]:
            if not _within(edge["site"], data) or not _within(edge["target"], data):
                raise ValueError(f"callback edge outside image: {name}")
        for edge in spec["indirect_calls"]:
            if not _within(edge["site"], data):
                raise ValueError(f"indirect edge outside image: {name}")
        callbacks[name] = {
            "range": [f"0x{spec['start']:08x}", f"0x{spec['end']:08x}"],
            "event_id": f"0x{spec['event_id']:02x}",
            "object_global": f"0x{spec['object_global']:08x}",
            "direct_calls": [
                {"site": f"0x{edge['site']:08x}", "target": f"0x{edge['target']:08x}"}
                for edge in spec["direct_calls"]
            ],
            "indirect_calls": [
                {"site": f"0x{edge['site']:08x}", "kind": edge["kind"]}
                for edge in spec["indirect_calls"]
            ],
        }
    return {
        "main_sha256": digest,
        "scope": "hash-guarded static call edges from MN103 disassembly; no execution or ABI proof",
        "camera_accessed": False,
        "firmware_created": False,
        "callbacks": callbacks,
        "open_questions": [
            "object global type and vtable layout",
            "meaning of event IDs 0x91 and 0x9d",
            "Display/OSD argument ABI and reachable draw path",
            "whether these callbacks run on the GUI task in all ART modes",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = inventory(args.image.read_bytes())
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
