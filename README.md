# Declawd

Declawd is an educational toolkit for inspecting known content carriers and reproducing published watermark experiments. Its Rust CLI can inspect listed Unicode structures, apply exact text edits you select, remove embedded C2PA stores from PNG/JPEG files, and score token traces from a fixed public SynthID-Text reference.

The [website](https://declawd.com) explains the experiments and provides browser tools. Its text checker uses the recorded `declawd-v2-r2` teaching profile. Declawd has no compatible production key, detector or decision rule for Claude, ChatGPT or Gemini. Its findings and scores do not establish authorship or whether someone used AI.

## Install

[Download 0.3.3 binaries](https://declawd.com/downloads) for Apple Silicon, Intel Mac, Linux or Windows, or install the [crate](https://crates.io/crates/declawd/0.3.3) with Rust 1.96 or newer:

```sh
cargo install declawd --locked --version 0.3.3
```

Archives have SHA-256 checksums and GitHub build attestations. Mac and Windows binaries are unsigned by operating-system signing services. The [verification guide](docs/DEVELOPMENT.md#release-checks) explains what to check before running them.

## First checks

```sh
declawd inspect notes.txt --json --exit-zero
declawd clean text notes.txt --output edited.txt --remove U+200B
declawd clean c2pa signed.png --output stripped.png --json
```

Inspection reports only its explicit registry and embedded stores. A clean operation applies the selectors you request and refuses an existing output path. When nothing matches, it returns `changed:false` and creates no file unless you add `--allow-empty`.

Unicode characters can carry meaning in ordinary writing. Review each edit in context. C2PA removal leaves remote references and pixel watermarks outside the operation, and it does not validate a signature or establish that an image is authentic.

## Guides

| Task | Guide |
|---|---|
| Inspect files, select edits, understand reports and exit codes | [CLI](docs/CLI.md) |
| Use standard input, SARIF or the CI examples | [CLI integration](docs/CLI.md#integration) |
| Score SynthID token traces or use optional model runners | [SynthID lab](docs/SYNTHID.md) |
| Find recorded results and reproduce them without a new draw | [Evidence](docs/EVIDENCE.md) |
| Register future inputs and record one seed | [Future registration](docs/FUTURE-REGISTRATION.md) |
| Build, contribute or verify a release | [Development](docs/DEVELOPMENT.md) |
| Report a vulnerability or inspect advisory exceptions | [Security](SECURITY.md) |

## Recorded results

| Record | Retained outcome |
|---|---|
| Root r2 profile | The marked fixture scored 0.77 below 2.30. Six of 96 full human evaluation passages crossed. |
| Separate v3 run | The marked fixture scored 1.90 below 3.30. One of 96 full evaluation passages crossed. |
| Mixed passages | The adjusted search detected 19 of 648 marked mixtures and correctly located six. |
| Window families | Exact enumeration of 4,096 synthetic sequences measures false alarms within its independent null model. |
| TrustMark | The matching decoder recovered ten of twelve exact payloads before and after C2PA removal, retaining both misses. |

The [evidence guide](docs/EVIDENCE.md) links the plans, registrations, complete outputs and limits. Reused corpora, small controls and synthetic models have separate scopes. These measurements supply no production-detector or population guarantee. Registered files retain their bytes, including failures and the invalidated first v2 attempt.

## Boundaries

Use the tools on content you own or are authorised to change. Findings must not support employment, education, disciplinary, legal, forensic or authorship decisions. Read [responsible use](ETHICS.md) before extending or applying the cleaner.

The CLI makes no network requests. Release 0.3.3 uses c2pa 0.91.8 and ZIP 9.2.2. The [security policy](SECURITY.md) records the scoped RSA exception, its 28 November 2026 expiry and the checks required for reassessment.

## Licence

Original code, specifications and documentation are Apache-2.0. See [NOTICE](NOTICE), [dependency notices](THIRD_PARTY_LICENSES.txt) and the separate [SynthID notices](SYNTHID_THIRD_PARTY_NOTICES.md). Fixtures and optional models retain their own recorded licences.
