import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rust_osv", ROOT / "scripts/check-rust-osv.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class RustOsvTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.lock = Path(self.directory.name) / "Cargo.lock"
        self.lock.write_bytes((ROOT / "Cargo.lock").read_bytes())
        expected, _ = POLICY.inventory(self.lock)
        self.entries = [
            {"package": {"ecosystem": ecosystem, "name": name, "version": version}}
            for ecosystem, name, version in expected
        ]
        self.report = {"results": [{
            "source": {"type": "lockfile", "path": str(self.lock)},
            "packages": self.entries,
        }]}

    def entry(self, name, version=None):
        return next(entry for entry in self.entries if entry["package"]["name"] == name
                    and (version is None or entry["package"]["version"] == version))

    def review(self):
        return POLICY.review(self.report, self.lock)[0]

    def test_full_inventory_with_multiple_versions(self):
        findings, count = POLICY.review(self.report, self.lock)
        self.assertEqual(findings, [])
        self.assertEqual(count, len(self.entries))
        self.assertGreater(len([e for e in self.entries if e["package"]["name"] == "block-buffer"]), 1)

    def test_missing_duplicate_and_changed_packages_are_rejected(self):
        for mutation in ["missing", "duplicate", "changed"]:
            with self.subTest(mutation=mutation):
                report = copy.deepcopy(self.report)
                entries = report["results"][0]["packages"]
                if mutation == "missing":
                    entries.pop()
                elif mutation == "duplicate":
                    entries.append(entries[0])
                else:
                    entries[0]["package"]["version"] = "0.0.0"
                with self.assertRaisesRegex(ValueError, "inventory differs"):
                    POLICY.review(report, self.lock)

    def test_missing_wrong_and_extra_sources_are_rejected(self):
        for report in [{}, {"results": []}, {"results": [self.report["results"][0]] * 2},
                       {"results": [{"source": {"type": "directory", "path": str(self.lock)}}]}]:
            with self.assertRaises(ValueError):
                POLICY.review(report, self.lock)

    def test_rsa_aliases_share_the_reviewed_exception(self):
        for identifier in POLICY.RSA_IDS:
            self.entry("rsa")["vulnerabilities"] = [{"id": identifier, "aliases": sorted(POLICY.RSA_IDS - {identifier})}]
            self.assertEqual(self.review()[0]["decision"], "reviewed_rsa_exception_until_2026-11-28")

    def test_new_rsa_advisory_and_wrong_package_are_blocked(self):
        self.entry("rsa")["vulnerabilities"] = [{"id": "GHSA-new-advisory"}]
        self.entry("zip")["vulnerabilities"] = [{"id": "RUSTSEC-2023-0071"}]
        self.assertTrue(all(row["decision"] == "blocked" for row in self.review()))

    def test_unknown_rsa_alias_is_blocked(self):
        self.entry("rsa")["vulnerabilities"] = [{"id": "RUSTSEC-2023-0071", "aliases": ["CVE-unknown"]}]
        self.assertEqual(self.review()[0]["decision"], "blocked")

    def test_block_buffer_range_review_is_exact(self):
        self.entry("block-buffer", "0.10.4")["vulnerabilities"] = [{"id": "GHSA-qwgh-2vcv-g2f7"}]
        self.assertEqual(self.review()[0]["decision"], "outside_upstream_affected_range_0.11.0_to_0.12.1")
        self.entry("block-buffer", "0.12.1")["vulnerabilities"] = [{"id": "GHSA-qwgh-2vcv-g2f7"}]
        self.assertIn("blocked", [row["decision"] for row in self.review()])

    def test_block_buffer_checksum_changes_require_review(self):
        self.entry("block-buffer", "0.10.4")["vulnerabilities"] = [{"id": "GHSA-qwgh-2vcv-g2f7"}]
        self.lock.write_text(self.lock.read_text().replace(POLICY.BLOCK_BUFFER_CHECKSUM, "0" * 64))
        self.assertEqual(self.review()[0]["decision"], "blocked")

    def test_zip_regression_advisory_is_blocked(self):
        self.entry("zip")["vulnerabilities"] = [{"id": "GHSA-m665-v7pm-7grj"}]
        self.assertEqual(self.review()[0]["decision"], "blocked")

    def test_only_the_recorded_unmaintained_notice_is_informational(self):
        entry = self.entry("proc-macro-error")
        entry["vulnerabilities"] = [{"id": "RUSTSEC-2024-0370", "affected": [
            {"database_specific": {"informational": "unmaintained"}}
        ]}]
        self.assertEqual(self.review()[0]["decision"], "informational_unmaintained")
        entry["vulnerabilities"][0]["affected"][0]["database_specific"].clear()
        self.assertEqual(self.review()[0]["decision"], "blocked")

    def test_git_dependency_requires_inventory_review(self):
        self.lock.write_text(self.lock.read_text().replace(
            'registry+https://github.com/rust-lang/crates.io-index', 'git+https://example.test/crate', 1))
        with self.assertRaisesRegex(ValueError, "non-crates.io"):
            self.review()

    def test_malformed_scan_is_rejected(self):
        self.entry("rsa")["vulnerabilities"] = "not a list"
        with self.assertRaises(ValueError):
            self.review()

    def test_scanner_errors_and_invalid_json_cannot_pass(self):
        for status, output, exception in [(128, "{}", RuntimeError), (0, "invalid", ValueError), (0, "{}", ValueError)]:
            with self.subTest(status=status, output=output):
                results = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], status, output, "network error")]
                arguments = ["check-rust-osv.py", "--output", str(Path(self.directory.name) / "scan.json")]
                with patch("sys.argv", arguments), patch.object(POLICY.subprocess, "run", side_effect=results), patch.object(
                    POLICY.subprocess, "check_output", return_value=f"osv-scanner version: {POLICY.VERSION}\n"
                ):
                    with self.assertRaises(exception):
                        POLICY.main()


if __name__ == "__main__":
    unittest.main()
