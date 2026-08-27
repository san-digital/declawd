# Declawd

Declawd is an inspect-first educational laboratory for known content carriers.
It publishes the frozen `declawd-v1` watermark reference and reproducibility
artefacts, and provides a conservative Rust CLI for:

- inspecting UTF-8 text for an explicit registry of Unicode structures;
- removing or replacing only the exact text selectors a user requests; and
- removing only an embedded C2PA/JUMBF store from PNG or JPEG files.

**This project does not detect or remove Claude's text watermark.** Without
Anthropic's key, a compatible detector and a published decision rule, Declawd
cannot directly score or exclude Anthropic's production watermark. A finding
does not show that AI was involved, and an absence does not prove human
authorship. Pixel-level marks are not tested.

## CLI

```text
declawd inspect <file> [--json] [--include-context] [--exit-zero]

declawd clean text <input> --output <output>
  [--remove U+200B]...
  [--remove-class tag-character]...
  [--replace U+202F=U+0020]...
  [--allow-empty] [--json]

declawd clean c2pa <input.png|jpg> --output <output>
  [--allow-empty] [--json]

declawd lab synthid score <trace.json> [--json]
```

Selectors compose as a union. Duplicate selectors are deduplicated. Removing
and replacing the same scalar is an error, as is replacing one scalar with a
target selected for another removal or replacement. The selectable class IDs are:

- `zero-width`
- `join-control`
- `bidi-control`
- `tag-character`
- `variation-selector`

There is deliberately no `format-control` umbrella. A leading U+FEFF is
reported as `bom`, preserved by every class operation, and removable only with
the explicit `--remove U+FEFF` selector. The complete, disjoint membership is
enumerated in [`spec/unicode-registry-v1.json`](spec/unicode-registry-v1.json).

### Input and output contract

- Text must be valid UTF-8 and is limited to 10 MiB. UTF-16 with a BOM and
  other invalid UTF-8 fail. BOM-less UTF-16 can be byte-wise valid UTF-8 and is
  not inferred from NUL patterns; callers must supply correctly labelled UTF-8
  input. A UTF-8 BOM, CRLF, lone CR, LF and tabs are otherwise preserved exactly.
- Reports and clean operations are limited to 10,000 Unicode findings or
  changed scalars. Inputs exceeding that bound fail instead of truncating or
  allocating an unbounded report; split the input or narrow the selectors.
- PNG and JPEG are identified by their signatures, not extensions, and limited
  to 100 MiB.
- Image validation checks bounded PNG chunks, all chunk CRCs, a first 13-byte
  IHDR, at least one IDAT and an exact empty final IEND. JPEG validation checks
  bounded segments, scan framing, byte stuffing, restart markers, multiple
  scans and a terminal EOI. It does not enforce every format semantic or
  perform a pixel decode. Use a full decoder as an additional validation
  boundary when those properties matter.
- Input file entries that are symbolic links or Windows reparse points are
  refused with no-follow handle opening. Parent-directory links are resolved by
  the operating system. Inputs are never overwritten and existing outputs are
  refused.
- Output is written beside the destination, verified, flushed and atomically
  renamed.
- A clean operation with no matching target succeeds with `changed:false` and
  creates no output. Add `--allow-empty` to create a byte-identical copy.
- `inspect` exits `1` when it finds a supported carrier and `0` otherwise. This
  makes findings visible in automated checks; use `--exit-zero` when a finding
  should not stop a `set -e` pipeline. Usage/input failures exit `2`, while
  post-transform verification failures exit `3`.
- JSON reports use [`declawd.report/v1`](spec/report-v1.md). Source context is
  absent unless `--include-context` is explicitly requested; that option can
  disclose up to 32 source scalars on either side of a finding.

## Standard input, SARIF and CI

`inspect` reads standard input when the file is a single hyphen, so it composes
without a temporary file. The 10 MiB text limit still applies: it cannot be read
from metadata here, so the bytes are counted as they arrive and one past the
limit is refused.

```sh
git show :docs/page.md | declawd inspect -
pbpaste | declawd inspect - --json
```

`--sarif` emits a SARIF 2.1.0 run for the code scanning tools a repository
already runs. Working examples are in `examples/ci/`: a GitHub Actions workflow
that uploads results per changed file, and a pre-commit hook that reports
against the staged content rather than the working tree.

```sh
declawd inspect docs/page.md --sarif --exit-zero > page.sarif
```

Two things about that output are deliberate.

The report carries no path. `Artifact` is a media type, a byte length and a
SHA-256, because a report describes bytes rather than a place on somebody's
disk. SARIF results need a location, so the one the tool was invoked with is
used, and `--sarif-uri` sets it explicitly when the scanned path is not the path
a reader should see.

