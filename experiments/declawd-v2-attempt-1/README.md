# Superseded attempt

This archive preserves the first v2 registration and its single sampled run from commit `77c1d6e9dfad7018491308e13ddd5a4a1b9d08e0`. Browser inspection after sampling found two candidate-review failures: "a empty field" and "a additional check". The candidate catalogue had approved both sentences. The original marked fixture contains both errors.

The run remains available with its original inputs, executable code, plan, seed and all five outputs. Its threshold was 1.65, the marked score was 2.94, and full-passage evaluation crossed twice in 96 passages. These values are retained as results of the invalidated candidate review. The archived results document is the contemporaneous report and should be read with this correction.

The successor has the distinct registration and profile identifier `declawd-v2-r2` and domain separator `declawd/v2-r2/green`. Its template removes the two candidate slots, its review checks a/an agreement against a finite authored vocabulary, and it receives one fresh seed after its own registration. Corpus, length groups and threshold policy remain the same. The correction was prompted by grammar in the rendered passage, after the first draw's results were known.

Reproduce this archived run with `python3 experiments/declawd-v2-attempt-1/reference/calibrate_v2.py reproduce` from the repository root. This command verifies the recorded bytes without sampling or writing.
