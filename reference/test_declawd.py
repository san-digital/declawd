from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import declawd

PROFILE = Path(__file__).resolve().parents[1] / "fixtures" / "profile-v1.json"


def setUpModule() -> None:
    """The engine refuses to score without a profile, so load the shipped one."""
    declawd.load_profile(PROFILE)


VIETNAMESE = "Tiếng Việt có dấu thanh điệu"
CZECH = "Příliš žluťoučký kůň úpěl ďábelské ódy"
PERSIAN = "می‌خواهم"
EMOJI_ZWJ = "👨‍👩‍👧"


class ScannerTests(unittest.TestCase):
    def test_zero_width_insertion_splits_a_token(self) -> None:
        self.assertEqual(declawd.scan("ab​cd"), ["ab", "cd"])

    def test_zero_width_is_not_deleted_before_matching(self) -> None:
        # The whole perturbation demo depends on this. If the scanner stripped
        # the character first, the token would survive intact and nothing would
        # happen to the score.
        self.assertEqual(declawd.scan("water​mark"), ["water", "mark"])
        self.assertEqual(declawd.scan("watermark"), ["watermark"])

    def test_hyphen_delimits(self) -> None:
        self.assertEqual(declawd.scan("co-operate"), ["co", "operate"])

    def test_straight_apostrophe_is_part_of_the_token(self) -> None:
        self.assertEqual(declawd.scan("can't"), ["can't"])

    def test_curly_apostrophe_delimits(self) -> None:
        self.assertEqual(declawd.scan("can’t"), ["can", "t"])

    def test_non_ascii_letters_delimit(self) -> None:
        self.assertEqual(declawd.scan("naïve"), ["na", "ve"])

    def test_supplementary_plane_character_delimits(self) -> None:
        self.assertEqual(declawd.scan("a\U0001F600b"), ["a", "b"])

    def test_passage_text_is_never_modified_by_scanning(self) -> None:
        passage = "water​mark, naïve\r\nco-operate\t"
        declawd.scan(passage)
        self.assertEqual(passage, "water​mark, naïve\r\nco-operate\t")


class FoldTests(unittest.TestCase):
    def test_ascii_upper_is_folded(self) -> None:
        self.assertEqual(declawd.fold("WaterMark"), "watermark")

    def test_apostrophe_survives_folding(self) -> None:
        self.assertEqual(declawd.fold("CAN'T"), "can't")


class PredicateTests(unittest.TestCase):
    def test_predicate_is_deterministic(self) -> None:
        first = [declawd.is_green("the", "quick") for _ in range(5)]
        self.assertEqual(len(set(first)), 1)

    def test_predicate_distinguishes_context(self) -> None:
        # The same token under different predecessors must be classified
        # independently, or the scheme degenerates to a unigram list. Four
        # predecessors is not enough to assert this: at gamma = 1/4 they are all
        # red about a third of the time, which made this fail on some seeds.
        predecessors = [f"w{n}" for n in range(60)]
        results = {declawd.is_green(prev, "work") for prev in predecessors}
        self.assertEqual(results, {True, False})

    def test_green_rate_is_close_to_gamma(self) -> None:
        # The property that actually matters, and it does not depend on the seed.
        pairs = [(f"a{i}", f"b{j}") for i in range(40) for j in range(40)]
        green = sum(declawd.is_green(a, b) for a, b in pairs)
        gamma = declawd.GAMMA_NUM / declawd.GAMMA_DEN
        self.assertAlmostEqual(green / len(pairs), gamma, delta=0.04)

    def test_length_prefixing_prevents_concatenation_collisions(self) -> None:
        # ("ab", "c") and ("a", "bc") concatenate to the same bytes, so without
        # length prefixes they would score identically. Comparing one pair is
        # not a test: they agree half the time by chance. Compare many.
        split_one = [declawd.is_green(f"ab{n}", "c") for n in range(60)]
        split_two = [declawd.is_green(f"a", f"b{n}c") for n in range(60)]
        self.assertNotEqual(split_one, split_two)

    def test_determinism_across_hash_seeds(self) -> None:
        # Python's built-in hash() is process-randomised; hashlib is not. This
        # catches any accidental reliance on the former.
        script = (
            "import sys; sys.path.insert(0, %r); import declawd; "
            "declawd.load_profile(%r); "
            "print(declawd.score('The quick brown fox jumps over the lazy dog').green)"
            % (str(Path(__file__).resolve().parent), str(PROFILE))
        )
        outputs = set()
        for seed in ("0", "1", "12345"):
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
                check=True,
            )
            outputs.add(result.stdout.strip())
        self.assertEqual(len(outputs), 1)


