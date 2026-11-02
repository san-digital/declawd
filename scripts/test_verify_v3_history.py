from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v3_history", ROOT / "scripts/verify-v3-history.py")
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


class TaggedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory(prefix="declawd-v3-history-template-")
        cls.top = Path(cls.template.name)
        subprocess.run(["git", "init", "-q", str(cls.top)], check=True)
        cls.git("config", "user.name", "Evidence Test")
        cls.git("config", "user.email", "evidence-test@example.invalid")
        cls.git("remote", "add", "origin", str(ROOT))
        cls.git("fetch", "--quiet", "--no-tags", "origin", f"refs/tags/{history.TAG}:refs/tags/{history.TAG}")
        shutil.copytree(ROOT / history.PREFIX, cls.top / history.PREFIX, ignore=shutil.ignore_patterns("__pycache__"))
        cls.git("add", ".")
        cls.git("-c", "commit.gpgsign=false", "commit", "-qm", "squashed evidence")

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(["git", "-C", str(cls.top), *args], stderr=subprocess.PIPE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="declawd-v3-history-case-")
        self.root = Path(self.directory.name)
        shutil.copytree(self.top, self.root, dirs_exist_ok=True)

    def tearDown(self):
        self.directory.cleanup()

    def case_git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE)

    def test_squashed_checkout_uses_the_pinned_original_history(self):
        seed = json.loads((self.root / history.PREFIX / history.SEED).read_text())
        check = subprocess.run(["git", "merge-base", "--is-ancestor", seed["registration_commit"], "HEAD"], cwd=self.root)
        self.assertNotEqual(check.returncode, 0)
        result = history.verify_history(self.root)
        self.assertEqual(result["evidence_commit"], history.EVIDENCE_COMMIT)
        self.assertNotEqual(result["registration_commit"], result["seed_commit"])
        self.assertEqual(set(result["output_commits"]), set(history.OUTPUTS))

    def test_missing_tag_fails_without_implicit_fetch(self):
        self.case_git("tag", "-d", history.TAG)
        with self.assertRaisesRegex(ValueError, "missing evidence tag"):
            history.verify_history(self.root)

    def test_explicit_fetch_can_restore_a_missing_tag(self):
        self.case_git("tag", "-d", history.TAG)
        self.assertEqual(history.verify_history(self.root, fetch_history=True)["evidence_commit"], history.EVIDENCE_COMMIT)

    def test_moved_tag_is_rejected_even_with_fetch_enabled(self):
        self.case_git("tag", "-f", history.TAG, "HEAD")
        with self.assertRaisesRegex(ValueError, "evidence tag moved"):
            history.verify_history(self.root, fetch_history=True)

    def test_edited_output_is_rejected_before_reproduction(self):
        path = self.root / history.PREFIX / history.OUTPUTS[1]
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "current bytes differ from tagged evidence"):
            history.verify_history(self.root)

    def test_edited_registered_verifier_is_rejected(self):
        path = self.root / history.PREFIX / "verify.py"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "current bytes differ from tagged evidence"):
            history.verify_history(self.root)


if __name__ == "__main__":
    unittest.main()
