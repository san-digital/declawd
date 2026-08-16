#!/usr/bin/env python3
"""Tests for the byte-stable release source contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/generate-release-manifest.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "generate_release_manifest", MODULE_PATH
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
release_manifest = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(release_manifest)


class ReleaseManifestTest(unittest.TestCase):
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
