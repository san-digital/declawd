# Window families

This registered experiment enumerates every twelve-position independent Bernoulli sequence and calculates the exact probability of a false document alarm under three window searches. The [plan](PLAN.md) fixes the null, window schedules, thresholds, complete outputs and limits before the run. The [configuration](config.json) uses mark probability one quarter and nominal level one twentieth.

## Reproduce

The Python standard library is sufficient. Run from the repository root:

```bash
python3 -B -m unittest discover -s experiments/window-family-v1 -p 'test_*.py' -v
python3 experiments/window-family-v1/experiment.py verify
python3 experiments/window-family-v1/verify.py --fetch-history
```

The runner and independent verifier check the registered bytes and every sequence outcome. The verifier can fetch the permanent registration tag when a shallow checkout lacks its history. The result concerns a finite independent null model. It supplies no power estimate, human-corpus error rate or production-watermark result.
