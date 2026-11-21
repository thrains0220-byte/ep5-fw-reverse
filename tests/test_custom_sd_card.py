from hashlib import sha256
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from ep5studio.card_zip import edit_card, verify_card
from ep5studio.recipe_fx import fx_sidecars_v2
from ep5studio.wire import unpack_index

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "looks/EP5-Caduceus29-OneCard-FX.zip"
PERSONAL = ROOT / "looks/EP5-Personal-32.zip"
CUBE = b"LUT_3D_SIZE 2\n" + b"\n".join(f"{g} {b} {r}".encode() for b in (0, 1)
                                          for g in (0, 1) for r in (0, 1))
EDIT = (3, None, "Travel", CUBE, "Travel", "off", "Travel.cube")


def archive(files):
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(n, data)
    return payload.getvalue()


class CardEditing(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def test_default_cli_and_repeat_with_a_full_bank(self):
        cube = self.work / "Travel.cube"
        cube.write_bytes(CUBE)
        first = self.work / "first.zip"
        subprocess.run([sys.executable, str(ROOT / "tools/custom_sd_card.py"), str(first),
                        "--add-srgb-cube", f"Travel={cube}"], cwd=self.work, check=True, capture_output=True)
        source, _ = verify_card(BASE.read_bytes())
        files, data = verify_card(first.read_bytes())
        self.assertEqual([len(b["looks"]) for b in data["banks"]], [14, 14, 2])
        changed = {k for k in source if source[k] != files[k]}
        self.assertEqual(changed, {"CATALOG.JSON", "EP5LUT/B03/INDEX.EP5", "EP5LUT/B03/FX.EP5"})
        self.assertEqual(data["card_edits"][-1]["parent_sha256"], sha256(BASE.read_bytes()).hexdigest())
        second = self.work / "second.zip"
        subprocess.run([sys.executable, str(ROOT / "tools/custom_sd_card.py"), str(second), "--card", str(first),
                        "--replace-srgb-cube", "1", "12", f"Warm={cube}"], check=True, capture_output=True)
        revised, catalog = verify_card(second.read_bytes())
        self.assertEqual(catalog["card_edits"][-1]["changes"][0]["replaced"]["name"], "Gold 200")
        self.assertEqual(catalog["card_edits"][-1]["changes"][0]["source_filename"], "Travel.cube")
        rows = unpack_index(files["EP5LUT/INDEX.EP5"])
        replaced = "EP5LUT/L%07d.LUT" % rows[11]["number"]
        self.assertEqual({k for k in files if files[k] != revised[k]},
                         {"CATALOG.JSON", "EP5LUT/INDEX.EP5", "EP5LUT/FX.EP5", replaced})
        for key in ("EP5LUT/INDEX.EP5", "EP5LUT/FX.EP5"):
            width = 28 if "INDEX" in key else 16
            self.assertEqual(files[key][20:20+11*width], revised[key][20:20+11*width])
            self.assertEqual(files[key][20+12*width:], revised[key][20+12*width:])

    def test_v2_clarity_and_existing_personal_entries_survive_append(self):
        old, catalog = verify_card(PERSONAL.read_bytes())
        key = "EP5LUT/B03/FX.EP5"
        old[key] = fx_sidecars_v2(3, catalog["banks"][2], old["EP5LUT/B03/INDEX.EP5"])
        self.assertGreater(old[key][23], 0)  # first row, Atrophy clarity
        card, output = self.work / "v2.zip", self.work / "updated.zip"
        card.write_bytes(archive(old))
        edit_card(card, output, [EDIT])
        new, catalog = verify_card(output.read_bytes())
        self.assertEqual(new[key][:8], b"EP5FXP02")
        self.assertEqual(new[key][20:len(old[key])], old[key][20:])
        self.assertEqual(len(catalog["banks"][2]["looks"]), 5)

    def test_invalid_card_fails_before_output_and_protects_inputs(self):
        files, _ = verify_card(BASE.read_bytes())
        corrupt, output = self.work / "bad.zip", self.work / "out.zip"
        for key in ("EP5LUT/B02/L0000001.LUT", "EP5LUT/FX.EP5", "EP5LUT/B03/INDEX.EP5"):
            corrupt.write_bytes(archive({**files, key: files[key][:-1]}))
            with self.assertRaises(ValueError):
                edit_card(corrupt, output, [EDIT])
            self.assertFalse(output.exists())
        original = PERSONAL.read_bytes()
        corrupt.write_bytes(original)
        with self.assertRaises(ValueError):
            edit_card(corrupt, corrupt, [EDIT])
        self.assertEqual(corrupt.read_bytes(), original)
        for edit in [(1, None, *EDIT[2:]), (3, "watercolor-i", *EDIT[2:]),
                     (3, None, "Acros", *EDIT[3:]), EDIT[:3] + (b"bad",) + EDIT[4:]]:
            with self.assertRaises(ValueError):
                edit_card(corrupt, output, [edit])
            self.assertFalse(output.exists())
