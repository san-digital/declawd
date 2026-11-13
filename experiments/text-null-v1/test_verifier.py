import unittest
from verify import compare


class VerificationTests(unittest.TestCase):
    def test_library_rounding_is_bounded(self):
        compare({"value": 0.1234567890123456}, {"value": 0.1234567890123457})
        with self.assertRaisesRegex(ValueError, "numerical"):
            compare(0.1, 0.1000001)

    def test_discrete_outcomes_remain_exact(self):
        with self.assertRaisesRegex(ValueError, "discrete"):
            compare({"count": 26}, {"count": 27})
        with self.assertRaisesRegex(ValueError, "type"):
            compare(True, 1)

    def test_missing_results_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "length"):
            compare([0], [0, 1])
        with self.assertRaisesRegex(ValueError, "keys"):
            compare({}, {"outcome": 0})


if __name__ == "__main__":
    unittest.main()
