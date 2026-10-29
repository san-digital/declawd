import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import experiment as e


class MixedPassageTests(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))

    def test_hash_encoding(self):
        a, b = b"the", b"record"
        raw = b"declawd/mixed-passage-v1/green" + self.key + b"\0\0\0\3" + a + b"\0\0\0\6" + b
        self.assertEqual(e.green("the", "record", self.key), int(hashlib.sha256(raw).hexdigest()[:16], 16) % 4 == 0)
        self.assertNotEqual(e.green.cache_info().maxsize, None)

    def test_token_boundaries(self):
        self.assertEqual(e.tokens("A can't. naïve A\u200bB"), ["a", "can't", "na", "ve", "a", "b"])
        self.assertEqual(e.prefix("One, two. Three", 2), "One, two")
        with self.assertRaises(ValueError):
            e.prefix("One", 2)

    def test_pairs_are_distinct(self):
        self.assertEqual(e.counts(["a", "b", "a", "b"], self.key)["n"], 2)
        self.assertEqual(e.counts(["a"] * 100, self.key)["n"], 1)

    def test_strict_integer_threshold(self):
        score = {"n": 48, "g": 15}
        self.assertEqual(e.z(score), 1)
        self.assertFalse(e.crosses(score, 100))
        self.assertTrue(e.crosses(score, 95))
        self.assertFalse(e.crosses({"n": 31, "g": 31}, 0))
        self.assertFalse(e.crosses({"n": 48, "g": 0}, 0))

    def test_window_end_and_left_boundary(self):
        words = [f"w{n}" for n in range(145)]
        _, trace = e.search(words, self.key)
        windows64 = [r for r in trace if r["end"] - r["start"] == 64]
        self.assertEqual([r["start"] for r in windows64], [0, 16, 32, 48, 64, 80, 81])
        for row in trace:
            pairs = set(zip(words[row["start"]:row["end"] - 1], words[row["start"] + 1:row["end"]]))
            self.assertEqual(row["n"], len(pairs))
            self.assertEqual(row["g"], sum(e.green(a, b, self.key) for a, b in pairs))
            self.assertEqual(row["n"], row["end"] - row["start"] - 1)

    def test_exact_ranking_and_ties(self):
        a = {"start": 0, "end": 64, "n": 48, "g": 15}
        b = {"start": 16, "end": 80, "n": 48, "g": 15}
        self.assertTrue(e.better(a, b))
        self.assertFalse(e.better(b, a))
        short = {**a, "end": 32}
        self.assertTrue(e.better(short, a))
        low = {**a, "g": 0}
        self.assertTrue(e.better(a, low))
        self.assertFalse(e.better(low, a))

    def test_search_matches_brute_force(self):
        words = ["word" + str(n % 101) for n in range(279)]
        best, trace = e.search(words, self.key)
        eligible = [r for r in trace if r["n"] >= e.CONFIG["minimum_pairs"]]
        oracle = sorted(eligible, key=lambda r: (-e.z(r), r["start"], r["end"] - r["start"]))[0]
        self.assertEqual(best, oracle)
        self.assertIsNone(e.search(["repeat"] * 128, self.key)[0])

    def test_insert_span_and_token_count(self):
        for position, expected in [("start", [0, 2]), ("middle", [2, 4]), ("end", [4, 6])]:
            text, span = e.insert("One, two. Three four.", "Test passage", position)
            self.assertEqual(span, expected)
            self.assertEqual(len(e.tokens(text)), 6)
            self.assertEqual(e.tokens(text)[span[0]:span[1]], ["test", "passage"])

    def test_threshold_uses_every_length(self):
        rows = []
        for length in e.CONFIG["background_tokens"]:
            for i in range(24):
                score = {"n": 48, "g": 15 if length == 768 and i == 0 else 12}
                rows.append({"background_tokens": length, "whole": score})
        self.assertEqual(e.threshold(rows, "whole"), 100)

    def test_summary_counts_document_maxima(self):
        rows = [{"condition": "human", "background_tokens": 128, "insertion_tokens": 0, "position": "none", "author": "Example", "detected": {"whole": False, "window": True, "uncorrected_window": True}, "whole": {"n": 100, "g": 25}, "window": {"n": 60, "g": 30}}]
        summary = [r for r in e.summarise(rows) if r["position"] == "all"][0]
        self.assertEqual(summary["documents"], 1)
        self.assertEqual(summary["window"], 1)
        self.assertEqual(summary["by_author"]["Example"]["window"], 1)

    def test_second_draw_does_not_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registration.json").write_text('{"files": {}}')
            (root / "seed.json").write_text("existing draw")
            with patch.object(e, "HERE", root), patch.object(e, "verify_inputs"), patch.object(e, "committed"), patch.object(e.secrets, "token_bytes") as sample:
                with self.assertRaises(FileExistsError):
                    e.draw()
                sample.assert_not_called()
            self.assertEqual((root / "seed.json").read_text(), "existing draw")

    def test_registered_input_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.txt").write_text("original")
            registration = {"config": e.CONFIG, "experiment_id": e.CONFIG["experiment_id"], "files": {"input.txt": e.digest(b"original")}}
            (root / "registration.json").write_text(json.dumps(registration))
            with patch.object(e, "HERE", root), patch.object(e, "ROOT", root):
                e.verify_inputs()
                (root / "input.txt").write_text("edited")
                with self.assertRaisesRegex(ValueError, "Registered input differs"):
                    e.verify_inputs()

    def test_seed_registration_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registration.json").write_text("changed registration")
            (root / "seed.json").write_text('{"registration_sha256": "different"}')
            with patch.object(e, "HERE", root), patch.object(e, "verify_inputs"):
                with self.assertRaisesRegex(ValueError, "different registration"):
                    e.context()

    def test_unavailable_calibration_stops_run(self):
        backgrounds = [{"id": "repeated", "author": "Example", "split": "calibration", "text": "repeat " * 768}]
        with self.assertRaisesRegex(ValueError, "Unavailable calibration score"):
            e.calibrate_data(self.key, backgrounds)


if __name__ == "__main__":
    unittest.main()
