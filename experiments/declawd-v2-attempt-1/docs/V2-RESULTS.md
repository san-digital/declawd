# V2 results

The `declawd-v2` registration was committed and pushed at `d87977b989555f40da623675fd8053df8d120e1d` before the seed recorded at `2026-09-25T05:27:05.256083+00:00` was sampled. The draw used `secrets.token_bytes(32)` once. This is a documented sequence in the published history, with no independent witness to the randomness source.

## Candidate review

The replacement template has 50 varied slots and 115 candidate renderings. Each entry records an agent judgement of grammar and unchanged operational meaning, with the exact sentence and template SHA-256. The software verifies that the review covers every current candidate. Alternatives that changed calibration status, signatures, reporting dates or record destinations became fixed wording. The marked passage has 377 distinct pairs, and the control has 378.

## Measurements

The threshold is 1.65. It is the smallest point on the registered 0.05 grid meeting the 2% target separately for full calibration passages and their 200 and 201-pair prefixes. The marked passage scores 2.94, and the control scores 0.89. Neither fixture influenced the threshold.

| Group | Calibration crossings | Evaluation crossings | Evaluation rate | Descriptive 95% interval |
| --- | --- | --- | --- | --- |
| 200 pairs | 1/96 | 2/96 | 2.08% | 0.57% to 7.28% |
| 201 pairs | 1/95 | 2/94 | 2.13% | 0.59% to 7.43% |
| Full passage | 0/96 | 2/96 | 2.08% | 0.57% to 7.28% |

All 192 prefixes ending at 199 pairs return insufficient text, with public scores and green counts withheld. One calibration passage and two evaluation passages cannot reach 201 pairs and are counted as exclusions from that group.

The evaluation rates exceed the 2% calibration target. The target determines threshold selection on calibration authors only. These reported outcomes are retained without another draw or an adjusted threshold. The corpus and author split were already published and examined in v1. Length groups share source passages, and passages share authors, so the Wilson intervals describe this collection and do not establish a population false-positive rate or behaviour at every text length.

## Controlled changes

The registered procedure selects up to six changes from reviewed candidates using the public seed. It chooses the greatest available decrease in z at each step, breaking ties by slot and candidate order. All six changes were made in this run. The final passage has 378 distinct pairs, 108 green pairs and z = 1.6035674514745464, below the 1.65 threshold. Pair counts can change when a candidate changes, so each step is scored again.

## Reproduction

Run `python3 reference/calibrate_v2.py reproduce` to compare all five v2 outputs byte for byte. The command reads the recorded seed, verifies the registered source hashes and writes no files. `fixtures/seed-v2.json` binds the seed to the registration and commit. `reports/calibration-report-v2.json` binds the complete seed record, and `fixtures/profile-v2.json` binds the calibration report.

V1 fixture, registration, profile, corpus, rewrite, perturbation, report and vector bytes remain unchanged. Both profiles have regression coverage, including the original v1 vectors. Website adoption is prepared separately with a source commit pin. The website release check requires a published v0.3.0 source contract before deployment.
