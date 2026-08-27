from __future__ import annotations

import json
import re
import statistics
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

import declawd


class DocumentationPinTests(unittest.TestCase):
    def test_dependency_and_release_examples_follow_cargo_toml(self) -> None:
        cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
        package_version = cargo["package"]["version"]
        c2pa_version = cargo["dependencies"]["c2pa"]["version"].removeprefix("=")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn(f"The SDK is pinned to `c2pa ={c2pa_version}`", readme)
        self.assertIn(f"`c2pa {c2pa_version}` selects", security)

        release_section = readme.split("## Release verification", 1)[1]
        release_section = release_section.split("## Licensing and related work", 1)[0]
        documented_versions = set(re.findall(r"declawd-v(\d+\.\d+\.\d+)", release_section))
        self.assertEqual(documented_versions, {package_version})


class FrozenV1LimitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(
            (ROOT / "fixtures" / "profile-v1.json").read_text(encoding="utf-8")
        )
        cls.corpus = json.loads(
            (ROOT / "fixtures" / "corpus.json").read_text(encoding="utf-8")
        )["passages"]
        cls.segments = json.loads(
            (ROOT / "fixtures" / "template.json").read_text(encoding="utf-8")
        )["segments"]
        declawd.load_profile(ROOT / "fixtures" / "profile-v1.json")

    def test_registered_floor_sits_below_the_measured_band(self) -> None:
        self.assertEqual(self.profile["min_effective_tokens"], 120)
        full_counts = [declawd.count_contexts(passage["text"]) for passage in self.corpus]
        self.assertEqual(
            (len(full_counts), min(full_counts), statistics.median(full_counts), max(full_counts)),
            (192, 200, 267, 638),
        )

        crossing_results = []
        threshold = self.profile["threshold"]["numerator"]
        for passage in self.corpus:
            words = passage["text"].split()
            low, high = 1, len(words)
            while low < high:
                middle = (low + high) // 2
                result = declawd.score(" ".join(words[:middle]))
                if result.effective_tokens >= declawd.MIN_EFFECTIVE_TOKENS:
                    high = middle
                else:
                    low = middle + 1
            result = declawd.score(" ".join(words[:low]))
            if result.z_display is not None and result.z_display > threshold:
                crossing_results.append(
                    (passage["id"], result.effective_tokens, round(result.z_display, 2))
                )

        crossing_results.sort(key=lambda item: item[2], reverse=True)
        self.assertEqual(
            crossing_results,
            [
                ("pg20203-09", 120, 3.16),
                ("pg33310-00", 120, 2.95),
                ("pg34901-07", 120, 2.32),
                ("pg2931-04", 120, 1.90),
            ],
        )

    def test_two_registered_candidates_do_not_fit_their_frames(self) -> None:
        self.assertEqual(self.segments[39], ["worth", "due", "wise", "prudent"])
        self.assertEqual(self.segments[116], ["continue", "proceed", "carry", "press"])
        marked = declawd.generate(self.segments, marked=True)
        self.assertIn("due the delay", marked)
        self.assertIn("carry with a run", marked)

    def test_readme_discloses_the_v1_boundary(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/san-digital/declawd/issues/17", readme)
        self.assertIn("withhold scores and verdicts below 200 pairs", readme)
        self.assertIn("will not be corrected in place", readme)


if __name__ == "__main__":
    unittest.main()
