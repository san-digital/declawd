# Optional SynthID runner notices

The token-only model runner is optional. It is not linked into the Rust binary
and its packages are not redistributed in release archives. Its pinned runtime
inventory is recorded in the Python CycloneDX SBOM.

- `google-deepmind/synthid-text` 0.2.1, Apache-2.0. Copyright 2024 DeepMind
  Technologies Limited.
- `transformers` 4.43.3, Apache-2.0. Copyright the Hugging Face team and
  contributors.
- `torch` 2.4.0, BSD-3-Clause. Copyright the PyTorch contributors.
- `immutabledict` 4.2.0, Apache-2.0. Copyright Google LLC.

Model weights are not included. GPT-2 and Gemma each retain their own model
licence and access terms. The Gemma runner requires the caller to accept the
applicable terms and obtain access independently.
