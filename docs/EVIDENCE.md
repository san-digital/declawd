# Evidence guide

The repository separates recorded experiments from current tool and workflow documentation. Registered inputs, seeds and results keep their original bytes. Reproduce a record using its existing seed. Future creation uses the [registration guard](FUTURE-REGISTRATION.md).

## Records

| Record | Purpose and retained result |
|---|---|
| [V1](../fixtures/registration-v1.json) | Original public-key word-pair example, including its candidate and length-floor defects. [Calibration](../reports/calibration-report-v1.json) and [evaluation](../reports/evaluation-report-v1.json) retain every result |
| [First v2 attempt](../experiments/declawd-v2-attempt-1/README.md) | Invalidated after two further candidate grammar errors, with results preserved |
| [R2](V2-RESULTS.md) | Active browser profile: marked 0.77 below 2.30, six crossings among 96 full evaluation passages |
| [R2 archive](../experiments/declawd-v2-r2/README.md) | Exact registered payload and its own scorer |
| [V3](../experiments/declawd-v3/README.md) | Separate workflow registration: marked 1.90 below 3.30, one crossing among 96 full evaluation passages |
| [Mixed passages](../experiments/mixed-passage-v1/README.md) | Adjusted search detected 19 of 648 marked mixtures and located six |
| [Window families](../experiments/window-family-v1/README.md) | Exact probabilities for all 4,096 weighted sequences in an independent finite null |
| [TrustMark](../experiments/trustmark-v1/README.md) | Ten of twelve payloads recovered before and after C2PA removal, with both misses retained |
| [SynthID](SYNTHID.md) | Integer-exact public-reference token scoring, with no detection decision |

The r2 and v3 human corpora were already public and examined in earlier work. Author splits separate calibration and evaluation, while overlapping prefixes and shared authors create dependent observations. Their measured rates describe these samples. The window-family probabilities concern a different, synthetic independent model. The TrustMark image set and matching model settings have their own scope.

## Reproduce

Run from a full repository checkout with Python 3.12 and `PYTHONSAFEPATH` unset. These commands check existing records without requesting entropy:

```sh
python3 reference/calibrate_v2.py reproduce
python3 experiments/declawd-v2-r2/reference/calibrate_v2.py reproduce
python3 experiments/declawd-v3/reference/calibrate_v3.py reproduce
python3 scripts/verify-v3-history.py --fetch-history
python3 experiments/mixed-passage-v1/experiment.py verify
python3 experiments/mixed-passage-v1/verify.py --fetch-history
python3 experiments/window-family-v1/experiment.py verify
python3 experiments/window-family-v1/verify.py --fetch-history
```

The three history verifiers need original Git objects, and their explicit `--fetch-history` options can retrieve missing recorded history from `origin`. The v3 checker pins `declawd-v3-evidence-2026-11-02` to its exact evidence commit so a squash merge does not substitute publication history for the original sequence. Numerical reproduction and original commit-order verification are separate checks.

The [TrustMark guide](../experiments/trustmark-v1/README.md#check) gives its retained-byte and pixel checks, runtime lock and optional model reproduction. A fresh inference run downloads model weights separately. The [C2PA fixture guide](../fixtures/c2pa/public/README.md) records container and independent-validator controls.

## V1 limits

The original fixture scored 2.99 against 1.80. Its six-substitution trace ended at 1.5256954942433834, with 358 effective contexts and 102 green contexts. Zero-width and confusable substitutions could be reversed byte for byte, while the bundled rewrite scored -0.04. The blind edit attempt remained above the cut-off at 2.61.

The registered two per cent evaluation target was missed: two of 96 human passages crossed (2.08 per cent, 95 per cent interval 0.57 to 7.28). Every measured passage had at least 200 distinct pairs, while the frozen engine issued verdicts from 120. At 120 pairs, four of the 192 passages crossed, including a Benjamin Franklin passage at 3.16. Interfaces using this historical profile should withhold scores and verdicts below 200 pairs.

Candidate slots 39 and 116 produce “due the delay” and “carry with a run” in the marked fixture. [Issue 17](https://github.com/san-digital/declawd/issues/17) records both the grammar and length-floor problems. R2 supplies separate calibration and candidate review while preserving v1 inputs. These frozen defects will not be corrected in place.

The v1 calibration command rewrites its recorded reports. Run it in a disposable checkout with the recorded seed, then confirm that the resulting bytes match Git:

```sh
python3 reference/calibrate.py --seed-hex 3af0a69fbe7c97fb6c73d2c96d7824d26782d36b6e5b6379eb0886382ce39164
git diff --exit-code -- fixtures reports
```

`calibrate.py` without that seed creates a new experiment. Corpus rebuilding also requires separately downloaded Project Gutenberg source texts. Ordinary tests and numeric reproduction use the committed corpus.

## Frozen boundaries

[Release source contracts](../release-manifest-v1.json), registration records and archive manifests bind their listed files by hash. This includes plans, normative specifications, some result documents and the first-attempt archive README. Those files remain historical records even when current wording or procedures improve.

The copied r2 result document has an inherited relative link that does not resolve in its nested archive layout. Use the [complete first-attempt archive](../experiments/declawd-v2-attempt-1/README.md) through this current index. The bound result document remains unchanged.

R2's truncated calibration report can prevent its registered `reproduce --write` recovery. Use the [recorded recovery instructions](V2-RESULTS.md#recovery) for that run. Its creation commands are archival. The current route for a new profile is the [future guard](FUTURE-REGISTRATION.md), whose receipt binds its code and checked inputs before one seed attempt.

V3's recorded template has 290 guaranteed literal contexts, above its recorded conservative bound of 286. Its old generic helper can overcount when adjacent literal fragments split tokens. The future guard coalesces literals, checks slot boundaries and rejects the recorded counterexample before registration or entropy. No additional experimental draw accompanied that correction.

The website keeps its active r2 and SynthID release pins separately from the current CLI release. An update to tool dependencies or current guides does not replace registered browser evidence. Complete misses, failed targets and invalidated attempts remain available alongside successful checks.
