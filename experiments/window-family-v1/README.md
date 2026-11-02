# Window families

The dyadic search has an exact false document alarm probability of `909559/16777216` (about 5.42 per cent) at an uncorrected five per cent per-window level. Correcting for its eighteen tested windows lowers that probability to `12619/16777216` (about 0.075 per cent). The single document and nine-window sliding search stay below five per cent under both rules.

The experiment enumerates every twelve-position independent Bernoulli sequence, with mark probability one quarter. It weights each sequence by its exact probability and records all 4,096 outcomes. The [plan](PLAN.md), [configuration](config.json), runner, independent verifier and tests were committed and pushed before the exhaustive run. No random seed or draw is used.

## Results

Each rule gives one document alarm if any window rejects. The probability column sums the exact Bernoulli weights of rejecting sequences. The count column is an enumeration count, rather than an equally weighted error rate.

| Family | Rule | Windows | Rejecting sequences | Exact probability |
|---|---|---:|---:|---|
| Document | Uncorrected | 1 | 1,586 | 119561/8388608 |
| Document | Bonferroni | 1 | 1,586 | 119561/8388608 |
| Sliding | Uncorrected | 9 | 1,224 | 14285/524288 |
| Sliding | Bonferroni | 9 | 1,224 | 14285/524288 |
| Dyadic | Uncorrected | 18 | 2,167 | 909559/16777216 |
| Dyadic | Bonferroni | 18 | 259 | 12619/16777216 |

The document uses width twelve. The sliding search uses width four at stride one. The dyadic search uses widths two, four and eight at half-length strides. Each schedule includes the final possible start. The corresponding Bonferroni thresholds are `1/20`, `1/180` and `1/360`.

The sliding result is unchanged by correction. Its width-four binomial tails have no attainable value between `1/180` and `1/20`, so both rules reject exactly when a window has four marks. Discreteness and overlap can make a correction conservative. These results do not show that every larger search exceeds its nominal level or that correction changes every decision.

## Sequence

The public registration commit is [`99a9ba57d0353ea11f4ba1d0bc5e63c2a526e151`](https://github.com/san-digital/declawd/commit/99a9ba57d0353ea11f4ba1d0bc5e63c2a526e151), preserved by the permanent `window-family-v1-registration` tag. It is based on `d3678e22c3d638bef046b69cdaefbe129534905d`. The exhaustive outputs and [provenance](provenance.json) were recorded separately after review of the registration. The complete [outcomes](run/outcomes.jsonl) and [summary](run/report.json) retain both rules for every family. Their probability weights sum to one.

## Reproduce

The Python standard library is sufficient. Run from the repository root:

```bash
python3 -B -m unittest discover -s experiments/window-family-v1 -p 'test_*.py' -v
python3 experiments/window-family-v1/experiment.py verify
python3 experiments/window-family-v1/verify.py --fetch-history
```

The runner checks the registered bytes and recalculates every outcome. The independent verifier constructs the binomial distribution by integer polynomial expansion, reconstructs the intervals separately and checks all weights, decisions and summaries. Its eight helper and fault tests include uniform weighting, counting widths instead of windows, multiplying the correction and changing decisions. The verifier can fetch the permanent registration tag when a shallow checkout lacks its history.

## Scope

These are exact probabilities for the registered finite null model. Independent binary mark positions make its fixed-window binomial p-values valid. Real token contexts and keyed word pairs can repeat or depend on each other, so the model establishes no error rate for human text, the existing Declawd scorer or a production watermark. It supplies no power or attribution result. Bonferroni permits dependent tests when each fixed-window p-value is valid.
