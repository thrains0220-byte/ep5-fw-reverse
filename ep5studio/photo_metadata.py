"""Write and read the chosen E-P5 film look in JPEG EXIF UserComment."""
import json

from PIL import Image

from .project import SLOT_SPECS, short_label


EXIF_IFD = 0x8769
USER_COMMENT = 0x9286
PREFIX = "E-P5 Film Look "
UNICODE_TAG = b"UNICODE\0\xfe\xff"
SLOTS = frozenset((mode, variant) for _, _, mode, variant in SLOT_SPECS)
FIELDS = frozenset(("label", "bank", "amount_q8", "number", "table_crc32",
                    "picture_mode", "variant", "version"))


def _validate(record):
    if not isinstance(record, dict) or record.keys() != FIELDS:
        raise ValueError("Invalid E-P5 film look metadata fields")
    for name, low, high in (("version", 1, 1), ("bank", 1, 3), ("amount_q8", 0, 256),
                            ("number", 1, 16), ("table_crc32", 0, 0xffffffff),
                            ("picture_mode", 0, 0xffff), ("variant", 1, 3)):
        value = record[name]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"Invalid E-P5 film look {name}")
    if ((record["picture_mode"], record["variant"]) not in SLOTS or
            short_label(record["label"]) != record["label"]):
        raise ValueError("Invalid E-P5 film look slot or label")
    return record


def build_photo_exif(*, label, bank, amount_q8, number, table_crc32, picture_mode, variant):
    """Return EXIF bytes to pass to Pillow when encoding the derived JPEG."""
    record = _validate(dict(version=1, label=label, bank=bank, amount_q8=amount_q8,
                            number=number, table_crc32=table_crc32,
                            picture_mode=picture_mode, variant=variant))
    comment = PREFIX + json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    exif = Image.Exif()
    exif[EXIF_IFD] = {0xA001: 1, USER_COMMENT: UNICODE_TAG + comment.encode("utf-16-be")}
    return exif.tobytes()


def read_photo_metadata(source):
    """Read a path or binary stream, returning None for unrelated photos."""
    with Image.open(source) as image:
        value = image.getexif().get_ifd(EXIF_IFD).get(USER_COMMENT)
    if not isinstance(value, bytes) or not value.startswith(UNICODE_TAG):
        return None
    value = value[len(UNICODE_TAG):]
    prefix = PREFIX.encode("utf-16-be")
    if not value.startswith(prefix):
        return None
    if len(value) > 1024:
        raise ValueError("E-P5 film look metadata is too long")
    return _validate(json.loads(value[len(prefix):].decode("utf-16-be")))
