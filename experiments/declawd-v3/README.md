# Third registration

This directory contains the successor to the r2 experiment workflow. It addresses the review and draw-safety findings in [issue 35](https://github.com/san-digital/declawd/issues/35), while the root r2 implementation, published evidence and [separate archive](../declawd-v2-r2/README.md) retain their exact bytes. The website continues to use its recorded r2 evidence until a separate reviewed integration changes it.

The [plan](docs/PLAN-V3.md) defines the `declawd-v3` profile and all decisions made before the draw. The [candidate review](fixtures/candidate-review-v3.json) includes every alternative in its sentence and full paragraph. The 192 human passages retain their published author split and their previous exposure in earlier studies, so the new evaluation is a result on a reused corpus.

## Procedure

Run `python3 -B -m unittest discover -s experiments/declawd-v3/reference -p 'test_*.py' -v` and `python3 experiments/declawd-v3/reference/calibrate_v3.py reproduce` from the repository root to check this recorded experiment without writing or drawing. `python3 scripts/verify-v3-history.py` checks the preserved registration, seed and output history after the publication merge. The original registered verifier remains available as historical code. Future experiment creation uses the [separate registration front door](../../docs/FUTURE-REGISTRATION.md). The old `register` and `sample` commands describe this archived sequence and are not the route for a new run.

The scorer derives the domain from the profile identifier and validates the entire profile before changing global parameters. This recorded template has a true guaranteed bound of 290 distinct contexts, above its recorded conservative count of 286. The old calculation treats literal segments separately and is not a general bound when a token crosses adjacent literal fragments. The future front door coalesces those fragments and requires safe boundaries around every slot before registration. Output recovery checks the seed binding in every surviving file before any write. Complete temporary files are published atomically so interruption can leave files absent, but cannot expose a partial replacement through this procedure.

## Scope

V3 records the workflow used for this historical experiment. It does not change the r2 profile or establish a rate on unseen writing. The public seed and reviewed alternatives allow deliberate editing against this teaching scheme. No provider's production text watermark or private detector is measured here.

The [recorded result](docs/RESULTS.md) retains the missed marked fixture: its score of 1.90 is below the selected 3.30 threshold. Full evaluation crossed once in 96 passages. The six-edit trace starts and ends below the threshold.
