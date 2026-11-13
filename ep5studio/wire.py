"""Bounded SD data protocol; no GUI or numerical package dependency."""
import struct
import zlib
from .project import SLOTS

TABLE_BYTES = 17 ** 3 * 3 * 2
LUT_HEADER = struct.Struct("<8sHHIII")
INDEX_HEADER = struct.Struct("<8sHHII")
SLOT_RECORD = struct.Struct("<HBBHHI16s")

def pack_lut(number, table):
    if type(number) is not int or not 1 <= number <= 16 or len(table) != TABLE_BYTES:
        raise ValueError("风格编号或 17³ 数据长度无效")
    return LUT_HEADER.pack(b"EP5LUT01", 17, 1, number, len(table), zlib.crc32(table)) + table


def unpack_lut(data):
    if len(data) < LUT_HEADER.size:
        raise ValueError("风格数据头被截断")
    magic, side, encoding, number, size, crc = LUT_HEADER.unpack_from(data)
    table = data[LUT_HEADER.size:]
    if (magic != b"EP5LUT01" or side != 17 or encoding != 1 or not 1 <= number <= 16
            or size != TABLE_BYTES or len(table) != size or zlib.crc32(table) != crc):
        raise ValueError("风格数据版本、尺寸或 CRC 校验失败")
    return number, table


def pack_index(project, numbers, checksums):
    rows = []
    for binding in project.bindings:
        slot = SLOTS[binding.slot_id]
        label = binding.label.encode("utf-16-le") + b"\0\0"
        rows.append(SLOT_RECORD.pack(slot["picture_mode"], slot["variant"], 1,
                                     binding.amount_q8, numbers[binding.look_id], checksums[binding.look_id], label))
    body = b"".join(rows)
    return INDEX_HEADER.pack(b"EP5IDX02", 2, len(rows), len(body), zlib.crc32(body)) + body


def unpack_index(data):
    if len(data) < INDEX_HEADER.size:
        raise ValueError("位置索引被截断")
    magic, version, count, size, crc = INDEX_HEADER.unpack_from(data)
    body = data[INDEX_HEADER.size:]
    if (magic != b"EP5IDX02" or version != 2 or not 1 <= count <= 32 or
            size != count * SLOT_RECORD.size or len(body) != size or zlib.crc32(body) != crc):
        raise ValueError("位置索引尺寸或 CRC 校验失败")
    known = {(s["picture_mode"], s["variant"]) for s in SLOTS.values()}
    rows, used = [], set()
    for at in range(0, size, SLOT_RECORD.size):
        mode, variant, flags, amount, number, table_crc, raw = SLOT_RECORD.unpack_from(body, at)
        if (mode, variant) not in known or (mode, variant) in used or flags != 1 or amount > 256 or not 1 <= number <= 16:
            raise ValueError("位置记录、强度或风格引用无效")
        used.add((mode, variant))
        try:
            # The writer only allows six BMP code points, leaving a full terminator.
            label = raw.decode("utf-16-le").rstrip("\0")
        except UnicodeError as err:
            raise ValueError("位置短名编码无效") from err
        from .project import short_label
        if not raw.endswith(b"\0\0") or short_label(label) != label:
            raise ValueError("位置短名无效")
        rows.append(dict(picture_mode=mode, variant=variant, amount_q8=amount, number=number,
                         table_crc32=table_crc, label=label))
    return rows


