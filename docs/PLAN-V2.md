# Second registration

Issue #17 records two defects in the frozen `declawd-v1` experiment: candidates that do not fit their sentence frames and a 120-pair verdict floor below the measured range. V2 keeps the original inputs, reports and vectors available and introduces `declawd-v2-r2` with its own domain separator, registration, seed record and outputs. The package version becomes 0.3.0.

The first `declawd-v2` attempt was registered and sampled before browser inspection exposed two further grammar errors: "a empty field" and "a additional check". Its complete inputs, executable code, seed and results remain in `experiments/declawd-v2-attempt-1`. This successor removes those candidate slots, adds a finite article-agreement check and has a new identifier and domain separator. Its corpus, length groups and threshold selection policy remain the same. The new seed follows a separately committed registration, and the first attempt's measured results remain available.

## Inputs

Review every candidate in every sentence frame before registration, including grammar and the operational instruction it gives. The review catalogue records each exact rendered variant and binds it to the template hash. A deterministic check verifies coverage and rejects changes to reviewed wording. It checks a/an agreement against a finite reviewed vocabulary and rejects an unknown follower until it has an explicit sound classification. Grammar beyond that rule and the meaning judgement are recorded as agent review.

Keep the existing author-separated corpus and disclose that it was already published and examined for v1. This is a new seeded experiment on a historical corpus, so its evaluation set is not newly collected or previously unseen. Keep the existing rewrite and perturbation rules as named historical inputs. No example is selected or rewritten after scores are known.

## Lengths

The minimum is 200 distinct token pairs. For each passage, take the shortest original-text prefix ending at a token that reaches 199, 200 or 201 distinct pairs, plus the full passage. If a passage cannot reach a length, report its exclusion from that group. Prefix selection counts pairs without consulting the seed. The 199-pair group checks that scores and verdicts are withheld. The other groups measure behaviour at and immediately above the floor as well as across full passages.

Choose the smallest threshold on the existing 0.05 grid from 0 to 19.95 for which the crossing rate is at most 2% in each eligible calibration group separately (200, 201 and full). Use the exact integer verdict comparison. Evaluation authors and the marked fixture have no part in choosing the threshold. Keep the result if the marked fixture misses it or evaluation exceeds 2%. Publish each length group separately, including exclusions, crossings and descriptive Wilson intervals. Prefixes share source passages and passages share authors, so the intervals are not population guarantees and groups are not pooled.

## Draw

Commit the implementation, reviewed template and plan before registration. `register` writes a new registration containing hashes of every input and executable used by the run. Commit that registration before `sample` can proceed. Sampling requires those files to match the committed bytes and records the commit, registration hash, UTC time and one 32-byte seed using exclusive file creation before any scoring. An existing seed or output prevents another draw. An interrupted run can reproduce its recorded seed. This documents a single draw within this checkout, while an independently witnessed randomness ceremony remains outside its claims.

## Outputs

Generate a profile, calibration report, evaluation report, scoring vectors and a controlled-removal vector. The controlled-removal rule is fixed before sampling: take at most six steps, each choosing the reviewed candidate substitution with the lowest resulting z among unused slots, break ties by slot and authored candidate order, and stop when no candidate lowers the score. Keep all steps whether or not they cross the threshold. This is a demonstration with the public seed and candidate table available.

Update the source-contract manifest to bind v2 evidence and implementation. Reproduce both versions and verify that every existing v1 fixture, report and vector has unchanged bytes. Add tests for registration tampering, duplicate draws, incomplete candidate review, length boundaries, author separation and calibration-only threshold selection.

## Website

Vendor the new run into the website with its exact source commit and hashes. Use v2 on the active demonstration, checker, cleaner and method pages. Historical v1 articles and reproduction bundles retain their original numbers and inputs. All displayed scores, crossings and edit counts come from the new outputs. The release check continues to distinguish a staged source commit from a published release, and publication follows review of the completed changes.
