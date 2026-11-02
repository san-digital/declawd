# Contributing

Contributions should preserve the project's evidence and supported scope. Describe the exact carrier or contract you change, include the relevant tests and follow the [development checks](docs/DEVELOPMENT.md). The release workflow applies the full suite.

## Evidence

Registered inputs, seeds and outputs retain their bytes. Read the [evidence guide](docs/EVIDENCE.md#frozen-boundaries) before editing a scorer, fixture, specification or archived document. Future experiments use the [registration guard](docs/FUTURE-REGISTRATION.md).

Claims about a production watermark need reproducible ground truth from its provider. A public reference implementation alone does not establish compatibility with a provider's deployed method.

## Exact scoring

SynthID trace and score changes must agree exactly in Rust, browser BigInt and Python. Keep token-only input, integer contract fields and the existing boundary: no prose input, model logits, detector threshold or authorship verdict.

## Reports

Report vulnerabilities through the [private security route](SECURITY.md). Use ordinary issues for documentation errors, reproducible bugs and proposed changes, with the smallest relevant input that you are authorised to share.
