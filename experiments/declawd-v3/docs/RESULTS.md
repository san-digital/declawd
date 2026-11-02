# Third draw

The `declawd-v3` registration was committed as `075c2176a8795c3239557620b55bb4197c6d20ab` before one 32-byte draw on 2 November 2026 at 17:30:21 UTC. The complete seed record was committed as `64a9746` before scoring. The registration SHA-256 is `6ac84b6c39d7c1bf4d1a67b2e4184d11941e1f4a001e2c6446020f0a9fa45630`. No second draw was made.

## Outcomes

The registered calibration rule selected a threshold of 3.30. The marked fixture scored 1.90 across 380 distinct pairs, below the threshold, while the default control scored 0.33 across 377 pairs. The marked fixture was missed. These results are retained alongside all human-corpus outcomes.

| Group | Calibration crossings | Evaluation crossings | Unavailable prefixes |
|---|---|---|---|
| 199 pairs | insufficient text | insufficient text | 0 calibration, 0 evaluation |
| 200 pairs | 0/96 | 0/96 | 0 calibration, 0 evaluation |
| 201 pairs | 0/95 | 1/94 | 1 calibration, 2 evaluation |
| Full | 0/96 | 1/96 | 0 calibration, 0 evaluation |

Full evaluation crossed once in 96 passages (1.04 per cent). The threshold was computed from calibration authors and frozen by the registered algorithm before evaluation authors were scored in the same output-generation run. Calibration and evaluation were not separately committed stages. The corpus, author split and previous exposure are unchanged from the historical studies, so this proportion describes the reused corpus.

## Edits

The six registered candidate substitutions reduced the marked score from 1.8955164088290954 to 0.5345224838248488. Both endpoints were below 3.30. This is an edit trace with a declining score. It demonstrates no transition from a detected mark to an undetected mark. Each substitution and intermediate score is retained in `vectors/controlled-removal-v3.json`.

## Reproduction

Run `python3 experiments/declawd-v3/reference/calibrate_v3.py reproduce` to compare all five output files with their deterministic reconstruction. Run `python3 experiments/declawd-v3/verify.py` to verify the exact registered bytes, the first committed seed, and the later output commits. The 24 successor regression tests and 150 existing root reference tests passed before the draw. The separate r2 archive reproduced its exact historical outputs.

These results concern the public educational scheme. They measure no provider production watermark and establish no authorship, disciplinary or forensic conclusion.
