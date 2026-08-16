# Declawd SynthID teaching contracts v1

These contracts reproduce exact mean scoring for one frozen profile derived
from `google-deepmind/synthid-text` 0.2.1. They do not reproduce Gemini or
Claude production keys, detectors or decision rules.

## Trace boundary

`declawd.synthid-trace/v1` accepts generated-output token IDs only. It rejects
unknown fields, so prose, logits, floating-point probabilities, private keys
and thresholds cannot be smuggled into the contract. Files are limited to
8 MiB, sequences to 100,000 IDs and every token ID to the non-negative i32
range. `profile.file_sha256` binds the trace to the exact committed profile.

`tokenizer.eos_token_id` may be null. If present, the first matching token is
the EOS boundary. Its index and every later final-token position are excluded.
The prompt is never part of the trace: `sequence_role` is always
`generated_output_only`.

## Hash and g values

For each five-token n-gram, start with signed i64 `h = 1`. For each token, and
then separately for each of the 30 keys, apply:

```text
h = (h + datum) * 6364136223846793005 + 1
```

Every addition and multiplication wraps in two's-complement i64. The sampling
table index is the Euclidean remainder modulo 65,536. The table is the
committed Torch 2.4.0 CPU bitset, not a runtime RNG.

G values are laid out row-major. Bit `position * 30 + depth` is the value for
candidate context `position` and key `depth`. All contract bitsets are packed
LSB0: logical bit `p` is byte `p / 8`, bit `p % 8`. Unused high bits in the
last byte are zero. A zero-bit vector hashes the zero-byte string, whose
SHA-256 is
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## Masks and counts

A candidate context exists for each n-gram final token, so its count is
`max(token_count - 4, 0)`. The repetition context is the preceding four token
IDs. Context hashes are compared with the previous 1,024 entries, including
the reference implementation's initial zero entries, then pushed into the
bounded history. `repetition` is one only for a context not found in that
history. `eos` is one only when the n-gram's final token is before the first
EOS. `valid = repetition & eos`.

Exclusion counts are the number of zero bits in each individual mask. They may
overlap. Score numerators use only rows whose valid bit is one.

## Exact scores

For `N` valid rows:

```text
raw       = sum(valid g bits) / (30 * N)
weighted  = sum(valid g[i] * (290 - 9*i)) / (4785 * N)
```

Fractions are deliberately unreduced. Decimal strings have exactly 12
fractional places and use round-half-to-even implemented with integers. When
`N = 0`, status is `insufficient_data` and both scores are null; NaN and
infinity are never emitted.

The optional trace `expected` object contains derived fields only. It excludes
trace identity and hashes to avoid a self-referential document. A mismatch is
a verification failure and exits 3. A null, malformed or schema-invalid
`expected` value is an input error and exits 2; only a structurally valid but
incorrect expected result can produce exit 3.

The report warnings are fixed identifiers:

- `public-reference-profile-only`
- `no-detector-threshold-or-authorship-verdict`

CLI and site copy provide their prose explanation.

## Fixed teaching distribution

`declawd.synthid-distribution/v1` is not a trace or model output. It defines
four model-neutral candidates whose positive integer masses share the explicit
denominator 1,000 and sum to it exactly. Each candidate has one g value at each
of the profile's 30 depths, derived from the same four-token context, candidate
token ID, keyed hash and committed sampling table.

The six fixed draws make the tournament rule inspectable. At a draw's stated
depth, compare the first and second candidate's keyed g value. The candidate
with the larger bit wins; equal bits retain the first draw. Candidate IDs and
token IDs are unique, draw depths are unique, every reference resolves, and
the committed winners are recomputed in both Rust and Python tests.

The distribution schema const-pins the entire teaching fixture. It cannot be
used to publish alternate candidate IDs, masses, g-values, draws or winners
under the v1 identity.

## Registered token edits

`declawd.synthid-registered-edits/v1` is a frozen vector, not an additional
input contract. It binds the prepared trace by SHA-256 and registers three
independent token-ID substitutions. Each entry identifies the original token
at its zero-based index and records the exact raw and weighted score after the
replacement, including signed numerator changes. Rust and Python recompute all
three effects. The vector contains no prose, threshold or verdict.

## Runtime and upstream oracle

Torch 2.4.0 on CPU is immutable sampling-table generation provenance only.
Routine gates never install it. The supported runner uses the reviewed,
hash-pinned Linux CPU closure rooted at Torch 2.13.0, Transformers 5.15.0,
safetensors 0.8.0 and JAX 0.11.0. Model classes and revisions are allowlisted,
remote code is disabled and only safetensors weights are loaded. GPT-2
reproduction enables deterministic Torch algorithms and uses one intra-op and
one inter-op CPU thread before byte-comparing the generated trace.

The release oracle checks out DeepMind 0.2.1 at its exact commit, detached and
clean. On the prepared trace it compares the maintained runtime with the pinned
source for every keyed g-value and the repetition, EOS and valid masks. It then
calls DeepMind's JAX `detector_mean.mean_score` and
`detector_mean.weighted_mean_score` and compares each with the exact rational
report within `1e-6`.
