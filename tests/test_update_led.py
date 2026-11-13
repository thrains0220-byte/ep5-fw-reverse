import unittest

from tools import inspect_update_led as led


@unittest.skipUnless(led.DEFAULT.is_file(), "exact E-P5 stock MAIN not available")
class UpdateLedEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = led.DEFAULT.read_bytes()

    def test_real_sd_result_and_wait(self):
        report = led.inspect(self.stock)
        fields = report["flow"]["pwm_period_fields"]
        self.assertEqual(fields[2] * 2, fields[3] * 5)
        self.assertEqual(report["flow"]["duty_fields"], {1: 100, 2: 50, 3: 50})

    def test_inverted_result_and_wait_branches_are_rejected(self):
        for pc in (0x7e206fdd, 0x7e585dc9):
            with self.subTest(pc=hex(pc)):
                changed = bytearray(self.stock)
                changed[pc - led.CPU_BASE] ^= 1  # swap BEQ/BNE
                with self.assertRaises(ValueError):
                    led.audit_flow(changed)

    def test_region_comparison_includes_bytes_between_landmarks(self):
        changed = bytearray(self.stock)
        changed[0x7e585b60 - led.CPU_BASE] ^= 1  # inside a diagnostic print call
        with self.assertRaisesRegex(ValueError, "success, failure, wait"):
            led.compare_regions(self.stock, changed)


if __name__ == "__main__":
    unittest.main()
