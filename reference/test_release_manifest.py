#!/usr/bin/env python3
"""Tests for the byte-stable release source contract."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/generate-release-manifest.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "generate_release_manifest", MODULE_PATH
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
release_manifest = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(release_manifest)


def isolated_git_environment() -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return environment


def archive_inventory(root: Path, archive_root: str) -> set[str]:
    if not (root / ".git").exists():
        return {
            path.relative_to(root).as_posix()
            for path in (root / archive_root).rglob("*")
            if (path.is_file() or path.is_symlink())
            and not path.name.endswith(".pyc")
            and path.name != ".DS_Store"
        }

    environment = isolated_git_environment()
    top_level = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if Path(top_level).resolve() != root.resolve():
        raise ValueError("Git checkout root differs from the source root")
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", archive_root],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
    ).stdout
    return {name for name in tracked.decode("utf-8").split("\0") if name}


class ArchiveInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temporary = Path(temporary.name)
        self.root = self.temporary / "source"
        self.archive_root = "experiments/attempt"
        self.payload = f"{self.archive_root}/nested/payload.json"
        self.write(self.payload)

    def write(self, name: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    def git(self, *arguments: str, root: Path | None = None) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=root or self.root,
            env=isolated_git_environment(),
            check=True,
            capture_output=True,
        )

    def test_source_export_uses_files_without_querying_git(self) -> None:
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("Git called")):
            self.assertEqual(archive_inventory(self.root, self.archive_root), {self.payload})

    def test_source_export_excludes_only_known_generated_files(self) -> None:
        for name in ("module.pyc", "__pycache__/module.cpython-311.pyc", ".DS_Store"):
            self.write(f"{self.archive_root}/{name}")
        self.assertEqual(archive_inventory(self.root, self.archive_root), {self.payload})
        for name in ("unexpected.json", "__pycache__/unexpected.txt", ".DS_Store.bak", "module.pyo"):
            self.write(f"{self.archive_root}/{name}")
            self.assertIn(f"{self.archive_root}/{name}", archive_inventory(self.root, self.archive_root))

    def test_source_export_inside_another_repository_uses_its_own_files(self) -> None:
        self.git("init", "--quiet", root=self.temporary)
        self.git("add", "source", root=self.temporary)
        added = f"{self.archive_root}/untracked.json"
        self.write(added)
        self.assertEqual(archive_inventory(self.root, self.archive_root), {self.payload, added})

    def test_git_checkout_uses_tracked_files_and_ignores_inherited_settings(self) -> None:
        self.git("init", "--quiet")
        self.git("add", ".")
        self.write(f"{self.archive_root}/untracked.json")
        foreign = self.temporary / "foreign"
        foreign.mkdir()
        self.git("init", "--quiet", root=foreign)
        with mock.patch.dict(os.environ, {
            "GIT_DIR": str(foreign / ".git"),
            "GIT_WORK_TREE": str(foreign),
            "GIT_INDEX_FILE": str(foreign / "foreign-index"),
            "GIT_CONFIG_GLOBAL": str(foreign / "missing-config"),
        }):
            self.assertEqual(archive_inventory(self.root, self.archive_root), {self.payload})
        self.assertFalse((foreign / "foreign-index").exists())

    def test_git_file_uses_tracked_inventory(self) -> None:
        self.git("init", "--quiet", "--separate-git-dir", str(self.temporary / "metadata"))
        self.git("add", ".")
        self.write(f"{self.archive_root}/untracked.json")
        self.assertTrue((self.root / ".git").is_file())
        self.assertEqual(archive_inventory(self.root, self.archive_root), {self.payload})


class ReleaseManifestTest(unittest.TestCase):
    def test_manifest_covers_both_experiments(self) -> None:
        required = {
            "docs/PLAN-V2.md",
            "docs/V2-RESULTS.md",
            "fixtures/candidate-review-v2.json",
            "fixtures/corpus.json",
            "fixtures/perturbations.json",
            "fixtures/profile-v1.json",
            "fixtures/profile-v2.json",
            "fixtures/registration-v1.json",
            "fixtures/registration-v2.json",
            "fixtures/rewrite.json",
            "fixtures/seed-v2.json",
            "fixtures/template.json",
            "fixtures/template-v2.json",
            "reference/calibrate.py",
            "reference/calibrate_v2.py",
            "reference/candidate_review.py",
            "reference/declawd.py",
            "reports/calibration-report-v1.json",
            "reports/calibration-report-v2.json",
            "reports/evaluation-report-v1.json",
            "reports/evaluation-report-v2.json",
            "vectors/controlled-removal-v1.json",
            "vectors/controlled-removal-v2.json",
            "vectors/scoring-v1.json",
            "vectors/scoring-v2.json",
        }
        self.assertTrue(required <= set(release_manifest.FILES))
        self.assertEqual(len(release_manifest.FILES), len(set(release_manifest.FILES)))

    def test_records_match_source_bytes(self) -> None:
        document = json.loads(release_manifest.render("v-test", None))
        for record in document["files"]:
            with self.subTest(path=record["path"]):
                data = (ROOT / record["path"]).read_bytes()
                self.assertEqual(record["byte_length"], len(data))
                self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())

    def test_manifest_retains_every_archived_attempt_file(self) -> None:
        actual = archive_inventory(ROOT, release_manifest.ARCHIVE_ROOT)
        recorded = {name for name in release_manifest.FILES if name.startswith(release_manifest.ARCHIVE_ROOT + "/")}
        self.assertEqual(recorded, actual)

    def test_archive_inventory_ignores_inherited_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(os.environ, {"GIT_DIR": str(Path(temporary) / "unrelated.git"), "GIT_WORK_TREE": temporary}):
                self.test_manifest_retains_every_archived_attempt_file()

    def test_default_release_follows_package_version(self) -> None:
        cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release-manifest-v1.json"
            subprocess.run(
                [sys.executable, str(MODULE_PATH), "--output", str(destination)],
                check=True,
                capture_output=True,
            )
            generated = destination.read_bytes()
            document = json.loads(generated)
        self.assertEqual(document["release"], f"v{cargo['package']['version']}-source-contract")
        self.assertIsNone(document["source_revision"])
        self.assertEqual(generated, (ROOT / "release-manifest-v1.json").read_bytes())

    def test_writer_emits_canonical_utf8_lf_bytes(self) -> None:
        release = "v-test"
        source_revision = "0" * 40
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release-manifest-v1.json"
            release_manifest.write_manifest(
                destination, release, source_revision
            )
            generated = destination.read_bytes()

        self.assertEqual(
            generated,
            release_manifest.render(release, source_revision).encode("utf-8"),
        )
        self.assertTrue(generated.endswith(b"\n"))
        self.assertNotIn(b"\r", generated)


if __name__ == "__main__":
    unittest.main()
