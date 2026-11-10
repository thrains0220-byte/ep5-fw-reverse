#!/usr/bin/env python3
"""Exact-input E-P5 evidence inventory; no camera access or firmware output."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

STOCK_SHA256 = "cc59a4e13b3bf6c46405bd396975cb9c93a7634b7a4a36822259b1fc498b5cfd"
CPU_BASE = 0x7E101020


def check_stock(data):
    if hashlib.sha256(data).hexdigest() != STOCK_SHA256:
        raise ValueError("E-P5 stock SHA-256 mismatch; unknown/modified builds are not accepted")


def string_pointer_refs(data, base):
    refs = []
    for match in re.finditer(rb"\xfc[\xcc-\xcf\xdc-\xdf](....)", data, re.S):
        offset = struct.unpack("<I", match[1])[0] - base
        if not 0 <= offset < len(data) or (offset and data[offset - 1] != 0):
            continue
        end = data.find(b"\0", offset, offset + 240)
        if end < offset + 6:
            continue
        text = data[offset:end]
        if not all(32 <= value <= 126 for value in text):
            continue
        refs.append({"instruction_offset": match.start(), "string_offset": offset,
                     "text": text.decode("ascii")})
    return refs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = args.image.read_bytes()
    check_stock(data)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "external/oly_fw_analysis/tools"))
    import oly_container

    blocks = oly_container.parse(data)
    if oly_container.reconstruct(blocks) != data:
        raise ValueError("container round trip failed")
    main_image = blocks[0].payload
    refs = string_pointer_refs(main_image, CPU_BASE)
    leads = []
    pattern = re.compile(r"raw.*edit|edit.*raw|bayer|rec.*jpeg|rec.*face|stl2ycc|IMGPRO_CTRL", re.I)
    for ref in refs:
        if pattern.search(ref["text"]):
            leads.append({**ref,
                          "instruction_address": hex(CPU_BASE + ref["instruction_offset"]),
                          "string_address": hex(CPU_BASE + ref["string_offset"])})
    report = {
        "stock_sha256": STOCK_SHA256,
        "main_sha256": hashlib.sha256(main_image).hexdigest(),
        "container_roundtrip_identical": True,
        "blocks": [block.metadata() for block in blocks],
        "candidate_cpu_base": hex(CPU_BASE),
        "base_evidence": "Literal MOV-immediate operands pointing at complete ASCII strings; not instruction reachability proof.",
        "mov_string_references": len(refs),
        "unique_referenced_strings": len({ref["string_offset"] for ref in refs}),
        "flash_address_as_cpu_base_references": len(string_pointer_refs(main_image, blocks[0].address)),
        "image_processing_leads": leads,
        "camera_accessed": False,
        "flashable_output_created": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("blocks", "image_processing_leads")}, indent=2))
    print(f"Image-processing leads: {len(leads)}; report: {args.out}")


if __name__ == "__main__":
    main()
