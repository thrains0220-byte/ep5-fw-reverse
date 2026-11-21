"""Drive the on-camera menu controller using indices from the actual 29-look archive."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile
import zlib

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "looks/EP5-Caduceus29-OneCard-FX.zip"


@unittest.skipUnless(shutil.which("cc") and CARD.exists(), "requires cc and a generated 29-look card")
class CameraMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.dir = Path(tmp.name)
        cls.binary = cls.dir / "menu"
        modules = ("lut_camera_menu", "lut_bank", "lut_job", "lut_menu", "lut_menu_index", "look_store",
                   "lut_menu_adapter", "lut_wheel", "lut_wheel_view", "lut_wheel_draw")
        subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-I", ROOT / "firmware",
                        ROOT / "tests/test_lut_camera_menu.c",
                        *(ROOT / "firmware" / f"{m}.c" for m in modules), "-o", cls.binary], check=True)

    def setUp(self):
        with ZipFile(CARD) as archive:
            for bank in ("", "B02/", "B03/"):
                name = f"EP5LUT/{bank}INDEX.EP5"
                path = self.dir / name
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(archive.read(name))

    def run_menu(self, *args):
        return subprocess.check_output([self.binary, *args], cwd=self.dir, text=True)

    def persistence_card(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        card = Path(tmp.name)
        (card / "EP5LUT/B02").mkdir(parents=True)
        index = self.dir / "EP5LUT/INDEX.EP5"
        for folder in ("EP5LUT", "EP5LUT/B02"):
            shutil.copyfile(index, card / folder / "INDEX.EP5")
        return card

    def persist(self, card, operation, bank, value):
        # Every invocation starts a fresh process; only card bytes survive.
        subprocess.run([self.binary, "--persist", operation, str(bank), str(value)], cwd=card, check=True)

    def test_wheel_survives_restart_and_isolates_identical_banks_and_cards(self):
        a, b = self.persistence_card(), self.persistence_card()
        self.persist(a, "write", 1, 0)
        self.persist(a, "read", 1, 1)
        self.persist(a, "write", 2, 0)
        self.persist(a, "write", 2, 1)
        self.persist(a, "read", 1, 1)
        self.persist(a, "read", 2, 2)
        self.persist(b, "read", 1, 0)
        self.persist(b, "read", 2, 0)

    def test_wheel_queued_cancel_eject_wrong_mount_and_atomic_failure(self):
        card = self.persistence_card()
        self.persist(card, "write", 1, 0)
        path, = (card / "EP5LUT").glob("W*.EP5")
        committed = path.read_bytes()
        for action in ("cancel", "eject", "rebound", "commit-eject", "fail"):
            with self.subTest(action=action):
                self.persist(card, action, 1, 1)
                self.assertEqual(path.read_bytes(), committed)
                self.assertEqual(list(path.parent.glob("*.tmp")), [])
                self.persist(card, "read", 1, 1)
        self.persist(card, "retry", 1, 1)
        self.persist(card, "read", 1, 2)

    def test_wheel_rejects_corruption_trailing_data_and_replaced_look(self):
        card = self.persistence_card()
        self.persist(card, "write", 1, 0)
        path, = (card / "EP5LUT").glob("W*.EP5")
        old = path.read_bytes()
        for raw in (old + b"\0", old[:-1], old[:-1] + bytes([old[-1] ^ 1])):
            path.write_bytes(raw)
            self.persist(card, "damaged", 1, 0)
            self.assertEqual(path.read_bytes(), raw)
        other = bytearray(old)
        other[12] ^= 1  # Valid EP5W for an older colour table in the same slot.
        other[52:] = zlib.crc32(other[:52]).to_bytes(4, "little")
        path.write_bytes(other)
        self.persist(card, "clean", 1, 0)
        self.assertEqual(path.read_bytes(), other)

    def test_detached_worker_ignores_stale_and_duplicate_completions(self):
        card = self.persistence_card()
        self.persist(card, "worker-write", 1, 0)
        self.persist(card, "late-read", 1, 1)
        self.persist(card, "worker-eject", 1, 1)
        self.persist(card, "read", 1, 1)

    def test_normalized_dual_dials_edit_only_the_focused_control(self):
        self.run_menu("--dials")

    def test_foreground_release_forwards_controls_and_keeps_last_confirmed_look(self):
        for reason in (1, 2, 3, 4):
            with self.subTest(reason=reason):
                self.run_menu("--release",str(reason))

    def test_shutter_before_and_after_dispatch_never_waits_for_card(self):
        card = self.persistence_card()
        self.persist(card, "write", 1, 0)
        for operation in ("release-queued", "release-fail", "release-write"):
            with self.subTest(operation=operation):
                self.persist(card, operation, 1, 1)
                self.persist(card, "read", 1, 2 if operation == "release-write" else 1)

    def test_every_real_recipe_from_keys(self):
        actual = []
        for line in self.run_menu().splitlines():
            group, number, mode, variant, crc, label = line.split(maxsplit=5)
            actual.append((int(group), int(number), int(mode), int(variant), int(crc,16), label))
        with ZipFile(CARD) as archive:
            catalog = json.loads(archive.read("CATALOG.JSON"))
            expected = []
            for group, bank in enumerate(catalog["banks"],1):
                prefix = "EP5LUT/" + ("" if group == 1 else f"B{group:02d}/")
                for number, look in enumerate(bank["looks"],1):
                    table = archive.read(prefix + f"L{number:07d}.LUT")[24:]
                    expected.append((group,number,look["mode"],look["variant"],zlib.crc32(table),look["label"]))
        self.assertEqual(len(expected),29)
        self.assertCountEqual(actual,expected)

    def test_same_name_number_and_crc_in_different_bank(self):
        shutil.copyfile(self.dir / "EP5LUT/INDEX.EP5", self.dir / "EP5LUT/B02/INDEX.EP5")
        self.run_menu("--duplicate")

    def test_change_group_during_read_and_eject(self):
        self.run_menu("--cancel")

    def test_group_and_list_display_selected_bank_and_real_labels(self):
        def captions(*args):
            return ["".join(chr(int(code,16)) for code in op.split()[4:])
                    for op in self.run_menu(*args).splitlines() if op.startswith("T ")]
        self.assertIn("2/3",captions("--trace-groups"))
        labels=captions("--trace-looks")
        self.assertIn("2/3",labels)
        self.assertIn("主拨盘选风格  副拨盘调强度",labels)
        self.assertIn("Pr400H",labels)
        self.assertIn("100%",labels)
        for state, hint in (
            ("loading", "正在载入色表"), ("ready", "色表已就绪  OK 调色"),
            ("error", "色表不可用  使用原色"), ("off", "胶片效果关闭"),
            ("stale", "OK 选用   再按 OK 调色"),
        ):
            with self.subTest(state=state):
                self.assertIn(hint, captions("--trace-looks", state))


if __name__ == "__main__":
    unittest.main()
