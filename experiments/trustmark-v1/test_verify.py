import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("trustmark_verify", HERE / "verify.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class EvidenceTests(unittest.TestCase):
    def copy_evidence(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        target = Path(directory.name) / "evidence"
        shutil.copytree(HERE, target, ignore=shutil.ignore_patterns("__pycache__"))
        return target

    def test_frozen_evidence_includes_the_two_misses(self):
        summary = VERIFY.verify()
        self.assertEqual(summary["cases"], 12)
        self.assertEqual(summary["exact_payload_matches"]["marked"], 10)
        self.assertEqual(summary["exact_payload_matches"]["cleaned"], 10)
        self.assertEqual(summary["byte_identical_after_removal"], 12)

    def test_changed_image_is_rejected(self):
        root = self.copy_evidence()
        path = root / "run/gradient-png/cleaned.png"
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            VERIFY.verify(root)

    def test_dropped_case_and_inflated_summary_are_rejected(self):
        for change in ("drop", "inflate"):
            with self.subTest(change=change):
                root = self.copy_evidence()
                path = root / "run/results.json"
                result = json.loads(path.read_text())
                if change == "drop":
                    result["cases"].pop()
                else:
                    result["summary"]["exact_payload_matches"]["cleaned"] = 12
                path.write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    VERIFY.verify(root)

    def test_false_payload_match_is_rejected(self):
        root = self.copy_evidence()
        path = root / "run/results.json"
        result = json.loads(path.read_text())
        missed = next(case for case in result["cases"] if case["id"] == "tiles-png")
        missed["states"]["cleaned"]["decode"]["exact_payload"] = True
        path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "incorrect payload match"):
            VERIFY.verify(root)


if __name__ == "__main__":
    unittest.main()
