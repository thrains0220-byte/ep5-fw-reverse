"""Build a same-size Olympus E-P5 1.8 update from checked decoded MAIN edits."""
import hashlib
from pathlib import Path

from tools.inspect_ep5 import check_stock


# tools/oly_container.py from fishcu/oly_fw_analysis a61498e.
CONTAINER_TOOL = Path(__file__).resolve().parents[1] / "external/oly_fw_analysis/tools/oly_container.py"
CONTAINER_SHA256 = "27a6b3439b7c24eddb3b63bbbe0bd7dcd100fef131a63235e678158c224f9105"


def build_update(stock: bytes, edits: list[tuple[int, bytes, bytes]]) -> bytes:
    """Apply (decoded offset, expected bytes, replacement bytes) to exact stock."""
    check_stock(stock)
    if not edits:
        raise ValueError("at least one MAIN edit is required")
    if hashlib.sha256(CONTAINER_TOOL.read_bytes()).hexdigest() != CONTAINER_SHA256:
        raise ValueError("Olympus container helper SHA-256 mismatch")
    from external.oly_fw_analysis.tools import oly_container

    blocks = oly_container.parse(stock)
    if [block.kind for block in blocks] != [0x100, 0x101, 0x106, 0x104]:
        raise ValueError("unexpected E-P5 block layout")
    main = blocks[0]
    payload = bytearray(main.payload)
    previous_end = 0
    for offset, old, new in sorted(edits, key=lambda edit: edit[0]):
        end = offset + len(old)
        if offset < 0 or end > len(payload):
            raise ValueError(f"MAIN edit outside payload at {offset:#x}")
        if offset < previous_end:
            raise ValueError(f"overlapping MAIN edit at {offset:#x}")
        if not old or len(old) != len(new) or old == new:
            raise ValueError(f"MAIN edit must change bytes and preserve size at {offset:#x}")
        if main.payload[offset:end] != old:
            raise ValueError(f"MAIN original bytes differ at {offset:#x}")
        payload[offset:end] = new
        previous_end = end

    if oly_container.reconstruct(blocks) != stock:
        raise ValueError("stock container round trip failed")
    updated = oly_container.replace_payload(main, payload)
    candidate = oly_container.reconstruct([updated, *blocks[1:]])
    verified = oly_container.parse(candidate)
    if (len(candidate) != len(stock) or verified[1:] != blocks[1:]
            or verified[0].header != main.header or verified[0].trailer[:28] != main.trailer[:28]
            or verified[0].payload != payload or oly_container.reconstruct(verified) != candidate):
        raise ValueError("candidate differs from the declared edits or failed its container round trip")
    return candidate
