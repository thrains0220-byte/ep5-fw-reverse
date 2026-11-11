import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.native_probe import MAIN_SHA256, build_probe


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
STOCK_WORDS = "b0a5f3943ee92ae601e865e700cf75792a693e4bc549535743e0685c8b6f9604"
FILM_WORDS = "c2ca7ee1b391f3787c5ba34163cb36f3218146f898e837ae299a038d2d3bda05"


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class FilmRouteTests(unittest.TestCase):
    def test_pin_hole_routes_with_stock_and_finished_main(self):
        from external.oly_fw_analysis.tools import oly_container
        from tools.build_native_film import build_film

        original = STOCK.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            probe = build_probe(ROOT / "tools/ep5_film_route_probe.c", directory)
            for name, image in (("stock", original), ("film", build_film(original))):
                main = directory / f"{name}.main"
                payload = oly_container.parse(image)[0].payload
                if name == "stock":
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), MAIN_SHA256)
                main.write_bytes(payload)
                for (variant, mode), (level, stage, submit) in itertools.product(
                    enumerate((73, 106, 108, 65535), start=1),
                    ((200, 0, 0x7e40d54f), (3200, 2, 0x7e40d23a)),
                ):
                    with self.subTest(image=name, variation=variant, level=level):
                        run = subprocess.run([probe, main, str(variant), str(level)],
                                             capture_output=True, text=True, timeout=10)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        case = json.loads(run.stdout)
                        self.assertEqual(case["movie_kind"], 2)
                        self.assertEqual(case["movie_state"], 7)
                        self.assertEqual(case["movie_mode"], mode)
                        self.assertEqual(case["movie_entry"], 0 if variant == 4 else 0x7e40115c)
                        self.assertEqual(case["movie_next"], 0)
                        self.assertEqual(case["packet_mode"], mode)
                        self.assertEqual(case["stage"], stage)
                        self.assertEqual(case["gate"], int(variant == 4))
                        if variant == 4:
                            self.assertEqual(case["submit"], 0)
                            self.assertEqual(case["driver_mode"], -1)
                            self.assertEqual(case["words_hex"], "")
                            continue
                        self.assertEqual(case["converter"], 0x7e40cbb1)
                        self.assertEqual(case["filter"], 0x7e40115c)
                        self.assertEqual(case["submit"], submit)
                        self.assertEqual(case["work_mode"], mode)
                        self.assertEqual(case["job"], 4)
                        self.assertEqual(case["driver_mode"], mode)
                        words = bytes.fromhex(case["words_hex"])
                        self.assertEqual(len(words), 136)
                        expected = FILM_WORDS if (name, variant) == ("film", 1) else STOCK_WORDS
                        self.assertEqual(hashlib.sha256(words).hexdigest(), expected)
