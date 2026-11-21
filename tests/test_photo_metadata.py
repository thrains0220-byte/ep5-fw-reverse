from io import BytesIO
import unittest

from PIL import Image

from ep5studio.photo_metadata import build_photo_exif, read_photo_metadata


CHOSEN = {"label": "柯达金", "bank": 2, "amount_q8": 144, "number": 3,
          "table_crc32": 0xD00DA432, "picture_mode": 105, "variant": 3}


def encode(exif=None):
    image = Image.new("RGB", (48, 32))
    image.putdata([(x * 5, y * 8, (x + y) * 3) for y in range(32) for x in range(48)])
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=96, subsampling=1, exif=exif or b"")
    return buffer.getvalue()


def remove_exif(jpeg):
    """Remove the EXIF APP1 segment while retaining all other JPEG bytes."""
    offset = 2
    while jpeg[offset:offset + 1] == b"\xff":
        marker = jpeg[offset + 1]
        if marker in (0xda, 0xd9):
            break
        length = int.from_bytes(jpeg[offset + 2:offset + 4], "big")
        end = offset + length + 2
        if marker == 0xe1 and jpeg[offset + 4:offset + 10] == b"Exif\0\0":
            return jpeg[:offset] + jpeg[end:]
        offset = end
    raise AssertionError("Missing EXIF APP1")


class PhotoMetadataTest(unittest.TestCase):
    def test_chinese_label_and_identity_round_trip_without_reencoding(self):
        jpeg = encode(build_photo_exif(**CHOSEN))
        self.assertEqual(read_photo_metadata(BytesIO(jpeg)), {"version": 1, **CHOSEN})
        self.assertEqual(encode(), remove_exif(jpeg))
        with Image.open(BytesIO(jpeg)) as image:
            self.assertEqual(image.getexif().get_ifd(0x8769).get(0xA001), 1)

    def test_stock_and_unrelated_unicode_exif_are_ignored(self):
        exif = Image.Exif()
        exif[0x8769] = {0x9286: b"UNICODE\0\xfe\xff" + "另一张照片".encode("utf-16-be")}
        self.assertIsNone(read_photo_metadata(BytesIO(encode())))
        self.assertIsNone(read_photo_metadata(BytesIO(encode(exif.tobytes()))))

    def test_bank_strength_slot_and_label_validation(self):
        for changes in ({"bank": 4}, {"amount_q8": -1}, {"amount_q8": 257},
                        {"amount_q8": True}, {"table_crc32": 2**32}, {"number": 0},
                        {"picture_mode": 100}, {"label": " Gold"}, {"label": "🎞"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_photo_exif(**(CHOSEN | changes))
        for value in (0, 256):
            jpeg = encode(build_photo_exif(**(CHOSEN | {"amount_q8": value})))
            self.assertEqual(read_photo_metadata(BytesIO(jpeg))["amount_q8"], value)


if __name__ == "__main__":
    unittest.main()
