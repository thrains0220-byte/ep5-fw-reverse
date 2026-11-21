"""Exercise the portable routing adapter against the same data shipped in the one-card ZIP."""
import ctypes as c
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from test_look_store import Cache, IO, N, OPEN, Reader, Selection

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "looks/EP5-Caduceus29-OneCard-FX.zip"
NATIVE_OPEN = c.CFUNCTYPE(c.c_void_p, c.c_char_p, c.c_char_p)


class Bank(c.Structure):
    _fields_ = [("parent", IO), ("number", c.c_uint8)]


@unittest.skipUnless(shutil.which("cc"), "requires native C compiler")
class LutBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        binary = Path(tmp.name) / "banks.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "firmware"),
                        *(str(ROOT / "firmware" / p) for p in ("lut_bank.c", "look_store.c", "lut_menu.c",
                                                               "lut_menu_index.c", "lut_job.c")),
                        str(ROOT / "tests/test_lut_bank_browser.c"),
                        "-o", str(binary)], check=True)
        cls.lib = c.CDLL(str(binary))
        native = Path(tmp.name) / "native.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                        "-fvisibility=hidden", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                        "-Wl,-z,defs", str(ROOT / "tests/native_look_open.c"), "-o", str(native)], check=True)
        cls.native = c.CDLL(str(native)).native_look_open
        cls.native.argtypes = [c.c_char_p, NATIVE_OPEN]
        cls.native.restype = c.c_void_p
        cls.lib.ep5_lut_bank_path.argtypes = [c.c_char_p, c.c_uint, c.c_char_p]
        cls.lib.ep5_lut_bank_bind.argtypes = [c.POINTER(Bank), c.POINTER(IO), c.POINTER(IO), c.c_uint]
        cls.lib.ep5_look_load.argtypes = [c.POINTER(IO), c.POINTER(Cache), c.c_uint16, c.c_uint8,
                                         c.POINTER(Selection)]
        cls.lib.ep5_look_cache_init.argtypes = [c.POINTER(Cache), c.c_void_p, c.c_size_t,
                                                c.c_void_p, c.c_size_t]

    def test_paths_only_accept_known_files_and_banks(self):
        output = c.create_string_buffer(32)
        for path in (b"EP5LUT/INDEX.EP5", b"EP5LUT/L0000016.LUT", b"EP5LUT/FX.EP5"):
            for number, prefix in ((1, b"EP5LUT/"), (2, b"EP5LUT/B02/"), (3, b"EP5LUT/B03/")):
                self.assertEqual(self.lib.ep5_lut_bank_path(output, number, path), 1)
                self.assertEqual(output.value, prefix + path.split(b"/")[1])
        for path in (b"EP5LUT/../INDEX.EP5", b"EP5LUT/L0000017.LUT", b"EP5LUT/L0000000.LUT",
                     b"EP5LUT/L0", b"EP5LUT/L0000016.LUT/B02", b"EP5LUT/B02/INDEX.EP5", b"C:/EP5LUT/FX.EP5", b""):
            self.assertEqual(self.lib.ep5_lut_bank_path(output, 1, path), 0)
        for number in (0, 4):
            self.assertEqual(self.lib.ep5_lut_bank_path(output, number, b"EP5LUT/INDEX.EP5"), 0)
        self.assertEqual(self.lib.ep5_lut_bank_next(3, 1), 1)
        self.assertEqual(self.lib.ep5_lut_bank_next(1, -1), 3)

    def test_native_open_uses_exact_card_names_only(self):
        opened = []
        backend = NATIVE_OPEN(lambda path, mode: opened.append((path, mode)) or 123)
        for folder in ("", "B02/", "B03/"):
            for leaf in ["INDEX.EP5", "FX.EP5"] + [f"L{n:07}.LUT" for n in range(1, 17)]:
                name = ("EP5LUT/" + folder + leaf).encode()
                self.assertEqual(self.native(name, backend), 123)
                self.assertEqual(opened.pop(), (b"C:\\" + name.replace(b"/", b"\\"), b"rb"))
        for path in (None, b"", b"EP5LUT/", b"EP5LUT/B", b"EP5LUT/B02", b"EP5LUT/B01/FX.EP5",
                     b"EP5LUT/B04/INDEX.EP5", b"EP5LUT/B03/L0000017.LUT", b"EP5LUT/L0000000.LUT",
                     b"EP5LUT/B03/../FX.EP5", b"EP5LUT\\B02\\FX.EP5", b"EP5LUT/B02/B03/FX.EP5",
                     b"C:/EP5LUT/INDEX.EP5", b"EP5LUT/INDEX.EP5" + b"A"*4096):
            self.assertIsNone(self.native(path, backend), path)
        self.assertEqual(opened, [])

    @unittest.skipUnless(RELEASE.is_file(), "generate the actual release with --release-library")
    def test_real_card_switches_across_29_distinct_tables_and_missing_bank(self):
        with ZipFile(RELEASE) as archive:
            files = {n: archive.read(n) for n in archive.namelist() if n.startswith("EP5LUT/")}
            catalog = json.loads(archive.read("CATALOG.JSON"))
        card = Reader(files)
        def from_native(path, mode):
            if mode != b"rb" or not path.startswith(b"C:\\") or b"/" in path:
                return None
            return card.io.open(None, path[3:].replace(b"\\", b"/"))
        backend = NATIVE_OPEN(from_native)
        via_native = IO(None, OPEN(lambda _, path: self.native(path, backend)), card.io.read, card.io.close)
        self.assertEqual(self.lib.bank_browse_real_card(c.byref(via_native)), 1)
        self.assertIsNone(card.live)
        banks = [Bank() for _ in range(3)]
        views = [IO() for _ in banks]
        for i in range(3):
            self.assertTrue(self.lib.ep5_lut_bank_bind(c.byref(banks[i]), c.byref(views[i]), c.byref(via_native), i+1))
        cache, selection = Cache(), Selection()
        a, b = (c.c_uint16*N)(), (c.c_uint16*N)()
        self.assertEqual(self.lib.ep5_look_cache_init(c.byref(cache), a, c.sizeof(a), b, c.sizeof(b)), 0)
        seen = set()
        for i in [2, 0, 1, 2]:
            for entry in catalog["banks"][i]["looks"]:
                self.assertEqual(self.lib.ep5_look_load(c.byref(views[i]), c.byref(cache), entry["mode"],
                                                        entry["variant"], c.byref(selection)), 1)
                self.assertEqual(selection.amount, 256)
                digest = sha256(c.string_at(selection.table, 2*N)).hexdigest()
                self.assertEqual(digest, entry["table_sha256"])
                seen.add(digest)
        self.assertEqual(len(seen), 29)
        del files["EP5LUT/B02/INDEX.EP5"]
        self.assertEqual(self.lib.ep5_look_load(c.byref(views[1]), c.byref(cache), 100, 1, c.byref(selection)), -1)
        self.assertFalse(selection.table)
        self.assertEqual(card.opened[-1], "EP5LUT/B02/INDEX.EP5")
        self.assertIsNone(card.live)


if __name__ == "__main__":
    unittest.main()
