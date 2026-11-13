"""Deserialize actual desktop packs with the isolated, freestanding C loader."""
import ctypes as c
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from ep5studio.wire import pack_index, pack_lut
from ep5studio.project import Binding, Project, SLOTS

ROOT = Path(__file__).resolve().parents[1]
N = 17**3 * 3
INDEX = "EP5LUT/INDEX.EP5"
LOOK = "EP5LUT/L0000016.LUT"
LOOK_ID = "a"*64
TABLE = b"".join(struct.pack("<H", (i*1879) & 65535) for i in range(N))
OPEN = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_char_p)
READ = c.CFUNCTYPE(c.c_int32, c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32)
CLOSE = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p)


class IO(c.Structure):
    _fields_ = [("ctx", c.c_void_p), ("open", OPEN), ("read", READ), ("close", CLOSE)]


class Cache(c.Structure):
    _fields_ = [("active", c.c_void_p), ("staging", c.c_void_p)]


class Selection(c.Structure):
    _fields_ = [("table", c.c_void_p), ("amount", c.c_uint16), ("number", c.c_uint16)]


def files(slots=(("pin-hole-ii", 171),), table=TABLE):
    project = Project("test", tuple(Binding(s, LOOK_ID, "试验", q) for s, q in slots))
    return {INDEX: pack_index(project, {LOOK_ID: 16}, {LOOK_ID:zlib.crc32(table)}),
            LOOK: pack_lut(16, table)}


def mutate_row(index, offset, change, row=0):
    data = bytearray(index)
    at = 20+row*28+offset
    data[at:at+len(change)] = change
    struct.pack_into("<I", data, 16, zlib.crc32(data[20:]))
    return data


class Reader:
    def __init__(self, payload, fault=None):
        self.files, self.fault = payload, fault
        self.opened, self.closed = [], []
        self.live = None

        def op(_ctx, path):
            if self.live is not None: raise AssertionError("two handles open")
            path = path.decode("ascii")
            self.opened.append(path)
            if path not in payload: return None
            self.live, self.pos = path, 0
            return 1

        def rd(_ctx, _h, dst, n):
            data = self.files[self.live]
            if self.fault==(self.live, "eof") and self.pos==len(data): return -1
            if self.fault==(self.live, "short") and self.pos>=24 and n>1: n-=1
            chunk = data[self.pos:self.pos+n]
            c.memmove(dst, bytes(chunk), len(chunk))
            self.pos += len(chunk)
            return len(chunk)

        def cl(_ctx, _h):
            path, self.live = self.live, None
            self.closed.append(path)
            return -1 if self.fault==(path, "close") else 0
        self.io = IO(None, OPEN(op), READ(rd), CLOSE(cl))