And a run that finds nothing has not verified anything. This tool reads a
registry of Unicode carriers and embedded C2PA stores. It does not read
confusable letters, which are a cleaning selector rather than a finding, and it
does not read statistical token-choice watermarks at all. An empty SARIF file in
a security dashboard reads as a clean bill of health, so every untested channel
is emitted as a `notApplicable` result and the invocation repeats it in its
notifications. The reader is told what was not looked at, in the same file that
tells them what was.

## Public SynthID-Text laboratory

The v0.2 laboratory reproduces exact mean scoring for a fixed profile from
DeepMind's public `synthid-text` 0.2.1 implementation. It accepts token IDs,
not prose, and emits exact fractions, 12-place decimals and hashes of the
g-value and mask bitsets. It deliberately provides no detector threshold,
Claude compatibility or authorship verdict.

```sh
cargo run -- lab synthid score fixtures/synthid/trace-prepared-v1.json --json
python3 reference/synthid_reference.py fixtures/synthid/trace-prepared-v1.json
```

The Rust and standard-library Python reports are byte-identical. The contract
is split into four schemas:

- [`declawd.synthid-profile/v1`](spec/synthid-profile-v1.schema.json) pins the
  public keys, hash arithmetic, CPU table and score representation;
- [`declawd.synthid-distribution/v1`](spec/synthid-distribution-v1.schema.json)
  is a fixed, model-neutral candidate exercise for the browser laboratory;
- [`declawd.synthid-trace/v1`](spec/synthid-trace-v1.schema.json) permits only
  token IDs, an EOS ID and an optional expected result; and
- [`declawd.synthid-score/v1`](spec/synthid-score-v1.schema.json) reports exact
  scores and bitset digests without a decision.

Traces are limited to 8 MiB and 100,000 token IDs. They contain no prose,
logits, floating-point probabilities, private keys or thresholds. The
committed 65,536-bit sampling table was generated once with Torch 2.4.0 on
`device="cpu"`, packed LSB0 and pinned by SHA-256. Runtime code never
regenerates it.

The public reference itself warns that its hashing differs from production
Gemini hashing and its trained detectors do not transfer. Declawd makes the
same boundary explicit for Anthropic: naming SynthID-Text does not publish the
production key, configuration, detector or decision rule.

### Optional model runners

[`reference/synthid_model_runner.py`](reference/synthid_model_runner.py) can
produce token-only traces from pinned GPT-2 and Gemma 2B IT revisions. Model
weights and decoded output are never committed. GPT-2 is the ungated release
oracle. Gemma is optional and requires separate licence acceptance, Hugging
Face access and suitable hardware. The runner allowlists concrete model
classes, pins revisions, requires safetensors and disables remote code.

The release gate installs the complete, hash-pinned 40-package Linux CPU lock
in [`reference/synthid-runner-linux-cpu.lock`](reference/synthid-runner-linux-cpu.lock).
The supported runtime is Torch 2.13.0, Transformers 5.15.0, safetensors 0.8.0
and JAX 0.11.0. Torch 2.4.0 remains only as the historical CPU table-generation
provenance and is not installed. The DeepMind 0.2.1 source is checked out clean
at its immutable commit for compatibility checks rather than installed with its
obsolete runtime pins.

Three registered token-ID substitutions and their exact independent score
effects are frozen in
[`registered-edits-v1.json`](fixtures/synthid/registered-edits-v1.json). They
contain no decoded model output, detector threshold or verdict.

The retained version-of-record [SynthID-Text paper](evidence/synthid/README.md)
is CC BY 4.0 and pinned by DOI, length and SHA-256. The teaching code follows
the separately licensed Apache-2.0 reference implementation; it does not copy
production keys or model weights.

## C2PA scope

`clean c2pa` removes only the embedded C2PA store through `c2pa-rs`. It does not
strip EXIF orientation, ICC profiles, IPTC copyright, unrelated XMP or image
data. Remote manifest references are not followed or removed. Soft bindings are
not tested. The accurate result is “embedded C2PA store removed”, not
“provenance removed” or “Claude watermark removed”.

The SDK is pinned to `c2pa =0.90.12` with default and network features disabled;
only `file_io` and `rust_native_crypto` are enabled. This same-day pre-release
pin was reassessed on 12 August 2026 and retained for v0.2.0; upgrades must be
deliberate. CI verifies the manifest pin against `Cargo.lock`. `c2pa-rs`
declares `MIT OR Apache-2.0`; this project elects Apache-2.0 and generates
dependency notices with `cargo-about`.

Synthetic C2PA stores exercise malformed-input and preservation cases. Two
additional PNG/JPEG fixtures were signed with `c2patool 0.27.11`'s development
certificate. The independent Linux oracle is pinned separately to `c2patool
0.27.12`; it must find the embedded manifests and
matching hard bindings, run Declawd, confirm the cleaned bytes equal the
committed sources and confirm no claim remains. The gate deliberately does not
assert current certificate validity, so it does not rot when a test certificate
expires; nor does it establish public trust-list acceptance. Ordinary Rust
tests run on Linux, macOS and Windows.

