# Third registration

This directory contains the successor to the r2 experiment workflow. It addresses the review and draw-safety findings in [issue 35](https://github.com/san-digital/declawd/issues/35), while the root r2 implementation, published evidence and [separate archive](../declawd-v2-r2/README.md) retain their exact bytes. The website continues to use its recorded r2 evidence until a separate reviewed integration changes it.

The [plan](docs/PLAN-V3.md) defines the `declawd-v3` profile and all decisions made before the draw. The [candidate review](fixtures/candidate-review-v3.json) includes every alternative in its sentence and full paragraph. The 192 human passages retain their published author split and their previous exposure in earlier studies, so the new evaluation is a result on a reused corpus.

## Procedure

Run `python3 -B -m unittest discover -s experiments/declawd-v3/reference -p 'test_*.py' -v` from the repository root before registration. Commit the complete registered inputs, then run `python3 experiments/declawd-v3/reference/calibrate_v3.py register` and commit its registration. Run `sample` once and commit the complete seed record before `reproduce --write` scores calibration and evaluation. `reproduce` checks the recorded outputs without writing or drawing. `python3 experiments/declawd-v3/verify.py` also checks their order and exact bytes in Git history.

The scorer derives the domain from the profile identifier and validates the entire profile before changing global parameters. Registration validates the template identifier and a seed-independent lower bound for the marked passage. Output recovery checks the seed binding in every surviving file before any write. Complete temporary files are published atomically so interruption can leave files absent, but cannot expose a partial replacement through this procedure.

## Scope

V3 supersedes the workflow for future educational runs. It does not change the r2 profile or establish a rate on unseen writing. The public seed and reviewed alternatives allow deliberate editing against this teaching scheme. No provider's production text watermark or private detector is measured here.
