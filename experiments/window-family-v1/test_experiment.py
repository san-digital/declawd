from copy import deepcopy
from fractions import Fraction
import unittest

import experiment
import verify


class WindowFamilyTests(unittest.TestCase):
    def test_binomial_tail_uses_exact_probabilities(self):
        self.assertEqual(experiment.binomial_tail(2, 2, Fraction(1, 4)), Fraction(1, 16))
        self.assertEqual(experiment.binomial_tail(2, 1, Fraction(1, 4)), Fraction(7, 16))
        for width in [2, 4, 8, 12]:
            for marked in range(width + 1):
                self.assertEqual(experiment.binomial_tail(width, marked, Fraction(1, 4)),
                                 verify.polynomial_tails(width)[marked])

    def test_counts_include_each_tested_interval(self):
        cfg = experiment.config()
        expected = {'document': 1, 'sliding': 9, 'dyadic': 18}
        for family in cfg['families']:
            spans = experiment.windows(family, cfg['length'])
            self.assertEqual(len(spans), expected[family['id']])
            self.assertEqual(spans, verify.independent_windows(family['id'], cfg['length']))
            self.assertEqual(len(spans), len(set(spans)))

    def test_final_possible_start_is_included(self):
        family = {'id': 'test', 'widths': [4], 'stride': 2}
        self.assertEqual(experiment.windows(family, 13)[-1], (9, 13))

    def test_sequences_have_bernoulli_weights(self):
        row = experiment.sequence_result([0] * 12, experiment.config())
        self.assertEqual(experiment.fraction(row['probability']), Fraction(3, 4) ** 12)
        bad = deepcopy(row)
        bad['probability'] = experiment.pair(Fraction(1, 4096))
        with self.assertRaisesRegex(ValueError, 'Sequence outcome'):
            verify.check_row(bad, row['sequence'])

    def test_correction_counts_windows_rather_than_widths(self):
        sequence = '111100000000'
        row = experiment.sequence_result(list(map(int, sequence)), experiment.config())
        self.assertTrue(row['families']['dyadic']['uncorrected'])
        self.assertFalse(row['families']['dyadic']['bonferroni'])
        bad = deepcopy(row)
        minimum = experiment.fraction(bad['families']['dyadic']['minimum_pvalue'])
        bad['families']['dyadic']['bonferroni'] = minimum <= Fraction(1, 20 * 3)
        with self.assertRaisesRegex(ValueError, 'Sequence outcome'):
            verify.check_row(bad, sequence)

    def test_multiplying_correction_is_rejected(self):
        sequence = '111100000000'
        row = verify.expected_row(sequence)
        bad = deepcopy(row)
        minimum = verify.as_fraction(bad['families']['dyadic']['minimum_pvalue'])
        bad['families']['dyadic']['bonferroni'] = minimum <= Fraction(18, 20)
        with self.assertRaisesRegex(ValueError, 'Sequence outcome'):
            verify.check_row(bad, sequence)

    def test_changed_sequence_decision_is_rejected(self):
        sequence = '000000000000'
        row = verify.expected_row(sequence)
        row['families']['document']['uncorrected'] = True
        with self.assertRaisesRegex(ValueError, 'Sequence outcome'):
            verify.check_row(row, sequence)

    def test_empty_and_full_marked_edges(self):
        for sequence in ['000000000000', '111111111111', '010101010101']:
            row = experiment.sequence_result(list(map(int, sequence)), experiment.config())
            self.assertEqual(row, verify.expected_row(sequence))


if __name__ == '__main__':
    unittest.main()
