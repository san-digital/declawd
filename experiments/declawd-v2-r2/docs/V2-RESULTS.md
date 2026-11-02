# Recorded results

The active experiment is `declawd-v2-r2`. Its registration was committed at [`126fac944b86e1f154a0470a46697beca4b3dd74`](https://github.com/san-digital/declawd/commit/126fac944b86e1f154a0470a46697beca4b3dd74) and pushed before its one seed draw at `2026-09-25T05:42:52.095797+00:00`. The registered plan, candidate review and executable inputs are bound by SHA-256. The corrected template has 48 candidate slots and 111 rendered sentences. Each rendering carries grammar and meaning approvals. The review gives one rationale per slot, copied word for word from the first attempt's review, including for 15 renderings whose sentences changed in r2. Tests cover all 220 combinations within its sentences.

## Outcomes

Calibration selected a threshold of **2.30** using the smallest 0.05-grid value that meets the 2% target separately at 200 pairs, 201 pairs and full passage length. The marked fixture scores **0.77** over 378 distinct pairs, so it is **below threshold and missed**. The control scores **-0.62** over 377 distinct pairs. The full-passage evaluation has **6 crossings among 96 human passages (6.25%)**, exceeding the calibration target. These are the recorded outcomes, with no selection of a replacement seed or adjustment of the registered rules.

| Length | Calibration crossings | Evaluation crossings | Evaluation interval |
| --- | --- | --- | --- |
| 199 pairs | Verdict withheld for 96 passages | Verdict withheld for 96 passages | Not calculated |
| 200 pairs | 1/96 (1.04%) | 1/96 (1.04%) | 0.18% to 5.67% |
| 201 pairs | 1/95 (1.05%) | 1/94 (1.06%) | 0.19% to 5.78% |
| Full passage | 1/96 (1.04%) | 6/96 (6.25%) | 2.90% to 12.97% |

One calibration passage and two evaluation passages cannot reach 201 distinct pairs and are excluded from that group. The 199-pair group exposes pair counts but withholds green counts, scores and threshold verdicts. The minimum for an eligible verdict is 200 distinct pairs.

The intervals are descriptive 95% Wilson intervals. Prefixes share source passages and passages share authors, so observations are dependent and the groups are not pooled. The author-separated historical corpus was already published and examined for v1. This run does not establish a population false-positive rate or performance on unseen contemporary writing.

## Edits

The registered rule chooses up to six reviewed candidate substitutions using the public seed. All six steps lower the marked fixture's score, from 0.77 to -0.21, with 379 distinct pairs in the final text. The starting passage is already below threshold, so this run does not demonstrate edits changing a detected passage into an undetected passage. The vector retains the substitutions, intermediate scores and final text.

## First attempt

The earlier `declawd-v2` attempt is retained in full under [`experiments/declawd-v2-attempt-1`](../experiments/declawd-v2-attempt-1/README.md), including its executable code, registration, seed and measured outputs. Browser inspection after that draw exposed two grammar errors its review had approved: "a empty field" and "a additional check". Its threshold was 1.65 and its marked fixture scored 2.94. It is superseded for candidate validity, and those more favourable numbers have not been deleted.

R2 removes the two faulty candidate slots, adds a finite article-agreement check, fixes the plural readings and twelve-month wording, and uses its own registration and domain separator. V1 remains unchanged and reproduces with its original seed.

## Reproduce

```bash
python3 -B reference/calibrate_v2.py reproduce
python3 -B experiments/declawd-v2-attempt-1/reference/calibrate_v2.py reproduce
python3 -B -m unittest discover -s reference -p 'test_*.py'
```

Reproduction compares all five active output files byte for byte. `sample` refuses an existing seed or output. `reproduce --write` restores missing outputs from the recorded seed and refuses a seed record that differs from an existing calibration report.

## Recovery

A truncated `reports/calibration-report-v2.json` causes a JSON parsing error before `reproduce --write` can write any outputs. The registered code retains this limitation. For the published r2 run, restore both the seed record and calibration report from the [v0.3.0 release](https://github.com/san-digital/declawd/releases/tag/v0.3.0), then regenerate and compare the outputs:

```bash
git fetch origin tag v0.3.0
git restore --source=v0.3.0 -- fixtures/seed-v2.json reports/calibration-report-v2.json
python3 -B reference/calibrate_v2.py reproduce --write
python3 -B reference/calibrate_v2.py reproduce
```

These commands replace the two local files with their published bytes. In a source archive without Git metadata, copy both files from a fresh download of the same v0.3.0 source release before running the two Python commands. Keep the seed record and calibration report together, since the report binds the complete seed record. Deleting the report alone removes that comparison and could accept a changed seed. Recovery uses the published draw and does not call `sample`.

## Publication

Version 0.3.0 was published with v1, the superseded attempt and active r2 evidence in the source contract. The 0.3.1 patch adds test portability and recovery guidance, with every registered input and output unchanged. Website production verification checks its pinned, published source contract and retains the historical v1 articles and examples.
