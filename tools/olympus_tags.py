"""Read two CameraSettings fields in the Olympus v3 MakerNote used by E-P5 JPEGs.

Field meanings: https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Olympus.pm
(ExifTool's names, not a manufacturer specification). ExifTool calls code 5
"Pin Hole"; "I" distinguishes that original setting from II and III.
"""
import struct


def parse_camera_settings(note: bytes | None) -> dict:
    """Unknown layout: unsupported. Known but damaged layout: ValueError.

    Reads only IFD 0x2020 and fields 0x0520/0x0529. Missing fields are None;
    known fields always preserve every raw value, even when the label is unknown.
    """
    if not isinstance(note, bytes) or not note.startswith(b"OLYMPUS\0"):
        return {"status": "unsupported"}
    if not note.startswith(b"OLYMPUS\0II\x03\x00"):
        return {"status": "unsupported"}  # no cross-model/layout assumptions
    if len(note) > 65535:
        raise ValueError("oversize Olympus JPEG MakerNote")
    occupied = [(0, 12)]

    def claim(pos, size):
        end = pos + size
        if end > len(note) or any(pos < hi and lo < end for lo, hi in occupied):
            raise ValueError("out-of-bounds or overlapping Olympus MakerNote offset")
        occupied.append((pos, end))

    def ifd(pos):
        if pos + 2 > len(note):
            raise ValueError("truncated Olympus IFD")
        entries, = struct.unpack_from("<H", note, pos)
        if entries > 256:
            raise ValueError("too many Olympus IFD entries")
        claim(pos, 2 + 12 * entries + 4)  # includes trailing next-IFD word (not followed)
        tags = {}
        for i in range(entries):
            p = pos + 2 + i * 12
            tag, typ, count = struct.unpack_from("<HHI", note, p)
            if tag in tags:
                raise ValueError(f"duplicate Olympus tag {tag:#06x}")
            tags[tag] = (typ, count, p + 8)
        return tags

    result = {"status": "parsed", "picture_mode": None, "art_filter": None}
    ptr = ifd(12).get(0x2020)
    if ptr is None:
        return result
    typ, count, slot = ptr
    if (typ, count) != (13, 1):
        raise ValueError("invalid Olympus CameraSettings type or count")
    offset, = struct.unpack_from("<I", note, slot)
    camera = ifd(offset)
    for tag, field, counts, labels in (
        (0x0520, "picture_mode", (1, 2), {2: "Natural"}),
        (0x0529, "art_filter", (4,), {0: "Off", 5: "Pin Hole I", 17: "Pin Hole II", 18: "Pin Hole III"}),
    ):
        if tag not in camera:
            continue
        typ, count, slot = camera[tag]
        if typ != 3 or count not in counts:
            raise ValueError(f"invalid Olympus {field} type or count")
        if count * 2 > 4:
            slot, = struct.unpack_from("<I", note, slot)
            claim(slot, count * 2)
        raw = list(struct.unpack_from(f"<{count}H", note, slot))
        result[field] = {"raw": raw, "label": labels.get(raw[0])}
    return result
