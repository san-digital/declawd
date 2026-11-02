# SynthID lab

The lab reproduces exact mean scoring for a fixed profile from DeepMind's public `synthid-text` 0.2.1 implementation. It accepts token IDs and returns exact fractions, 12-place decimals and hashes of the g-value and mask bitsets. The profile supplies no detector threshold or authorship verdict and is separate from production Claude or Gemini marking.

## Fixed traces

Run these commands from the repository root:

```sh
cargo run --locked -- lab synthid score fixtures/synthid/trace-prepared-v1.json --json
python3 reference/synthid_reference.py fixtures/synthid/trace-prepared-v1.json
```

The Rust and standard-library Python reports are byte-identical. Traces contain token IDs, an EOS ID and an optional expected result. They exclude prose, logits, floating-point probabilities and private keys. Input is limited to 8 MiB and 100,000 token IDs, with unknown JSON fields refused.

## Contracts

| Contract | Contents |
|---|---|
| [Profile](../spec/synthid-profile-v1.schema.json) | Public keys, hash arithmetic, CPU table and score representation |
| [Distribution](../spec/synthid-distribution-v1.schema.json) | Fixed, model-neutral candidate exercise for the browser lab |
| [Trace](../spec/synthid-trace-v1.schema.json) | Token IDs, EOS ID and optional expected result |
| [Score](../spec/synthid-score-v1.schema.json) | Exact scores and bitset digests without a decision |

The [normative specification](../spec/synthid-v1.md) and [three registered edits](../fixtures/synthid/registered-edits-v1.json) retain their original bytes. Each substitution records its independent score effect, without decoded model output or a decision rule.

The 65,536-bit CPU sampling table was generated once with Torch 2.4.0, packed LSB0 and pinned by SHA-256. Runtime code reads that table and does not regenerate it. The historical generation version is separate from the supported runner runtime.

## Model runners

The optional [runner](../reference/synthid_model_runner.py) produces token-only traces from pinned GPT-2 and Gemma 2B IT revisions. It allowlists concrete model classes, pins source revisions, requires safetensors and disables remote code. Model weights and decoded output are excluded from committed evidence.

GPT-2 is the ungated release oracle. Gemma needs separate licence acceptance, Hugging Face access and suitable hardware. Read the runner's help and [notices](../SYNTHID_THIRD_PARTY_NOTICES.md) before using either model.

The complete Linux CPU runtime is the [hash-pinned 40-package lock](../reference/synthid-runner-linux-cpu.lock). Its model libraries are Torch 2.13.0, Transformers 5.15.0, safetensors 0.8.0 and JAX 0.11.0. Torch 2.4.0 is historical table provenance and is not installed by the active runtime. The DeepMind 0.2.1 source is checked out at its immutable commit for compatibility checks, separately from its obsolete dependency pins.

## Reading results

The public reference warns that its hashing differs from production Gemini hashing and its trained detectors do not transfer. Anthropic's SynthID-Text attribution likewise supplies no production key, exact configuration, detector or decision rule for this lab. Exact reproduction of this public reference is evidence about its fixed contract.

The retained [version-of-record paper](../evidence/synthid/README.md) is CC BY 4.0 and pinned by DOI, length and SHA-256. The teaching implementation follows separately licensed Apache-2.0 source. Production keys and model weights are outside this repository.
