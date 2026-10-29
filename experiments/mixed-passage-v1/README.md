# Mixed passages

Searching more windows raised the number of human documents flagged by this controlled scheme. At the whole-document cut-off, the window search flagged 19 of 24 human evaluation documents in the longest group. Calibrating the maximum over the search separately reduced that count to 1 of 24. The adjusted search also missed most marked insertions. All outcomes from the registered key are retained.

The two cut-offs are **1.65** for the whole document and **3.40** for the window maximum. Each produced zero crossings among the 24 calibration documents at each registered length. Both methods exceeded the registered 2 per cent target in at least one evaluation length group. These small samples and the shared authors limit what those rates say about other writing.

## Human controls

Each cell counts documents flagged after the complete scoring procedure. There are 24 evaluation backgrounds per length, from eight authors. The three rows reuse prefixes of the same backgrounds.

| Background tokens | Documents | Whole document | Adjusted search | Uncorrected search |
|---|---:|---:|---:|---:|
| 128 | 24 | 2 | 0 | 3 |
| 384 | 24 | 1 | 0 | 11 |
| 768 | 24 | 4 | 1 | 19 |

The uncorrected search applies the whole-document cut-off of 1.65 to the highest window score. The adjusted search uses its own cut-off of 3.40, selected on human calibration documents after searching every window. It gives one verdict per document. Counts from individual windows are not the false-positive denominator.

The observed 1 of 24 at 768 tokens is 4.17 per cent, above the registered target. No threshold was changed after this result. The whole-document method exceeded the target at all three evaluation lengths.

## Insertions

The marked passage prefers candidates selected by the new key in a frozen language template. Its first 64, 128 and 256 tokens were inserted at the start, middle and end of each human background. Each row therefore contains 72 mixtures: 24 backgrounds multiplied by three positions.

| Background tokens | Inserted tokens | Mixtures | Whole document | Adjusted search | Uncorrected search | Located |
|---|---:|---:|---:|---:|---:|---:|
| 128 | 64 | 72 | 9 | 2 | 44 | 0 |
| 128 | 128 | 72 | 30 | 2 | 72 | 2 |
| 128 | 256 | 72 | 9 | 1 | 72 | 0 |
| 384 | 64 | 72 | 10 | 1 | 56 | 0 |
| 384 | 128 | 72 | 22 | 2 | 72 | 2 |
| 384 | 256 | 72 | 9 | 0 | 72 | 0 |
| 768 | 64 | 72 | 12 | 4 | 65 | 0 |
| 768 | 128 | 72 | 12 | 4 | 72 | 2 |
| 768 | 256 | 72 | 12 | 3 | 72 | 0 |

Across these dependent cases, the whole-document method flagged 125 of 648 mixtures, the adjusted search flagged 19 and the uncorrected search flagged 597. Six adjusted search results met the registered location rule: a detected winning window with intersection over union of at least 0.5 against the known insertion span. Thirteen adjusted detections did not locate the insertion under that rule. A high score somewhere in a mixed document can come from its human background or a boundary between the two sources.

The same 648 insertion cases were also run with a neutral template output that takes the first candidate in every slot. The whole-document method flagged 66, the adjusted search flagged nine and the uncorrected search flagged 369. The neutral template is authored experimental material and is reported separately from the historical human controls.

## Mark strength

The registered marking procedure creates a preference, with no requirement that every resulting prefix cross a detection cut-off. These are the whole-passage scores of the isolated inserted prefixes, before mixing. Values are rounded for display only.

| Inserted tokens | Marked score | Neutral score |
|---|---:|---:|
| 64 | 1.405 | 0.813 |
| 128 | 2.382 | 1.382 |
| 256 | 1.142 | 0.114 |

The 256-token prefix scored below the 128-token prefix. Adding text does not ensure a stronger score for this fixed template and key. All three isolated marked prefix scores were below the adjusted search cut-off. The weak signal and stricter cut-off help explain the low detection count, although a window inside a prefix can score differently from its complete span. This run establishes no improvement in detection from the adjusted search.

## Setup

The [plan](PLAN.md), [configuration](config.json), [corpus](corpus.json), implementation and tests were registered before a key existed. The [registration](registration.json) pins those files and the two source fixtures by SHA-256. The 192 historical public-domain passages were grouped into 48 backgrounds, with four disjoint source passages per background. The existing author split supplies 24 calibration backgrounds and 24 evaluation backgrounds. Each background has 768 tokens, tested through prefixes of 128, 384 and 768 tokens.

This reuses the corpus and reviewed language template already examined for Declawd v1/v2. The new key, domain, minimum, window search and thresholds belong to this experiment. The original scorer contracts and evidence files retain their bytes. No language model or vendor detector was run.

The search uses widths of 64, 128 and 256 tokens, a stride of 16 and the final possible start for each width. Each span counts distinct adjacent word pairs within its own boundaries and requires 32 pairs. The scheme's nominal green fraction is one quarter. The score is `(4G - N) / sqrt(3N)`, used here as a descriptive statistic. The maximum is compared with the adjusted threshold once per document. Threshold decisions and ranking use exact integer comparisons.

The public commit sequence is registration `8aaa372`, key `5ad4d32` and calibration `eb81ac2`, followed by the evaluation evidence in this directory. The key was recorded once, and the runner refuses another draw. The calibration report was committed before evaluation. [Provenance](provenance.json) records full commit identities, runtime details and output hashes. This sequence documents the reported run, without proving that no earlier private key draw occurred.

## Reproduce

The runner uses the Python standard library. Run from the repository root:

```bash
python3 -B -m unittest discover -s experiments/mixed-passage-v1 -p 'test_*.py' -v
python3 experiments/mixed-passage-v1/experiment.py verify
python3 experiments/mixed-passage-v1/verify.py
```

Verification checks the registered inputs and key binding, recomputes all 72 calibration cases and 1,368 evaluation cases, and compares every saved output byte. The evaluation set contains 72 human controls, 648 marked mixtures and 648 neutral mixtures. The JSONL files preserve every searched window, including its raw counts. Human prefixes, insertion variants and shared authors are dependent observations. The reports include breakdowns by author and position, with no population confidence intervals.

The separate `verify.py` was written after the run. It reconstructs the documents and hashes pairs independently of the registered scoring functions, checks every window, uses rational arithmetic to check rankings and thresholds, and checks the committed input sequence and provenance hashes. Its Git checks require the registration, key and calibration commits to be available locally. Add `--fetch-history` to retrieve the recorded calibration commit and its ancestors from `origin` if a shallow clone or squash merge omitted them. CI uses that option. The registered runner's output verification needs no network.

| File | Contents |
|---|---|
| `seed.json` | Public key, draw time and registration identity |
| `calibration/report.json` | All calibration scores and the two frozen thresholds |
| `calibration/windows.jsonl` | Every calibration window |
| `run/evaluation.json` | All evaluation cases, summaries, isolated prefixes and generated text |
| `run/windows.jsonl` | Every evaluation window |
| `run/marked.txt` | Complete marked template output |
| `run/neutral.txt` | Complete neutral template output |
| `provenance.json` | Commit sequence, runtime and evidence hashes |

## Scope

These counts concern one key, one controlled template and a reused public-domain corpus. They give no performance result for Claude, ChatGPT, Gemini, TextSeal or another production watermark. Authorship decisions require other evidence.

The research references and implementation boundary are recorded in the [plan](PLAN.md). A different key, mark, corpus or search needs a separate registration. The observed misses and evaluation target failures remain part of this run.
