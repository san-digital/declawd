import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecurityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="declawd-security-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copy(ROOT / "Cargo.lock", self.root / "Cargo.lock")
        shutil.copytree(ROOT / "src", self.root / "src")
        cargo = self.root / "cargo"
        cargo.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "sys.exit(int(os.environ.get('DECLAWD_TEST_AUDIT_EXIT', '0')))\n"
        )
        cargo.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
            "DECLAWD_AUDIT_DATE": "2026-10-29",
        }

    def run_policy(self):
        return subprocess.run(
            ["bash", str(ROOT / "scripts/check-security-advisories.sh"), "--json"],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def set_version(self, package, version):
        lock = self.root / "Cargo.lock"
        text, count = re.subn(
            r'(\[\[package\]\]\nname = "' + re.escape(package) + r'"\nversion = ")[^"]+("\n)',
            lambda match: match[1] + version + match[2],
            lock.read_text(),
        )
        self.assertEqual(count, 1)
        lock.write_text(text)

    def test_patched_zip_forwards_only_the_rsa_exception(self):
        for version in ["9.0.5", "9.1.3"]:
            with self.subTest(version=version):
                self.set_version("zip", version)
                result = self.run_policy()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout.splitlines()[-1]),
                    ["audit", "--ignore", "RUSTSEC-2023-0071", "--json"],
                )

    def test_vulnerable_and_prerelease_zip_are_rejected_before_audit(self):
        for version in ["8.6.0", "9.0.4", "9.0.5-rc.1"]:
            with self.subTest(version=version):
                self.set_version("zip", version)
                result = self.run_policy()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("GHSA-m665-v7pm-7grj", result.stderr)
                self.assertNotIn('["audit"', result.stdout)

    def test_an_extra_vulnerable_zip_is_rejected(self):
        with (self.root / "Cargo.lock").open("a") as lock:
            lock.write('\n[[package]]\nname = "zip"\nversion = "8.6.0"\n')
        result = self.run_policy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ZIP 8.6.0", result.stderr)

    def test_missing_zip_requires_reassessment(self):
        lock = self.root / "Cargo.lock"
        text, count = re.subn(
            r'\[\[package\]\]\nname = "zip"\n.*?(?=\[\[package\]\]|\Z)',
            "",
            lock.read_text(),
            flags=re.DOTALL,
        )
        self.assertEqual(count, 1)
        lock.write_text(text)
        result = self.run_policy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency missing", result.stderr)

    def test_expiry_warning_and_invalid_date(self):
        self.env["DECLAWD_AUDIT_DATE"] = "2026-11-28"
        result = self.run_policy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning", result.stdout)
        self.env["DECLAWD_AUDIT_DATE"] = "2026-11-29"
        self.assertIn("expired", self.run_policy().stderr)
        self.env["DECLAWD_AUDIT_DATE"] = "invalid"
        self.assertIn("invalid audit date", self.run_policy().stderr)

    def test_source_changes_require_reassessment(self):
        with (self.root / "src/lib.rs").open("a") as source:
            source.write("\n")
        result = self.run_policy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reviewed Rust source changed", result.stderr)

    def test_rsa_dependency_changes_require_reassessment(self):
        for package in ["c2pa", "c2pa_raw_crypto", "rsa"]:
            with self.subTest(package=package):
                shutil.copy(ROOT / "Cargo.lock", self.root / "Cargo.lock")
                self.set_version(package, "99.0.0")
                result = self.run_policy()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(package + " versions changed", result.stderr)

    def test_audit_failures_are_preserved(self):
        self.env["DECLAWD_TEST_AUDIT_EXIT"] = "17"
        self.assertEqual(self.run_policy().returncode, 17)


if __name__ == "__main__":
    unittest.main()