class RepeatedContextTests(unittest.TestCase):
    def test_repeated_contexts_are_counted_once(self) -> None:
        repetitive = "spam spam spam spam spam spam spam spam"
        result = declawd.score(repetitive)
        self.assertEqual(result.raw_tokens, 8)
        # Contexts are ("", spam) then (spam, spam) repeated.
        self.assertEqual(result.effective_tokens, 2)

    def test_repetition_cannot_inflate_the_green_count(self) -> None:
        short = declawd.score("spam spam")
        long = declawd.score("spam " * 200)
        self.assertEqual(short.green, long.green)
        self.assertEqual(short.effective_tokens, long.effective_tokens)


class VerdictTests(unittest.TestCase):
    def test_zero_tokens_is_insufficient_and_has_no_score(self) -> None:
        result = declawd.score("")
        self.assertEqual(result.effective_tokens, 0)
        self.assertEqual(result.verdict, declawd.VERDICT_INSUFFICIENT)
        self.assertIsNone(result.z_display)

    def test_one_token_below_the_minimum_is_insufficient(self) -> None:
        with patch.object(declawd, "MIN_EFFECTIVE_TOKENS", 400):
            self.assertEqual(declawd.verdict(399, 399), declawd.VERDICT_INSUFFICIENT)

    def test_exactly_at_the_minimum_is_adjudicated(self) -> None:
        with patch.object(declawd, "MIN_EFFECTIVE_TOKENS", 400):
            self.assertNotEqual(declawd.verdict(400, 400), declawd.VERDICT_INSUFFICIENT)

    def test_verdict_boundary_is_strict(self) -> None:
        # gamma = 1/4, threshold = 4: with T = 400, n = 4G - 400 and the test is
        # n^2 > 48T = 19200, so G = 135 crosses and G = 134 does not. The
        # threshold is patched so the arithmetic does not move with the profile.
        with patch.object(declawd, "MIN_EFFECTIVE_TOKENS", 400), \
             patch.object(declawd, "THRESHOLD_NUM", 4), \
             patch.object(declawd, "THRESHOLD_DEN", 1):
            self.assertEqual(declawd.verdict(400, 134), declawd.VERDICT_NOT_DETECTED)
            self.assertEqual(declawd.verdict(400, 135), declawd.VERDICT_DETECTED)

    def test_a_green_deficit_is_never_detected(self) -> None:
        with patch.object(declawd, "MIN_EFFECTIVE_TOKENS", 400):
            self.assertEqual(declawd.verdict(400, 0), declawd.VERDICT_NOT_DETECTED)

    def test_score_display_is_never_nan_or_infinite(self) -> None:
        for text in ("", "a", "the quick brown fox"):
            display = declawd.score(text).z_display
            if display is not None:
                self.assertEqual(display, display)  # NaN fails self-equality
                self.assertNotIn(display, (float("inf"), float("-inf")))


class CanonicaliserTests(unittest.TestCase):
    def test_zero_width_insertion_restores_exactly(self) -> None:
        original = "The watermark survives"
        perturbed = original.replace("watermark", "water​mark")
        self.assertNotEqual(perturbed, original)
        self.assertEqual(declawd.canonicalise(perturbed), original)

    def test_confusable_substitution_restores_exactly(self) -> None:
        original = "a plain passage"
        perturbed = original.replace("a plain", "а plаin")
        self.assertNotEqual(perturbed, original)
        self.assertEqual(declawd.canonicalise(perturbed), original)

    def test_restoration_is_byte_for_byte(self) -> None:
        original = "The watermark survives"
        perturbed = original.replace("watermark", "water​mark")
        self.assertEqual(
            declawd.canonicalise(perturbed).encode("utf-8"),
            original.encode("utf-8"),
        )

    def test_deletion_is_not_recovered(self) -> None:
        original = "The watermark survives"
        perturbed = "The watermrk survives"
        self.assertNotEqual(declawd.canonicalise(perturbed), original)

    def test_canonicalisation_is_idempotent(self) -> None:
        perturbed = "water​mаrk"
        once = declawd.canonicalise(perturbed)
        self.assertEqual(declawd.canonicalise(once), once)

    def test_legitimate_scripts_are_untouched(self) -> None:
        for passage in (VIETNAMESE, CZECH, PERSIAN, EMOJI_ZWJ):
            self.assertEqual(declawd.canonicalise(passage), passage)

    def test_newlines_and_tabs_survive(self) -> None:
        passage = "one\r\ntwo\rthree\nfour\tfive"
        self.assertEqual(declawd.canonicalise(passage), passage)


