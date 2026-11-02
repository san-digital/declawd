# Archived r2

This directory preserves the registered `declawd-v2-r2` payload from commit `0c1479a`. Every file listed in `archive-manifest.json` is an exact copy, including the scorer, procedure, plan, seed, reports and vectors. The nested first-attempt archive manifest is retained because the r2 registration binds it by hash.

Reproduce the archived outputs with `python3 experiments/declawd-v2-r2/reference/calibrate_v2.py reproduce`. The successor tests also verify every archive hash. The original root files remain unchanged, so existing browser evidence and source contracts continue to reproduce.

R2 recorded a threshold of 2.30, a marked-fixture score of 0.77 below that threshold, and six crossings in 96 full evaluation passages. Those outcomes retain their historical meaning. The v3 workflow addresses issue 35 in a separate registration and does not repair or replace these bytes.
