# Optional SynthID runner notices

The token-only model runner and compatibility oracle are optional. They are not
linked into the Rust binary and their packages are not redistributed in release
archives. The reviewed 40-package Linux CPU closure, archive hashes, licences
and dependency edges are recorded in `reference/synthid-runner-lock-v1.json`
and the Python CycloneDX SBOM.

- `google-deepmind/synthid-text` 0.2.1 at commit `8f2e231`, Apache-2.0.
  Copyright 2024 DeepMind Technologies Limited. It is a frozen source and
  provenance reference, not an installed runner package.
- `transformers` 5.15.0, Apache-2.0. Copyright the Hugging Face team and
  contributors.
- `torch` 2.13.0+cpu. Copyright the PyTorch contributors. Its wheel records the
  combined SPDX expression reproduced in the lock and SBOM.
- `jax` and `jaxlib` 0.11.0, Apache-2.0. Copyright Google LLC.
- `safetensors` 0.8.0, Apache-2.0. Copyright the Hugging Face team and
  contributors.
- `immutabledict` 4.2.0, MIT. Copyright 2020 Corentin Garcia.

Torch 2.4.0 is retained only as the historical CPU sampling-table generation
provenance. Routine builds and release gates do not install it.

Model weights are not included. GPT-2 and Gemma each retain their own model
licence and access terms. The Gemma runner requires the caller to accept the
applicable terms and obtain access independently.
