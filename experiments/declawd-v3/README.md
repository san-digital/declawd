# Third registration

This records the separate `declawd-v3` experiment after the r2 review in [issue 35](https://github.com/san-digital/declawd/issues/35). The root r2 implementation, website evidence and [r2 archive](../declawd-v2-r2/README.md) retain their bytes. New experiments use the [current registration tool](../../docs/FUTURE-REGISTRATION.md).

## Outcome

The marked fixture scored **1.90**, below the selected **3.30** cut-off. One of 96 full evaluation passages crossed. The six-edit trace starts and ends below the cut-off. The [complete results](docs/RESULTS.md) retain the miss, all length groups and exclusions.

The 192 human passages and author split were already public and examined. These counts describe the reused corpus and this key. They supply no measurement of unseen writing or a provider's production detector.

## Check

Run from the repository root with Python 3.12 and `PYTHONSAFEPATH` unset:

```sh
python3 -B -m unittest discover -s experiments/declawd-v3/reference -p 'test_*.py' -v
python3 experiments/declawd-v3/reference/calibrate_v3.py reproduce
python3 scripts/verify-v3-history.py --fetch-history
```

The first two commands check the recorded numerical outputs without writing or drawing. The history checker pins the original evidence tag and verifies the committed sequence after a squash publication. The original registered verifier remains historical code. Creation commands in that frozen procedure describe its archived sequence.

## Recorded method

The [plan](docs/PLAN-V3.md) fixed decisions before the draw. [Candidate review](fixtures/candidate-review-v3.json) records every alternative in its sentence and paragraph. Profile loading validates parameters before changing globals, and the domain derives from the profile identifier. Recovery checks every surviving output's seed binding before atomic replacement.

The committed template has 290 guaranteed contexts, above its recorded conservative bound of 286. Its old generic length helper can overcount when a token crosses adjacent literal fragments. The current registration tool coalesces those fragments and checks slot boundaries before registration. The existing fixture, seed and results remain valid.
