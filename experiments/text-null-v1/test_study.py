import math
import unittest
from study import count_bound, weighted_ebh, lower_bound


class DecisionTests(unittest.TestCase):
    def test_trimming_retains_negative_evidence(self):
        self.assertEqual(count_bound([10, -20], 3), 0)
        self.assertEqual(count_bound([10, 10, -1], 3), 2)

    def test_threshold_equality_does_not_reject(self):
        self.assertEqual(count_bound([3], 3), 0)

    def test_weighted_threshold_uses_selected_token_mass(self):
        self.assertEqual(weighted_ebh([math.log(30), math.log(30)], [1, 99], 0.05), [0, 1])
        self.assertEqual(weighted_ebh([0, 0], [1, 99], 0.05), [])

    def test_null_calibration_changes_the_lower_bound(self):
        self.assertGreater(lower_bound(6000, 100000, 0.05), 0)
        self.assertEqual(lower_bound(6000, 100000, 0.08), 0)


if __name__ == "__main__":
    unittest.main()
