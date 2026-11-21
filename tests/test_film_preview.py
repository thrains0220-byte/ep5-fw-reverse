"""Exercise the actual still-photo and preview colour paths in one process."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc"), "requires a host C compiler")
class FilmPreviewTests(unittest.TestCase):
    def test_photo_parity_source_lifetime_and_shutter_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "preview"
            files = ["film_preview", "film_photo", "film", "film_fx", "lut", "lut_job",
                     "lut_preload", "lut_wheel", "look_store"]
            subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-O2",
                            "-fsanitize=undefined", "-fsanitize-undefined-trap-on-error",
                            "-Ifirmware", "tests/test_film_preview.c",
                            *[f"firmware/{name}.c" for name in files], "-o", str(binary)],
                           check=True, cwd=ROOT)
            subprocess.run([str(binary)], check=True)
