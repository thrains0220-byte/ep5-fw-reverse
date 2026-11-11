"""Build a same-size Olympus E-P5 1.8 update from checked MAIN and language edits."""
import hashlib
from pathlib import Path

from tools.inspect_ep5 import check_stock


# tools/oly_container.py from fishcu/oly_fw_analysis a61498e.
CONTAINER_TOOL = Path(__file__).resolve().parents[1] / "external/oly_fw_analysis/tools/oly_container.py"
CONTAINER_SHA256 = "27a6b3439b7c24eddb3b63bbbe0bd7dcd100fef131a63235e678158c224f9105"


def _check_helper():
    # Git for Windows may check the pinned Python blob out with CRLF;
    # Python's tokenizer already treats that as LF. Preserve all other bytes.
    blob = CONTAINER_TOOL.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(blob).hexdigest() != CONTAINER_SHA256:
        raise ValueError("Olympus container helper SHA-256 mismatch")


def _edited_payload(original, edits):
    payload = bytearray(original)
    previous_end = 0
    for offset, old, new in sorted(edits, key=lambda edit: edit[0]):
        end = offset + len(old)
        if offset < 0 or end > len(payload):
            raise ValueError(f"edit outside payload at {offset:#x}")
        if offset < previous_end:
            raise ValueError(f"overlapping edit at {offset:#x}")
        if not old or len(old) != len(new) or old == new:
            raise ValueError(f"edit must change bytes and preserve size at {offset:#x}")
        if original[offset:end] != old:
            raise ValueError(f"original bytes differ at {offset:#x}")
        payload[offset:end] = new
        previous_end = end
    return payload


def build_update(stock: bytes, edits: list[tuple[int, bytes, bytes]], *, language_edits=()) -> bytes:
    """Apply (decoded offset, expected bytes, replacement bytes) to exact stock."""
    check_stock(stock)
    if not edits:
        raise ValueError("at least one MAIN edit is required")
    _check_helper()
    from external.oly_fw_analysis.tools import oly_container

    blocks = oly_container.parse(stock)
    if [block.kind for block in blocks] != [0x100, 0x101, 0x106, 0x104]:
        raise ValueError("unexpected E-P5 block layout")
    updated = blocks.copy()
    for index, changes in enumerate((edits, language_edits)):
        if changes:
            block = blocks[index]
            payload = _edited_payload(block.payload, changes)
            patched = oly_container.replace_payload(block, payload)
            if (patched.header != block.header or patched.trailer[:28] != block.trailer[:28]
                    or patched.payload != payload):
                raise ValueError("updated block differs from its declared edits")
            updated[index] = patched

    if oly_container.reconstruct(blocks) != stock:
        raise ValueError("stock container round trip failed")
    candidate = oly_container.reconstruct(updated)
    verified = oly_container.parse(candidate)
    if (len(candidate) != len(stock) or verified != updated
            or oly_container.reconstruct(verified) != candidate):
        raise ValueError("candidate differs from the declared edits or failed its container round trip")
    return candidate
