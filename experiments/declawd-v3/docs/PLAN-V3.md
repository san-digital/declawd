# Third registration

This experiment supersedes the r2 registration workflow after issue 35 identified weaknesses in candidate review, preflight checks, output recovery and profile loading. The root r2 files and the first v2 attempt retain their original bytes. `experiments/declawd-v2-r2` holds a separate exact r2 payload with its own scorer and archive manifest.

## Inputs

The profile identifier is `declawd-v3`, with its domain derived as `declawd/v3/green`. The tokeniser, gamma of one quarter, minimum of 200 distinct token pairs, corpus, rewrite and perturbation inputs retain their r2 definitions. The 192 human passages were previously published and inspected in v1, r2 and the mixed-passage study. Their author split remains fixed. This is a new registered teaching fixture using a reused historical corpus, so the evaluation results do not provide independent confirmation on unseen writing or a population error rate.

The template fixes the adjective following “A” as “small”, and fixes “band” where later sentences refer to that band. Candidate review records each alternative in its full sentence and paragraph, with the other slots at their default choices. Each entry records grammar and unchanged-instruction approval with a rationale. The validator checks exact coverage and context, captures every non-whitespace follower after a/an against one reviewed sound table, and rejects candidate slots immediately after an indefinite article. Those checks support a manual review of wording and operational meaning. They do not prove all possible combinations equivalent.

Before registration, check the template identifier and a lower bound of at least 201 distinct pairs formed entirely inside literal segments. Those pairs survive every candidate choice, so the marked passage covers the registered 199, 200 and 201 boundaries for every possible seed. Check corpus identifiers, split names, author separation, eligible lengths and the candidate review before any draw.

## Sequence

Commit the complete plan, inputs, template review, scorer, protocol and regression tests. Run `register`, which verifies that these bytes are committed and records their hashes. Commit the registration separately. Run `sample` once to draw 32 bytes and publish a complete seed record atomically without scoring. Commit that record before generating outputs. No second draw is permitted. A failed or disappointing outcome remains part of this registration.

Generation uses the first green candidate in authored order, or the default when no candidate is green. Calibration uses the historical calibration authors at prefix lengths of 200 and 201 distinct pairs and at full length. Select the lowest threshold on the 0.05 grid from 0 to 19.95 with at most two per cent crossings in every eligible calibration group. Freeze that threshold before scoring evaluation authors. Report unavailable lengths, the 199-pair insufficient-text group, all marked/control outcomes, evaluation crossings and author counts. Wilson intervals describe this corpus, whose passages share authors and whose length groups share passages.

## Recovery

Every output records the registration hash, seed and seed-record hash. Before computing results or repairing files, compare those values in every surviving output, including the profile and vectors. Missing calibration output does not weaken that check. A mismatch stops the run before any output write. Reproduction with writes requires the seed and registered inputs to be committed.

Publish each output through a complete temporary file, flush and synchronise it, then atomically replace its destination. An interrupted replacement preserves the earlier complete destination or leaves the destination absent. The same temporary-file procedure publishes a registration or seed with an exclusive link so an existing record cannot be replaced. An output set interrupted between files can be completed from the committed seed. A machine failure after entropy is drawn but before a complete seed is published remains a limitation of a local procedure without an independent witness.

## Outputs

Generate a profile, calibration report, evaluation report, scoring vectors and a controlled-removal vector. The removal procedure retains r2's six-step maximum, lowest-score choice among unused reviewed slots, authored tie order and stop on no strict reduction. Retain each step whether or not detection crosses the threshold. The seed and candidate table are public. These outputs describe the registered educational scheme and give no measurement of a provider's production watermark.

## Checks

Register the regression tests alongside the procedure. Cover non-letter article followers, variable slots after articles, complete paragraph review, the band wording, template identifiers, the literal-pair lower bound, nested Git paths and staged changes, single-draw ordering, seed checks with every surviving output, interrupted writes, complete profile validation without partial global mutation and domains derived from profile identifiers. Reproduce the archived r2 outputs and verify every archived hash. Run the existing root reference tests to confirm that the published r2 workflow still reproduces. `verify.py` checks exact bytes and separate registration, seed and output commits, then reproduces the recorded outputs.
