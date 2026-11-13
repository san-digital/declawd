# PNG continuation

The first run passed `--quality 95` to the Rust remover for every file. The CLI accepts that option only for JPEG, so all six PNG control removals and twelve PNG marked-file removals failed before inference. Preserve the complete first run and those eighteen command failures.

This continuation runs removal once on those eighteen frozen PNG inputs. It omits the JPEG-only option and performs no encoding, new payload assignment, image substitution or JPEG rerun. The inputs are the original six PNG controls and the twelve existing marked PNGs, each bound by hash before execution. All first-run decoder results and images retain their bytes.

## Registration

Commit this plan, `png_continuation.py`, its argument tests and `png-inputs.json`. Register their hashes, the first-run manifest, the original registration and runtime/model pins, and all eighteen source PNGs. Commit and push that receipt before loading models or running removal. Create a new exclusive attempt record and refuse existing continuation outputs. Retain every removal or decode error without retry.

## Method

Use the same patched Rust binary, Q remover, Python Q decoder, Rust decoder and runtime as the first run. Apply Rust removal at its published Q strength to PNG output with no quality option. Decode each result once with each decoder and retain the complete outcomes, hashes, dimensions, alpha presence, RGB mean squared error and PSNR against the frozen input. Exact-payload rules remain those in the original plan. Synthetic, matching-model and small-control limits still apply.

## Reporting

Keep the first-run failure count visible beside the completed continuation. Report removed-state results for the twelve JPEG trials from the first run and the twelve PNG trials from this continuation, retaining their input identities and procedure distinction. Do not replace first-run files or describe the continuation as a fresh encode experiment.