@unittest.skipUnless(shutil.which("cc"), "requires native cc")
class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        lib = Path(tmp.name)/"store.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC",
                        "-shared", str(ROOT/"firmware/look_store.c"), "-o", str(lib)], check=True)
        cls.lib = c.CDLL(str(lib))
        cls.lib.ep5_look_cache_init.argtypes = [c.POINTER(Cache), c.c_void_p, c.c_size_t,
                                                c.c_void_p, c.c_size_t]
        cls.lib.ep5_look_load.argtypes = [c.POINTER(IO), c.POINTER(Cache), c.c_uint16,
                                          c.c_uint8, c.POINTER(Selection)]

    def setUp(self):
        self.a, self.b = (c.c_uint16*(N+2))(), (c.c_uint16*(N+2))()
        self.a[0]=self.a[-1]=self.b[0]=self.b[-1]=0xa55a
        self.cache, self.selection = Cache(), Selection()
        self.assertEqual(self.init(c.addressof(self.a)+2, 2*N, c.addressof(self.b)+2, 2*N), 0)

    def init(self, a, an, b, bn):
        return self.lib.ep5_look_cache_init(c.byref(self.cache), a, an, b, bn)

    def load(self, card, mode=105, variant=2, fault=None):
        rd = Reader(card, fault)
        result = self.lib.ep5_look_load(c.byref(rd.io), c.byref(self.cache), mode, variant,
                                        c.byref(self.selection))
        self.assertIsNone(rd.live)
        self.assertEqual(rd.closed, [p for p in rd.opened if p in card])
        self.assertEqual([self.a[0], self.a[-1], self.b[0], self.b[-1]], [0xa55a]*4)
        if result!=1:
            self.assertEqual((self.selection.table,self.selection.amount,self.selection.number), (None,0,0))
        return result, rd.opened

    def test_actual_desktop_output_and_all_whitelisted_slots(self):
        card = files([(s, (i+1)*13) for i,s in enumerate(SLOTS)])
        for i,(name,s) in enumerate(SLOTS.items()):
            with self.subTest(name=name):
                prev = self.cache.active
                self.assertEqual(self.load(card, s["picture_mode"], s["variant"]), (1,[INDEX, LOOK]))
                self.assertNotEqual(prev,self.cache.active)
                self.assertEqual((self.selection.amount,self.selection.number), ((i+1)*13,16))
                words = c.cast(self.selection.table, c.POINTER(c.c_uint16))
                self.assertEqual(words[:N], list(struct.unpack("<"+"H"*N, TABLE)))

    def test_stale_same_number_mixed_with_other_pack_falls_back_without_overwriting_active(self):
        card = files(); self.assertEqual(self.load(card)[0],1)
        old = self.cache.active
        other_table = bytes([127])*(2*N)
        other = files(table=other_table)
        card[LOOK] = other[LOOK]  # independently valid header/CRC, same number
        self.assertEqual(self.load(card)[0],-1)
        self.assertEqual(self.cache.active,old)
        self.assertEqual(c.string_at(old,2*N),TABLE)
        self.assertEqual(self.load(other)[0],1)
        self.assertNotEqual(self.cache.active,old)
        self.assertEqual(c.string_at(self.cache.active,2*N),other_table)

    def test_corrupt_files_short_read_trailing_data_and_close_errors_keep_active(self):
        card = files(); self.assertEqual(self.load(card)[0],1)
        old = self.cache.active
        for file in (INDEX, LOOK):
            data = card[file]
            for broken in [data[:-1], data+b"x", data[:8], b"oldmagic"+data[8:],
                           data[:16]+bytes([data[16]^255])+data[17:], data[:-1]+bytes([data[-1]^255])]:
                with self.subTest(file=file, n=len(broken)):
                    self.assertEqual(self.load(dict(card, **{file:broken}))[0],-1)
            for fault in (["short","close","eof"] if file==LOOK else ["close","eof"]):
                with self.subTest(file=file, fault=fault):
                    self.assertEqual(self.load(card, fault=(file,fault))[0],-1)
            self.assertEqual(self.load({k:v for k,v in card.items() if k!=file})[0],-1)
        self.assertEqual(self.cache.active,old)
        self.assertEqual(c.string_at(old,2*N),TABLE)

    def test_invalid_later_record_rejects_even_if_requested_slot_is_first(self):
        card=files([("pin-hole-ii",171), ("pin-hole-iii",256)])
        for offset,bad in ((0,b"\xff\xff"),(2,b"\x02"),(3,b"\x00"),(4,b"\x01\x01"),
                           (6,b"\x11\x00"),(8,b"\xef\xbe\xad\xde"),(12,b"\x00\xd8"),
                           (12,b"\x00\x00"),(12,("abcdefg\0").encode("utf-16le")),
                           (26,b"\x01\x00")):
            with self.subTest(offset=offset,bad=bad):
                broken = mutate_row(card[INDEX], offset, bad, row=1)
                self.assertEqual(self.load(dict(card, **{INDEX:broken})), (-1,[INDEX]))

    def test_declared_header_fields_and_wrong_number_are_rejected(self):
        card=files()
        for name,offset,part in [
            (INDEX,7,b"1"), (INDEX,8,b"\x01\x00"), (INDEX,10,b"\x00\x00"),
            (INDEX,10,b"\x21\x00"), (INDEX,12,b"\xff\xff\xff\xff"),
            (LOOK,8,b"\x21\x00"), (LOOK,10,b"\x02\x00"),
            (LOOK,12,b"\x01\x00\x00\x00"), (LOOK,16,b"\xff\xff\xff\xff"),
            (LOOK,20,b"\xff\xff\xff\xff")]:
            with self.subTest(name=name,offset=offset):
                changed=bytearray(card[name]); changed[offset:offset+len(part)]=part
                self.assertEqual(self.load(dict(card, **{name:changed}))[0],-1)

    def test_zero_strength_and_nonassigned_slot_do_not_open_lut_or_return_old_selection(self):
        self.assertEqual(self.load(files())[0],1)
        old=self.cache.active
        self.assertEqual(self.load(files([("pin-hole-ii",0)])), (0,[INDEX]))
        self.assertEqual(self.load(files([("pin-hole-i",256)])), (0,[INDEX]))
        self.assertEqual(self.load(files(), 1, 1), (0,[]))
        self.assertEqual(self.cache.active,old)

    def test_cache_requires_two_disjoint_aligned_tables(self):
        a,b=c.addressof(self.a)+2,c.addressof(self.b)+2
        for args in [(a,2*N-2,b,2*N),(a,2*N,b,2*N-2),(a,2*N,a+2,2*N),
                     (a+1,2*N,b,2*N),(None,2*N,b,2*N)]:
            self.assertEqual(self.init(*args),-1)
            self.assertEqual((self.cache.active,self.cache.staging),(None,None))


if __name__ == "__main__":
    unittest.main()
