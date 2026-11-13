# TrustMark comparison

This separate registration compares Adobe's Rust 0.5.0 and Python Q encoders and matching decoders, then measures the explicit Rust pixel remover. The earlier TrustMark experiment retains its twelve cases, ten recoveries and two misses unchanged.

## Inputs

Use upstream revision 4c60b9fdb4125fca3001f0803e6890a6b55371ac. Its Rust dependency lock is updated before inference for the advisory findings recorded here. Preserve both locks and both advisory scans. The patched 316-package Rust/Python inventory has no vulnerability finding and retains paste 1.0.15 as an informational maintenance notice. Code and downloaded model files have the upstream MIT terms, copied with attribution.

Use all twelve owned original images from `trustmark-v1`, with their existing hashes. Assign each a new public 68-bit payload from SHA-256 over `trustmark-rust-v1:` plus its identifier. Use Q, BCH_4/schema 2, strength 0.95 and the Python bilinear merge. The upstream Rust CLI fixes encoding strength at 0.95. Retain PNG and JPEG as separate formats. Python JPEG uses quality 95 and no subsampling. Rust JPEG uses its image crate's quality-95 encoder. Differences between file encoders are part of the comparison.

Use the recorded Python 3.12 arm64 wheel lock, CPU, one PyTorch thread, deterministic algorithms and seed 20261113. Rust uses the upstream ORT configuration, including its thread settings. Pin all six model weights/configuration files and the Rust, Declawd and c2patool binaries by hash before execution. Verify local model files and disable automatic model downloads in the Python loader. No production provider detector is called.

## Sequence

Commit the complete plan, runner, case list, model hashes, dependency locks and advisory review. Create and commit a hash registration, then push it before the first encode or decode. Create one exclusive attempt record before loading the inference model. Refuse an existing attempt or output directory. There is one encode per implementation and image. Retain every error rather than replacing a case or retrying an encode.

Decode each original and each original after Rust removal as unmarked controls. Encode every input once with Python and once with Rust. For each marked file, record the marked state, add an owned test C2PA manifest, remove only that store with the proposed SDK CLI and separately run the Rust pixel remover on the marked state. Decode all states with both decoders. Record Python payload, detection and schema, the complete Rust decoder output and exact expected-payload equality. A Python match requires detected=true, schema 2 and all expected bits. A Rust match requires the exact `Found watermark:` output payload.

Use c2patool 0.27.12 on the signed and cleaned states, retaining its raw output and exit status. The signing certificate is an owned self-signed development credential outside public trust lists. It supplies no public identity claim. Record the binary and source identity of Declawd separately from the upstream TrustMark revision.

## Measurements

Retain all file and decoded RGB hashes, dimensions, alpha presence, decoder outcomes and failures. Compare signed and cleaned pixels with their marked input and cleaned bytes with the marked bytes. Compute RGB mean squared error and PSNR for marked output against its original and removed output against its marked input. Record unmarked removal distortion too. Count all twelve source controls and all 24 encoder trials, including missed payloads and execution errors. A pixel remover can change an image while leaving the watermark detectable.

## Limits

These generated images, Q models, payloads and matching decoders supply no result for another watermark, a provider production key or natural images in general. The small unmarked set supplies no population false-positive rate. Rust and Python resizing, inference and file encoding can differ. The experiment measures the pinned implementations, without assuming byte parity or equivalent detection rates. Certificate creation and ECDSA signing are randomised, so verification checks retained bytes and measured relationships rather than recreating signatures.
