# Null study

The registered synthetic run found no CountScan overclaim in 100 uniform-null documents or 100 marked documents. It detected at least one interval in 99 of the marked documents. These finite simulation counts supply no provider or natural-language guarantee.

| Condition | Documents | Count overclaims | Documents detected | Mean token FDP |
|---|---:|---:|---:|---:|
| Independent uniform null | 100 | 0 | 0 | 0 |
| Central marked segment | 100 | 0 | 99 | 0 |
| Repeated invalid null | 100 | 27 | 27 | 0.22 |

The repeated condition violates the conditional null assumption. Its 27 count overclaims and the token-weighted e-BH false discoveries are retained. A valid marginal pivot alone does not justify treating repeated evidence as fresh information.

## Corpus bounds

At 100,000 documents with a true null detection rate of 0.06, the lower bound assuming an exact 0.05 null falsely excluded the true zero origin share in all ten replicates. Using the independent calibration sample excluded it in none. Both procedures had zero false exclusions in the other three rate/size combinations, each with ten replicates. The calibration bound trades precision for protection against the declared null error.

This is a threshold-only illustration. It does not implement the prevalence paper's mechanism-specific upper bound or reproduce its model experiments. The block test implements BELL's token-weighted e-BH decision component with full fixed coverage, without its adaptive allocation. CountScan's count coverage and token-weighted FDR are different guarantees.

## Reproduce

Use Python 3.11 from the repository root:

```sh
python3 -m unittest discover -s experiments/text-null-v1 -p 'test_*.py'
python3 experiments/text-null-v1/verify.py
```

The verifier checks the registration and original input commit, recomputes the same fixed-seed run and compares all 624,000 interval rows, pivots, block decisions and 80 prevalence records. `results.json.gz` stores the complete 47,112,357-byte JSON result with deterministic gzip metadata. The expanded local `results.json` is ignored. The [plan](PLAN.md), [registration](registration.json) and original runner retain their committed bytes.
