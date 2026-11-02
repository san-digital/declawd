# Window families

This experiment measures the exact probability of at least one false alarm when several overlapping windows are tested in a finite independent null model. It compares an uncorrected per-window level with Bonferroni correction for each complete search family. It does not measure power, authorship, human writing, a language model or a provider watermark.

## Null

The input has twelve independent binary positions. Each position has mark probability one quarter. Enumerate every one of the 4,096 sequences once, in increasing binary order. A sequence with `g` marks has probability `(1/4)^g * (3/4)^(12-g)`. These probabilities differ between sequences. Sum them with exact rational arithmetic, and check that the total is one. No seed or random draw is used.

For each fixed window, count its marks and calculate the exact inclusive upper tail of `Binomial(width, 1/4)`. A decision rejects when `p <= threshold`. Every configured family gives one document-level false alarm if any of its windows rejects. Dependence from overlapping windows is retained by enumerating whole sequences.

## Families

- `document`: one window containing all twelve positions.
- `sliding`: width four at stride one.
- `dyadic`: widths two, four and eight, each at half its width as stride.

For every width, include the final possible start, remove duplicate intervals and preserve increasing width/start order. Record every interval and its count. The uncorrected threshold is `1/20` for every window. The Bonferroni threshold is `(1/20)/m`, where `m` counts every interval in that family. Correction is within each family, with no combined decision across the three families. Report both rules for every family regardless of whether an uncorrected rate exceeds the nominal level.

## Outputs

Save one JSONL row per binary sequence, with its exact probability and, for each family, the smallest window p-value and both decisions. Save a summary containing every interval, both exact family false-positive probabilities, the number of rejecting sequences and the total probability. Fractions contain integer numerators and denominators. Decimal displays are secondary to the fractions. Record runtime and output hashes in provenance.

The primary check is whether each Bonferroni family probability is at most `1/20`. This follows from valid fixed-window p-values and the union bound. Enumerated results can be conservative because the p-values are discrete and the windows overlap. Keep every outcome and the complete uncorrected comparison. No threshold, family or input probability is selected after computing outputs.

## Sequence

Commit and push this plan, configuration, runner, verifier, tests and registration before calculating the exhaustive outputs. The registration hashes these files and names the preceding Git commit. A permanent `window-family-v1-registration` tag preserves that commit through a possible squash merge. Send the registration commit for independent review before the run. Then execute the exhaustive run once and commit its outputs and provenance separately. Verification may recompute the same deterministic outputs.

The runner checks that the registration commit contains the registered bytes and is an ancestor of the checkout. The independent verifier uses a separate integer polynomial calculation for the binomial distribution and independently constructs the intervals, weights and decisions. Tests must detect uniform sequence weighting, a correction using only the number of widths, a correction multiplied by the family size and changed decisions. Tests of helper calculations before registration must not calculate the exhaustive family summaries.

## Scope

Independent mark positions make the binomial tails valid in this model. Real keyed token pairs can repeat and share context, and text can be selected or edited in ways absent here. This model establishes no binomial null for Declawd's existing word-pair scorer or for a production watermark. Bonferroni permits dependent tests when each fixed-window p-value is valid. Overlap alone does not invalidate that correction.

The family design is informed by [TextSeal2, section 3.4](https://arxiv.org/html/2610.40613v1#S3.SS4), which describes dyadic localisation and Bonferroni correction, and the earlier [TextSeal paper](https://arxiv.org/abs/2605.12456v2). Declawd's [mixed-passage experiment](../mixed-passage-v1/README.md) separately reports a measured window maximum on a reused human corpus. The experiments have different null models, scores, families and error targets. Their results must remain separate.

All inputs are synthetic. The Python standard library is sufficient. No third-party program, model, dataset, provider request or paid resource is used. The frozen v1/r2 files and earlier experiment records remain unchanged.
