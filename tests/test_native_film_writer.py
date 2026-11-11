import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.native_probe import build_probe


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "data/ep5-stock/OLY_E_108_1800_0000_0000.BIN"
IDENTITY_AXIS = [0, 0, 0, 0, 0x800000, 0x804040, 0x808080, 0x80c0c0] + [0xffff] * 9
FILM_AXIS = [0, 0x2800, 0x2800, 0x2800, 0x442800, 0x6c4a40, 0x6c8080, 0x43b6c0] + [0xd7ff] * 9


@unittest.skipUnless(STOCK.is_file(), "requires official E-P5 1.8 update")
class NativeFilmWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from external.oly_fw_analysis.tools import oly_container
        from tools.inspect_ep5 import check_stock

        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.directory = Path(tmp.name)
        cls.runner = build_probe(ROOT / "tools/ep5_contract_probe.c", cls.directory)
        cls.original = STOCK.read_bytes()
        check_stock(cls.original)
        main = cls.directory / "stock.main"
        main.write_bytes(oly_container.parse(cls.original)[0].payload)
        cls.stock_cases = cls.run_writer(main)

    @classmethod
    def run_writer(cls, main):
        result = subprocess.run([cls.runner, main, "chroma"], capture_output=True,
                                text=True, timeout=20)
        if result.returncode:
            raise AssertionError(f"chroma probe exited {result.returncode}: {result.stderr}")
        return json.loads(result.stdout)

    def test_stock_writer_packs_two_identity_axes_for_still_and_movie(self):
        self.assertEqual([case["mode"] for case in self.stock_cases], list(range(256)))
        for mode in (69, 73, 82):
            self.assertEqual(self.stock_cases[mode]["words"], IDENTITY_AXIS * 2)
        for case in self.stock_cases:
            self.assertEqual(case["flags"], 0xa5a5a5a5)
            self.assertEqual(len(case["words"]), 34)

    def test_finished_update_changes_both_axes_for_pinhole_i_alone(self):
        from external.oly_fw_analysis.tools import oly_container
        from tools.build_native_film import build_film

        bin_path = self.directory / "E1089999.BIN"
        bin_path.write_bytes(build_film(self.original))
        main = self.directory / "film.main"
        main.write_bytes(oly_container.parse(bin_path.read_bytes())[0].payload)
        cases = self.run_writer(main)
        self.assertEqual([case["mode"] for case in cases], list(range(256)))
        changed = [i for i in range(256) if self.stock_cases[i]["words"] != cases[i]["words"]]
        self.assertEqual(changed, [73])
        for case in cases:
            self.assertEqual(case["flags"], 0xa5a5a5a5)
        rerouted = [i for i in range(256) if self.stock_cases[i]["pointers"] != cases[i]["pointers"]]
        self.assertEqual(rerouted, [82])
        self.assertEqual(self.stock_cases[82]["pointers"], self.stock_cases[73]["pointers"])
        self.assertEqual(cases[82]["pointers"], self.stock_cases[69]["pointers"])
        self.assertEqual(cases[73]["words"], FILM_AXIS * 2)


if __name__ == "__main__":
    unittest.main()