class SurrogateTests(unittest.TestCase):
    def test_lone_surrogate_is_rejected_before_scoring(self) -> None:
        with self.assertRaisesRegex(declawd.DeclawdError, "unpaired surrogate"):
            declawd.score("a\ud800b")

    def test_lone_surrogate_is_rejected_before_canonicalising(self) -> None:
        with self.assertRaisesRegex(declawd.DeclawdError, "unpaired surrogate"):
            declawd.canonicalise("a\udfffb")


class StateMachineTests(unittest.TestCase):
    def test_defined_transitions(self) -> None:
        self.assertEqual(declawd.next_state("pristine", "perturb"), "perturbed")
        self.assertEqual(declawd.next_state("perturbed", "canonicalise"), "analysed")
        self.assertEqual(declawd.next_state("pristine", "rewrite"), "rewritten")
        self.assertEqual(
            declawd.next_state("rewritten", "canonicalise"), "rewritten-analysed"
        )

    def test_rewriting_a_perturbed_envelope_is_refused(self) -> None:
        with self.assertRaisesRegex(declawd.DeclawdError, "invalid transition"):
            declawd.next_state("perturbed", "rewrite")

    def test_double_canonicalisation_is_refused(self) -> None:
        with self.assertRaisesRegex(declawd.DeclawdError, "invalid transition"):
            declawd.next_state("analysed", "canonicalise")

    def test_unknown_command_is_refused(self) -> None:
        with self.assertRaisesRegex(declawd.DeclawdError, "invalid transition"):
            declawd.next_state("pristine", "enhance")


class ParameterTests(unittest.TestCase):
    def test_shipped_parameters_are_valid(self) -> None:
        declawd.validate_parameters()

    def test_gamma_must_be_in_lowest_terms(self) -> None:
        with patch.object(declawd, "GAMMA_NUM", 2), patch.object(declawd, "GAMMA_DEN", 8):
            with self.assertRaisesRegex(declawd.DeclawdError, "lowest terms"):
                declawd.validate_parameters()

    def test_gamma_must_be_below_one(self) -> None:
        with patch.object(declawd, "GAMMA_NUM", 5), patch.object(declawd, "GAMMA_DEN", 4):
            with self.assertRaisesRegex(declawd.DeclawdError, "out of range"):
                declawd.validate_parameters()

    def test_minimum_effective_tokens_must_be_positive(self) -> None:
        with patch.object(declawd, "MIN_EFFECTIVE_TOKENS", 0):
            with self.assertRaisesRegex(declawd.DeclawdError, "must be positive"):
                declawd.validate_parameters()

    def test_seed_must_be_32_bytes(self) -> None:
        with patch.object(declawd, "SEED", b"short"):
            with self.assertRaisesRegex(declawd.DeclawdError, "32 bytes"):
                declawd.validate_parameters()


class ChangeReportTests(unittest.TestCase):
    def test_report_names_both_sides_of_a_substitution(self) -> None:
        lines = declawd.describe_changes("аbc", "abc")
        self.assertEqual(len(lines), 2)
        joined = " ".join(lines)
        self.assertIn("U+0430", joined)   # the Cyrillic that was there
        self.assertIn("U+0061", joined)   # the Latin that replaced it
        self.assertTrue(all(line.startswith("Position 0:") for line in lines))

    def test_report_names_a_zero_width_removal_and_nothing_else(self) -> None:
        # An index-by-index walk reported the shifted tail as changed too.
        lines = declawd.describe_changes("ab​cd", "abcd")
        self.assertEqual(len(lines), 1)
        self.assertIn("U+200B", lines[0])
        self.assertIn("Position 2", lines[0])

    def test_report_names_an_insertion_present_only_in_after(self) -> None:
        # The old comparison never walked characters unique to `after`.
        lines = declawd.describe_changes("abcd", "ab​cd")
        self.assertEqual(len(lines), 1)
        self.assertIn("inserted", lines[0])
        self.assertIn("U+200B", lines[0])

    def test_report_is_empty_when_nothing_changed(self) -> None:
        self.assertEqual(declawd.describe_changes("abcd", "abcd"), [])


if __name__ == "__main__":
    unittest.main()
