#!/usr/bin/env python3
"""Read-only, hash-guarded inventory of E-P5 1.8 ART UI static leads.

Pointers and adjacent words are candidates, not a recovered menu schema or
evidence of execution. No firmware or camera storage is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import CPU_BASE, string_pointer_refs
from tools.native_probe import MAIN_SHA256

LEADS = {
    "jog": (0x7EAF1FA3, 0x7EAF1FDE, "StArtMenu_EvtStChgJogDial"),
    "control_ring": (0x7EAF2FB3, 0x7EAF2FE5, "StArtMenu_EvtStChgCtrlRing"),
    "exit": (0x7EAF46E8, 0x7EAF471B, "StArtMenu_Exit"),
}


def references(data, address):
    needle = struct.pack("<I", address)
    found, start = [], 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return found
        found.append(CPU_BASE + i)
        start = i + 1


def inventory(data):
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError("requires exact decoded E-P5 1.8 MAIN")
    strings = {CPU_BASE + ref["instruction_offset"]: ref["text"]
               for ref in string_pointer_refs(data, CPU_BASE)}
    results = {}
    for name, (entry, log_ref, needle) in LEADS.items():
        text = strings.get(log_ref, "")
        if needle not in text:
            raise ValueError(f"missing expected {name} log reference")
        refs = references(data, entry)
        results[name] = {
            "candidate_entry": f"0x{entry:08x}",
            "log_instruction": f"0x{log_ref:08x}",
            "log_text": text,
            "entry_u32_references": [f"0x{x:08x}" for x in refs],
            "adjacent_words": {
                f"0x{site:08x}": [
                    f"0x{struct.unpack_from('<I', data, site - CPU_BASE + j)[0]:08x}"
                    for j in range(-16, 20, 4)
                ] for site in refs if 16 <= site - CPU_BASE <= len(data) - 20
            },
        }
    return {
        "main_sha256": MAIN_SHA256,
        "scope": "static byte matches only; entry boundaries, table type, reachability and safety unproven",
        "adjacent_words_order": "-16 through +16 bytes relative to reference",
        "camera_accessed": False,
        "firmware_created": False,
        "leads": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "data/ep5-decoded/00_0100_402c0020.decoded.bin")
    args = parser.parse_args()
    print(json.dumps(inventory(args.image.read_bytes()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
