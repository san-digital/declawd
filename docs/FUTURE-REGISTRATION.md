# Future registration

Use `scripts/future_registration.py` to create a future experiment. The existing v1, r2 and v3 commands reproduce their recorded experiments. Their registered implementations, inputs, seeds and results retain their original bytes. The new tool has created no experimental registration or seed. Its tests use synthetic fixtures and mocked entropy.

## Literal counts

The recorded v3 preflight counted each literal segment separately. Adjacent literal fragments can split a token or apostrophe, so that calculation is not a general lower bound. A synthetic template passed it with a claimed 401 pairs and 201 control pairs, then produced 199 marked pairs with a test seed. Its scoring step failed after the draw. The committed v3 template has safe slot boundaries and a true guaranteed bound of 290, above its recorded conservative count of 286 and the required 201. Its recorded result remains valid.

The future tool coalesces adjacent literal strings before tokenising. It uses the exact `[A-Za-z]+(?:'[A-Za-z]+)?` scanner and ASCII folding. Every variable slot must have a separator at each neighbouring boundary, so an adjoining letter or apostrophe cannot change the literal tokens. The bound counts only distinct contexts inside the resulting literal runs, plus the initial empty context when the passage begins with a literal token. Those contexts survive every candidate choice. Registration requires at least one context above the profile's minimum, covering both sides of the eligibility boundary.

## Inputs

Give a future experiment an unused profile identifier and an `experiment.json` configuration. The template needs a non-empty, trimmed `fixture_id`. Its candidate review uses the exact sentence and paragraph review contract checked by `scripts/future_candidate_review.py`, including the single reviewed article-sound table and the ban on candidate slots after a/an. Corpus identifiers, author separation and eligibility in both splits are checked before registration.

This is an example configuration for future files, without a recorded draw:

```json
{
  "profile_id": "declawd-v4",
  "template": "fixtures/template-v4.json",
  "review": "fixtures/candidate-review-v4.json",
  "corpus": "fixtures/corpus.json",
  "minimum_effective_tokens": 200,
  "inputs": ["docs/PLAN-V4.md", "reference/run.py"],
  "registration": "fixtures/registration-v4.json",
  "seed": "fixtures/seed-v4.json",
  "outputs": ["fixtures/profile-v4.json", "reports/calibration.json", "reports/evaluation.json"]
}
```

Declare the complete plan, scoring procedure and other experimental inputs. The tool automatically includes the configuration, template, review, corpus, both guard modules and regression tests. Every path is relative to the experiment directory, while receipt hashes use repository-relative Git paths. The receipt records the derived domain, exact scanner, fixture identifier, guaranteed count, declared file hashes and input commit. Candidate grammar and operational meaning remain reviewed judgements.

## Sequence

Commit the complete future input set and guard files. Create the registration receipt, commit it separately, then record one seed and commit both its seed and attempt files before scoring:

```sh
python3 scripts/future_registration.py register experiments/future experiment.json
# Commit and preserve the registration receipt.
python3 scripts/future_registration.py sample experiments/future experiment.json
# Commit and preserve the complete seed and its .attempt.json record.
python3 scripts/future_registration.py verify experiments/future experiment.json
```

`sample` recomputes the preflight and requires the receipt, configuration, tool sources and all declared inputs to match their committed bytes. It checks the original input commit too. An exclusive, complete attempt record is published before entropy is requested. Existing registration, seed, attempt and output paths prevent another applicable creation step. If seed publication fails after the attempt record exists, a later call stops before requesting entropy. There is no automatic retry or marker-deletion command. Retain an incomplete attempt for review.

Preserve the registration, seed and output commits in an evidence branch or tag when publishing. After a squash publication, check out that preserved evidence branch or tag before running `verify`. Fetching its objects while staying on squashed main does not satisfy the required input-commit ancestry. `verify` needs the original Git objects and checks the seed against its first committed record. This is a record of the local procedure, without an independent witness or a guarantee against manual deletion and history replacement.

## Outputs

A future scorer must obtain its seed with `verified_seed(root, configuration)` and publish its complete declared output set through `write_outputs(root, configuration, documents)` from `scripts/future_registration.py`. Include the scorer in `inputs`. The helpers require a committed seed and attempt, reject changes to the first committed seed, and check every surviving output's registration, seed and seed-record binding before any replacement. Each supplied output must contain the verified binding. Writes publish complete temporary files atomically, allowing a partial set to be restored while preserving complete earlier files after an interrupted replacement.

The front door supplies registration, sampling and output guards. A future scoring procedure still needs its own review, registered decision rules and reproduction checks. Retain missed fixtures and false positives, and keep those results separate from the frozen v3 run. This tool supplies no production provider watermark or detector.

## Checks

Run `python3 -B -m unittest discover -s scripts -p 'test_future_registration.py' -v`. The regression cases cover split literal tokens, split apostrophes, every slot boundary, the previously accepted 401-versus-199 case, nested and staged Git paths, receipt and tool drift, profile reuse, attempt-before-entropy ordering, failed seed publication, seed commits, surviving output bindings and interrupted atomic replacement. Existing v3 and root reference tests remain separate.
