#!/usr/bin/env python3
"""Extract static ABI facts for the E-P5 1.8 display API helpers.

The input is the local ``build/display-full.txt`` disassembly generated
from the exact decoded MAIN.  This is an evidence inventory only: it does not
execute code, access a camera, or generate a firmware image.  Function bounds
are derived from the first epilogue after each known API entry and therefore
remain subject to manual review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DISASM_SHA256 = "7041716d26267d94c439374e2553d3228b4600fbcc78b7052f259c29d72c50c5"

TARGETS = {
    "update_screen": {"entry": 0x7E34DEAC, "label": "api_disp_Disp_UpdateScreen"},
    "layer_custom": {"entry": 0x7E34E5EE, "anchor": 0x7E34E5F2,
                      "label": "api_disp_Disp_LayerCustom"},
    "osd_palette": {"entry": 0x7E34EFA9, "anchor": 0x7E34EFAC,
                    "label": "api_disp_Disp_OsdUpdateColorPallet"},
    "image_update": {"entry": 0x7E34F0D0, "anchor": 0x7E34F0D3,
                     "label": "api_disp_Disp_ImgUpdateScreen"},
    "image_update_async": {"entry": 0x7E34F220, "anchor": 0x7E34F223,
                            "label": "api_disp_Disp_ImgUpdateScreen_Async"},
}

LINE_RE = re.compile(r"^([0-9a-f]+):\s+(.+?)\s*$", re.I)
CALL_RE = re.compile(r"\bcall\s+(0x[0-9a-f]+)\s*(?:,\[([^]]*)\],(\d+))?", re.I)


def parse_lines(text: str) -> list[tuple[int, str]]:
    rows = []
    for line in text.splitlines():
        match = LINE_RE.match(line)
        if match:
            rows.append((int(match.group(1), 16), match.group(2)))
    return rows


def _epilogue_index(rows: list[tuple[int, str]], start: int) -> int:
    for index, (address, instruction) in enumerate(rows):
        if address < start:
            continue
        if re.search(r"\bretf?\b", instruction, re.I):
            return index
    raise ValueError(f"no return epilogue after 0x{start:08x}")


def inventory(text: str) -> dict:
    if hashlib.sha256(text.encode()).hexdigest() != DISASM_SHA256:
        raise ValueError("requires the verified E-P5 display disassembly")
    rows = parse_lines(text)
    if not rows:
        raise ValueError("disassembly has no address lines")
    by_address = {address: (index, instruction) for index, (address, instruction) in enumerate(rows)}
    functions = {}
    for name, target in TARGETS.items():
        entry = target["entry"]
        if entry not in by_address:
            raise ValueError(f"missing API entry 0x{entry:08x}")
        start_index = by_address[entry][0]
        end_index = _epilogue_index(rows, entry)
        body = rows[start_index:end_index + 1]
        calls = []
        for address, instruction in body:
            match = CALL_RE.search(instruction)
            if match:
                calls.append({
                    "site": f"0x{address:08x}",
                    "target": match.group(1),
                    "registers": match.group(2).replace(" ", "") if match.group(2) else "",
                    "stack_bytes": int(match.group(3)) if match.group(3) else None,
                })
        entry_instruction = by_address[entry][1]
        epilogue_address, epilogue_instruction = body[-1]
        functions[name] = {
            "candidate_start": f"0x{entry:08x}",
            "anchor": f"0x{target.get('anchor', entry):08x}",
            "label": target["label"],
            "entry_instruction": entry_instruction,
            "end_inclusive": f"0x{epilogue_address:08x}",
            "epilogue": epilogue_instruction,
            "saved_registers": "d2,d3,a2,a3" if "movm\t[d2,d3,a2,a3]" in entry_instruction else "unknown",
            "calls": calls,
            "instruction_count": len(body),
        }
    return {
        "source": "build/display-full.txt",
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "scope": "static disassembly only; no camera access, no firmware output",
        "camera_accessed": False,
        "firmware_created": False,
        "functions": functions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disasm", type=Path, default=ROOT / "build/display-full.txt")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    text = args.disasm.read_text(encoding="utf-8", errors="replace")
    result = inventory(text)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
