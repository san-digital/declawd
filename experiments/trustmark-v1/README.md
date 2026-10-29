# Two carriers

On 29 October 2026, the matching TrustMark Q decoder recovered the exact payload in 10 of 12 marked image files. The same ten payloads decoded after an embedded C2PA store was added and then removed with Declawd. Both tiled images were missed at every marked stage. Every cleaned file was byte-identical to its marked version from before C2PA was added.

The [plan](PLAN.md), [registration](registration.json), input hashes, runner, model hashes and Python wheel lock were [committed before encoding](https://github.com/san-digital/declawd/commit/e4adcb3). The experiment made one encoding attempt per file and retained both misses. Its [results](run/results.json) include all twelve cases, 48 decoder observations, 48 raw C2PA oracle reports and Declawd's twelve cleaning reports.

## Results

| State | Embedded C2PA stores | Exact TrustMark payloads |
|---|---|---|
| Unmarked source | 0/12 | 0/12 |
| Marked image | 0/12 | 10/12 |
| Marked and C2PA-signed | 12/12 | 10/12 |
| C2PA-cleaned | 0/12 | 10/12 |

An exact payload requires a positive decoder result, all 68 registered bits and BCH_4 schema 2. None of the twelve unmarked source files produced a decoder detection. This small control set supplies no population false-positive estimate.

| Scene | PNG, before/after | JPEG, before/after |
|---|---|---|
| Gradient | Match / match | Match / match |
| Coloured tiles | Miss / miss | Miss / miss |
| Deterministic noise | Match / match | Match / match |
| Drawn landscape | Match / match | Match / match |
| Portrait circles | Match / match | Match / match |
| Generated texture | Match / match | Match / match |

The independent `c2patool 0.27.12` oracle reported matching content bindings and validated claim signatures for all twelve signed files. It reported the development signing credential as untrusted in each case. After cleaning, it reported no claim in all twelve files. Declawd's reports confirmed that the embedded store was absent and that non-C2PA bytes and compressed image data were unchanged. The saved files independently confirm byte identity with the marked inputs, and RGB hashes match across signing and removal for every case.

These files demonstrate a pixel watermark surviving removal of the embedded C2PA record. The same decoder recovered every payload it had recovered before signing. The two tiled misses remain part of the result. JPEG encoding changed pixels when the marked files were saved, before C2PA was added. This experiment supplies results for the fixed generated images, TrustMark Q and the selected decoder settings. SynthID, text watermarks, production vendor detectors, remote manifest recovery and public trust-list acceptance remain outside its measurements.

## Files

`assets/` contains the generated sources fixed in the registration. `run/` contains the recorded sources, marked images, signed images, cleaned images, signing manifests and raw reports. `models.json` records the three Adobe model/configuration URLs, their upstream MD5 values and the SHA-256 hashes verified for this run. The 64.96 MB of model files are downloaded separately. The source revision is `6df5a0a29b51cbec832695fdf02051a1937e37bd`.

The isolated runtime used Python 3.12 on macOS arm64, PyTorch 2.15.0, torchvision 0.29.2 and Pillow 13.0.0. [The wheel record](runtime-wheels.json) and [hash lock](requirements-macos-arm64.lock) cover all 32 installed runtime packages. [The OSV advisory check](runtime-advisory-check.json) found no known vulnerabilities in that complete inventory on 29 October, with no advisory exclusions. The runner uses CPU inference, one thread, deterministic algorithms and the weights-only checkpoint loader. It accepts the recorded local model files and loads neither the optional watermark remover nor the bounding-box detector.

The generated assets and experiment code follow this repository's Apache-2.0 licence. Adobe's [MIT licence](TRUSTMARK-LICENSE.txt) covers TrustMark code and model files according to its [pinned README](https://github.com/adobe/trustmark/tree/6df5a0a29b51cbec832695fdf02051a1937e37bd). The experiment is excluded from the published Rust crate and adds no CLI runtime dependency. The frozen Declawd v1/v2 and SynthID contracts are unchanged.

## Check

The evidence checker verifies input and output hashes, the complete case and file inventories, raw C2PA facts, soft-binding payloads, decoder match flags, cleaning reports and result counts. With Pillow installed, it also decodes every image and compares its RGB hash. It checks the saved observations. Repeating model inference is a separate operation.

```sh
python3 experiments/trustmark-v1/verify.py
python3.12 -m pip install --require-hashes --only-binary=:all: --requirement experiments/trustmark-v1/verifier-requirements.txt
python3.12 experiments/trustmark-v1/verify.py --pixels
python3 -B -m unittest discover -s experiments/trustmark-v1 -p 'test_*.py' -v
```

CI runs the pixel check and four tests that retain the misses and reject changed files, dropped cases, inflated counts and false payload matches. It downloads no TrustMark models and runs no TrustMark inference.

## Replay

The recorded runtime lock targets Python 3.12 on macOS arm64. Run these commands from the repository root, using new temporary directories. A replay reads the registered sources and writes a new output directory, preserving the recorded run.

```sh
git clone --filter=blob:none https://github.com/adobe/trustmark.git /tmp/trustmark-v1-source
git -C /tmp/trustmark-v1-source checkout --detach 6df5a0a29b51cbec832695fdf02051a1937e37bd
python3.12 -m venv /tmp/trustmark-v1-runtime
/tmp/trustmark-v1-runtime/bin/python -m pip install --require-hashes --only-binary=:all: --requirement experiments/trustmark-v1/requirements-macos-arm64.lock
/tmp/trustmark-v1-runtime/bin/python experiments/trustmark-v1/fetch-models.py --source /tmp/trustmark-v1-source
CARGO_TARGET_DIR=/tmp/declawd-trustmark-build cargo build --locked
cargo install c2patool --version 0.27.12 --locked --root /tmp/trustmark-v1-oracle
C2PATOOL=/tmp/trustmark-v1-oracle/bin/c2patool DECLAWD_BIN=/tmp/declawd-trustmark-build/debug/declawd /tmp/trustmark-v1-runtime/bin/python experiments/trustmark-v1/experiment.py run --source /tmp/trustmark-v1-source --output /tmp/trustmark-v1-replay
```

Compare payload recovery and preservation relationships with the frozen results. A fresh signing operation creates new C2PA identifiers and signatures, so its signed-file hashes will differ. Another image set, model or decoder search needs its own registration.
