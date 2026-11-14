#!/usr/bin/env python3
"""Inventory E-P5 1.8 ART/OSD draw-chain leads without executing the camera.

This tool is deliberately evidence-only.  It accepts the exact decoded E-P5
1.8 MAIN image, finds literal references to known GUI/display log strings and
reports the instruction address that references each string.  A string
reference is a useful navigation anchor, but is not proof that a function is
reachable from the ART screen or that an address is a callable API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_ep5 import CPU_BASE, string_pointer_refs
from tools.native_probe import MAIN_SHA256


# These are stable strings in the hash-guarded E-P5 1.8 decoded MAIN.  The
# addresses are navigation anchors only; the surrounding call convention has
# not been recovered yet.
ANCHORS = {
    "gui_loop": (0x7EAB7A7D, "WinMain messageloop start"),
    "art_task": (0x7E1C716C, "ART_MAI"),
    "art_jog": (0x7EAF1FDE, "StArtMenu_EvtStChgJogDial"),
    "art_control_ring": (0x7EAF2FE5, "StArtMenu_EvtStChgCtrlRing"),
    "art_exit": (0x7EAF471B, "StArtMenu_Exit"),
    "draw_disp_update": (0x7E34DEB5, "api_disp_Disp_UpdateScreen"),
    "draw_layer_custom": (0x7E34E5F2, "api_disp_Disp_LayerCustom"),
    "draw_osd_palette": (0x7E34EFAC, "api_disp_Disp_OsdUpdateColorPallet"),
    "draw_image_update": (0x7E34F0D3, "api_disp_Disp_ImgUpdateScreen"),
    "draw_image_update_async": (0x7E34F223, "api_disp_Disp_ImgUpdateScreen_Async"),
    "draw_sync": (0x7EB1B470, "OlyApiCameraCommon::getDispSync"),
    "draw_sync_cancel": (0x7EB1B489, "OlyApiCameraCommon::cancelDispSync"),
    "osd_buffer": (0x7E23CF7C, "Osd256"),
    "art_buffer": (0x7E23C9B9, "BUFF_MEMORY_ART"),
}


def inventory(data: bytes) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    if digest != MAIN_SHA256:
        raise ValueError("requires exact decoded E-P5 1.8 MAIN")

    refs = string_pointer_refs(data, CPU_BASE)
    by_address = {}
    for ref in refs:
        by_address.setdefault(CPU_BASE + ref["instruction_offset"], []).append(ref["text"])

    rows = {}
    for key, (instruction, expected) in ANCHORS.items():
        matches = [r for r in refs if CPU_BASE + r["instruction_offset"] == instruction]
        if not matches:
            raise ValueError(f"missing expected string reference at 0x{instruction:08x}")
        rows[key] = {
            "instruction_address": f"0x{instruction:08x}",
            "expected_fragment": expected,
            "referenced_strings": [r["text"] for r in matches],
            "string_addresses": [f"0x{CPU_BASE + r['string_offset']:08x}" for r in matches],
        }

    return {
        "main_sha256": digest,
        "scope": "static MOV-immediate string references; no camera execution, no firmware output",
        "camera_accessed": False,
        "firmware_created": False,
        "anchors": rows,
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
    result = inventory(args.image.read_bytes())
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
