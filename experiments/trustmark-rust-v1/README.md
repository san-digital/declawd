# Rust comparison

The registered comparison uses twelve owned images, two Q encoders and two matching decoders. C2PA signing and removal preserved every decoder outcome and all 24 marked files byte for byte. The Rust pixel remover left zero exact-payload recoveries in the 24 marked outputs for either decoder, with the PNG procedure completed in a separately registered continuation.

| Encoder | Decoder | Marked | After C2PA signing | After C2PA removal | After pixel removal |
|---|---|---:|---:|---:|---:|
| Python | Python | 11/12 | 11/12 | 11/12 | 0/12 |
| Python | Rust | 10/12 | 10/12 | 10/12 | 0/12 |
| Rust | Python | 10/12 | 10/12 | 10/12 | 0/12 |
| Rust | Rust | 10/12 | 10/12 | 10/12 | 0/12 |

The unmarked source controls produced zero Python positive flags and one Rust positive flag in twelve images. A positive flag and recovery of the expected payload are different observations. These twelve controls supply no population false-positive estimate. The encoder and decoder differences are retained rather than treated as equivalent implementations.

## PNG failures

The first runner supplied a JPEG-only quality option to PNG removal. Six unmarked and twelve marked PNG removal commands failed before remover inference. Their full commands, errors and completed encode/decode states remain in `run/results.json` and `first-run-manifest.json`.

The [PNG continuation](PNG-PLAN.md) was committed, hash-registered and pushed after the first run was frozen. It removed from the same eighteen PNG files without re-encoding, replacing a payload or repeating a JPEG trial. All eighteen continuation operations completed without errors. The combined removed-state column uses twelve JPEG trials from the first run and twelve marked PNG trials from this continuation.

## Image changes

Pixel removal changed the images. RGB PSNR against the marked input ranged from 42.58 to 51.68 dB across the 24 marked outputs. File hashes, pixel hashes, dimensions, alpha presence, mean squared error, PSNR and complete decoder outputs remain in the result files. The range describes this set and supplies no perceptual-quality guarantee.

The result concerns matching Q models and public test payloads. Zero exact recovery does not establish absence of an arbitrary watermark or performance against a production provider. The earlier `trustmark-v1` result remains ten of twelve exact recoveries before and after C2PA removal, with its two misses and bytes unchanged.

## Runtime review

The pre-inference advisory check found affected Rustix and TLS dependencies in the upstream lock. The recorded experiment lock updates Rustix to 1.1.6, rustls to 0.23.46, rustls-webpki to 0.103.17 and both current webpki root packages to 1.0.12. The 316-package Rust/Python query then retained only the informational paste maintenance notice. Both scans and both locks are preserved. This is upstream code at the pinned revision with an explicitly patched dependency lock.

## Verify

Use the preserved evidence tag after a squash merge, with Python 3.12 and the verifier requirements installed:

```sh
git worktree add --detach /tmp/declawd-trustmark-rust-evidence declawd-trustmark-rust-v1-20261113
python3 -m pip install -r /tmp/declawd-trustmark-rust-evidence/experiments/trustmark-rust-v1/verifier-requirements.txt
python3 /tmp/declawd-trustmark-rust-evidence/experiments/trustmark-rust-v1/verify.py
```

The verifier checks both input registrations and their original commits, every first-run file hash, decoded RGB hashes, exact-payload classifications, signed oracle controls, metadata preservation, continuation inputs and the derived summary. It uses retained outcomes and performs no model inference or new draw. The complete inference runtime, model hashes and source identity are in `runtime.json`, `models.json` and the two plans. The private signing key and downloaded models are excluded.
