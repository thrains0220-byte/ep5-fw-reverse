import struct
import unittest

from tools.inspect_ep5 import check_stock, string_pointer_refs


class EvidenceTests(unittest.TestCase):
    def test_mov_reference_uses_cpu_base(self):
        data = bytearray(96)
        data[40:51] = b"RAW develop"
        data[0:6] = b"\xfc\xdc" + struct.pack("<I", 0x7E101020 + 40)
        refs = string_pointer_refs(bytes(data), 0x7E101020)
        self.assertEqual(refs, [{"instruction_offset": 0, "string_offset": 40,
                                 "text": "RAW develop"}])
        self.assertEqual(string_pointer_refs(bytes(data), 0x402C0000), [])

    def test_does_not_accept_middle_unterminated_or_non_ascii_string(self):
        for text, target in [(b"prefix RAW\0", 47), (b"RAW" * 100, 40),
                             (b"RAW\xffdata\0", 40)]:
            with self.subTest(text=text[:12]):
                data = bytearray(352)
                data[40:40 + len(text)] = text
                data[0:6] = b"\xfc\xdc" + struct.pack("<I", 0x7E101020 + target)
                self.assertEqual(string_pointer_refs(bytes(data), 0x7E101020), [])

    def test_rejects_truncated_instruction_and_out_of_image_pointer(self):
        self.assertEqual(string_pointer_refs(b"\xfc\xdc\x00\x00", 0), [])
        self.assertEqual(string_pointer_refs(b"\xfc\xdc\xff\xff\xff\xff", 0), [])

    def test_rejects_unknown_firmware(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            check_stock(b"not the E-P5 stock image")


if __name__ == "__main__":
    unittest.main()
