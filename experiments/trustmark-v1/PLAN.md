# TrustMark plan

This experiment compares an embedded C2PA record with a TrustMark pixel watermark on twelve generated image files. It uses six generated scenes, each saved as PNG and JPEG, with a fixed payload for each file. The registration, source image hashes, runner, model hashes and Python wheel lock are committed before the first encoding attempt.

## Method

Use Adobe TrustMark revision `6df5a0a29b51cbec832695fdf02051a1937e37bd`, variant Q, BCH_4 encoding, a 68-bit payload, strength 1.0 and bilinear residual merging. Use CPU inference with one thread, deterministic PyTorch algorithms and seed `20261029`. Load the verified encoder and decoder with the weights-only loader. Model downloads are completed before inference, and the runner accepts only the recorded local model hashes. The optional detector, rotation search and watermark remover are disabled.

The input set contains a gradient, coloured tiles, deterministic noise, a drawn landscape, concentric circles in a portrait frame and a generated texture. The file generator and exact dimensions are in `experiment.py`. PNG compression is 9. JPEG quality is 95 with subsampling 0, without optimisation or progressive encoding. Payloads are the first 68 bits of SHA-256 over each case identifier. They are public test identifiers, with no claim of secrecy or authorship.

For each case, encode once, save the marked image, add a C2PA manifest with a `com.adobe.trustmark.Q` soft-binding assertion, then run Declawd's `clean c2pa`. Decode the original, marked, signed and cleaned images with the same model and settings. Retain every detection result, decoded payload and reported schema, including failures. A payload match requires a positive decoder result, all 68 expected bits and schema 2. Count detections in all twelve unmarked originals as controls.

Use `c2patool 0.27.12` as an independent oracle on all four states. Record store presence, content binding, claim signature and signing credential separately. The development certificate is outside public trust lists. Freeze the raw oracle output, Declawd's cleaning report, file hashes and decoded RGB hashes. Compare the cleaned file with the marked file byte for byte, and compare decoded pixels across signing and removal.

## Decision

Report counts for exact payload recovery in each state, detections in unmarked controls, byte identity after removal and pixel preservation. Retain each case in the denominator. There is one encoding attempt per case. Execution errors remain in the saved record. Changes to the image set, model, encoding settings or decoder search require another experiment registration.

## Limits

The result concerns these generated images and this matching decoder. Twelve unmarked controls do not establish a population false-positive rate. JPEG encoding changes pixels when the marked image is saved, so its effects remain separate from C2PA removal. The experiment measures TrustMark and supplies no result for SynthID, text watermarks or a vendor's production detector. Re-signing creates different C2PA identifiers and signatures, so a fresh run compares measured relationships and payload recovery rather than signed-file hashes.