## Deferred registry candidates

Typographic spaces, combining marks and mixed-script confusables are candidates
for a separately versioned v0.2 registry after their finite taxonomy and
multilingual negative controls have been reviewed. In v0.1 the CLI can still
transform an exact scalar such as `--replace U+202F=U+0020`, but `inspect` does
not classify it and no broad class selector is available.

## Frozen evidence and reproduction

The repository is a curated public snapshot, not an export of private history.

Frozen artefacts:

- `reference/declawd.py` and its original 45-test suite;
- `fixtures/profile-v1.json`, registration, template, corpus, rewrite and
  perturbation fixtures;
- calibration and evaluation reports;
- cross-runtime scoring vectors; and
- a machine-readable report schema, normative report vector and source-contract
  release manifest;
- the six-substitution controlled-removal vector, including every cumulative
  score. Its original-passage offsets are 75, 175, 295, 371, 631 and 994; the
  final result is 358 effective contexts, 102 green and z =
  1.5256954942433834.

Reproduction scripts are in `reference/`. Reproduce the committed run without
choosing a new seed:

```sh
python3 reference/calibrate.py \
  --seed-hex 3af0a69fbe7c97fb6c73d2c96d7824d26782d36b6e5b6379eb0886382ce39164
python3 -m unittest discover -s reference -p 'test_*.py'
```

`build_corpus.py` requires separately downloaded public-domain Project
Gutenberg source texts. The committed corpus means tests and builds need no
network. Do not run `calibrate.py` without `--seed-hex` merely to verify this
release: doing so intentionally creates a new experiment.

## Development

Rust 1.88 or newer is required.

```sh
cargo fmt -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets
./scripts/check-c2pa-pin.sh
./scripts/check-security-advisories.sh
./scripts/check-third-party-licences.sh
./scripts/check-c2patool-fixtures.sh
python3 scripts/check-python-runtime-lock.py
./scripts/check-synthid-bundle.sh
# With cargo-cyclonedx 0.5.9 and the exact tools in
# reference/sbom-tool-requirements.txt installed:
./scripts/check-sbom.sh
./scripts/check-python-sbom.sh
./scripts/check-sboms-clean-checkouts.sh
```

See [ETHICS.md](ETHICS.md) before using or extending the cleaner.

## Release verification

Release archives include SHA-256 checksum files and GitHub build-provenance
attestations. Each release also carries two checksummed, reproducible
CycloneDX 1.5 SBOMs: one for the Rust runtime and build graph, and one for the
reviewed 40-package Python runner closure plus its excluded DeepMind source
reference. Test-only Rust development dependencies are excluded. Verify them
before running a downloaded binary:

```sh
# Linux archive
sha256sum --check declawd-v0.2.0-<target>.tar.gz.sha256

# macOS archive
shasum -a 256 --check declawd-v0.2.0-<target>.tar.gz.sha256

# Windows archive, from a shell with sha256sum
sha256sum --check declawd-v0.2.0-<target>.zip.sha256

# SBOM on Linux or Windows
sha256sum --check declawd-v0.2.0.cdx.json.sha256
sha256sum --check declawd-v0.2.0-python.cdx.json.sha256
sha256sum --check declawd-v0.2.0-synthid-contracts.tar.gz.sha256

# SBOM on macOS
shasum -a 256 --check declawd-v0.2.0.cdx.json.sha256
shasum -a 256 --check declawd-v0.2.0-python.cdx.json.sha256
shasum -a 256 --check declawd-v0.2.0-synthid-contracts.tar.gz.sha256

gh attestation verify declawd-v0.2.0-<target>.tar.gz \
  --repo san-digital/declawd

gh attestation verify declawd-v0.2.0-synthid-contracts.tar.gz \
  --repo san-digital/declawd
```

The macOS and Windows binaries are not platform code-signed or notarised.
GitHub provenance attests the workflow and source revision; it is not an
operating-system signing certificate. Build from the tagged source if local
policy cannot accept an unsigned binary.

## Licensing and related work

Original software, specifications and documentation are Apache-2.0. Corpus
provenance is recorded in its fixture. See [NOTICE](NOTICE) and the generated
[third-party notices](THIRD_PARTY_LICENSES.txt). Optional Python runner notices
are recorded separately in
[`SYNTHID_THIRD_PARTY_NOTICES.md`](SYNTHID_THIRD_PARTY_NOTICES.md).

[demark](https://github.com/jcsuen/demark) informed the inspect-first workflow
and candid limitations. No demark code was copied, forked or executed here; its
PolyForm Noncommercial licence is incompatible with reuse for this project.
