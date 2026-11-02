# CLI guide

Install the published version through the [README](../README.md#install). These commands run locally and apply to the selected file. The CLI makes no network requests and has no recursive bulk-cleaning or general rewriting command.

## Commands

```text
declawd inspect <file|-> [--json|--sarif] [--sarif-uri <uri>] [--include-context] [--exit-zero]
declawd clean text <input> --output <output> [selectors] [--allow-empty] [--json]
declawd clean c2pa <input.png|jpg> --output <output> [--allow-empty] [--json]
declawd lab synthid score <trace.json> [--json]
```

`inspect` reports listed Unicode structures in UTF-8 text or an embedded C2PA/JUMBF store in PNG/JPEG. It does not inspect word-choice watermarks or classify confusable letters. The [SynthID lab](SYNTHID.md) accepts token traces separately.

## Text edits

Choose exact code points, classes or replacements. Multiple selectors compose as a union and duplicates are deduplicated:

```sh
declawd clean text input.txt --output edited.txt --remove U+200B
declawd clean text input.txt --output edited.txt --remove-class tag-character
declawd clean text input.txt --output edited.txt --replace U+202F=U+0020
```

| Class ID | Selected structure |
|---|---|
| `zero-width` | Listed zero-width characters |
| `join-control` | Join controls |
| `bidi-control` | Bidirectional controls |
| `tag-character` | Tag characters |
| `variation-selector` | Variation selectors |

The [registry](../spec/unicode-registry-v1.json) enumerates complete, disjoint memberships. There is no `format-control` umbrella. A leading U+FEFF is reported as `bom`, preserved by class operations and removable only with `--remove U+FEFF`.

Removing and replacing the same scalar is an error. A replacement target also cannot be selected for another removal or replacement. Typographic spaces, combining marks and mixed-script confusables need exact selectors where applicable. Their broader classification remains a candidate for a separately reviewed registry.

## File contract

| Input | Limit and handling |
|---|---|
| Text | Valid UTF-8, at most 10 MiB |
| Unicode findings or changed scalars | At most 10,000, with refusal instead of truncation |
| PNG/JPEG | Detected by signature, at most 100 MiB |
| SynthID trace | At most 8 MiB and 100,000 token IDs |

UTF-16 with a BOM and other invalid UTF-8 are refused. BOM-less UTF-16 can be valid UTF-8 bytes, so the CLI does not infer an encoding from NUL patterns. Supply correctly labelled UTF-8. A UTF-8 BOM, CRLF, lone CR, LF and tabs are preserved unless selected for an explicit edit.

The final input entry is opened with no-follow semantics and checked on that handle. Symbolic links and Windows reparse points are refused. Parent-directory links follow ordinary operating-system resolution. Inputs are preserved, and existing output paths are refused.

Successful output is written beside its destination, verified, flushed and atomically renamed. A clean operation with no target returns `changed:false` and creates no output. `--allow-empty` instead creates a byte-identical copy.

## Image stores

`clean c2pa` uses the PNG/JPEG asset I/O paths in the pinned c2pa SDK. It removes the embedded store while preserving image data, EXIF orientation, ICC profiles, IPTC copyright and unrelated XMP. Remote manifest references remain untouched. The result describes removal of an embedded C2PA store.

Container checks cover bounded PNG chunks, CRCs, a first 13-byte IHDR, at least one IDAT and an exact empty final IEND. JPEG checks cover bounded segments, scan framing, byte stuffing, restart markers, multiple scans and a terminal EOI. They do not enforce every format semantic or decode pixels. Use a full image decoder when those additional checks are required.

The CLI reports store presence separately from signature or content-binding validation. A store with an invalid signature can still be a removal case. The [public fixture guide](../fixtures/c2pa/public/README.md) records the independent validation and preservation controls. The separate [TrustMark study](../experiments/trustmark-v1/README.md) measures one fixed pixel watermark that remains after store removal.

## Reports

JSON follows [`declawd.report/v1`](../spec/report-v1.md). An artifact contains its media type, byte length and SHA-256, without a disk path. Source context is absent by default. `--include-context` can disclose up to 32 source scalars on each side of a finding, so use it only when that content belongs in the report.

| Exit | Meaning |
|---|---|
| `0` | Inspection found no supported carrier, or cleaning completed |
| `1` | Inspection found a supported carrier |
| `2` | Usage or input failure |
| `3` | Post-transform verification failure |

Use `--exit-zero` when an inspection finding should not stop a shell pipeline. An empty result covers only the channels the tool inspected.

## Integration

A single hyphen selects standard input. The text limit is counted as bytes arrive, with refusal at the first byte above 10 MiB:

```sh
git show :docs/page.md | declawd inspect - --exit-zero
pbpaste | declawd inspect - --json --exit-zero
declawd inspect docs/page.md --sarif --exit-zero > page.sarif
```

SARIF 2.1.0 uses the scanned path as a percent-encoded URI reference. `--sarif-uri` requires `--sarif` and supplies an already encoded alternative URI. Text columns count Unicode code points and exclude a leading BOM. Image findings identify the artifact because store length alone does not locate it within its container.

Untested channels appear as `notApplicable` results and invocation notifications. Findings use `kind: review` and `level: none`. Some viewers omit these informational entries, so read the raw SARIF and workflow summary alongside any dashboard. The [SARIF standard](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) defines those fields.

[CI examples](../examples/ci/) include a GitHub Actions workflow, a helper that combines changed-file reports and a hook for staged content. Copy the workflow into `.github/workflows/` and `inspect-changed.py` into `.github/scripts/`. Enable code scanning for uploads. The example retains the full report as an artifact, skips uploads when no text files change and rejects binary content with a text suffix.
