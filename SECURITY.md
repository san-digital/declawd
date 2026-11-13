# Security policy

Please report security vulnerabilities privately through GitHub's security advisory feature for `san-digital/declawd`. Use that private route for vulnerabilities that could expose a user's content or filesystem.

The CLI makes no network requests and follows no remote C2PA references. It limits input sizes, refuses existing outputs and verifies successful writes before an atomic rename. Keep the CLI updated when handling untrusted files. The [file contract](docs/CLI.md#file-contract) records the limits and output behaviour.

The final input file entry is opened with operating-system no-follow semantics, then checked on the same handle before reading. Symbolic links and Windows reparse points are refused. Parent-directory links remain subject to ordinary operating-system path resolution.

SynthID traces use the same no-follow input boundary, are limited to 8 MiB and 100,000 non-negative i32 token IDs, and reject unknown JSON fields. The lab accepts token traces and uses no production keys or detector threshold.

## ZIP fix

The 0.3.3 release uses c2pa 0.91.8, ZIP 9.2.2 and typed-path 0.13.0, with Rust 1.96 as its minimum. [GHSA-m665-v7pm-7grj](https://github.com/advisories/GHSA-m665-v7pm-7grj) concerns disagreement between ZIP central-directory inspection and streaming extraction. Its first patched release was ZIP 9.0.5, selected by the preceding 29 October SDK update. That update also removed exceptions for three earlier ZIP advisories.

`scripts/check-security-advisories.sh` rejects every ZIP version below 9.0.5, prerelease versions and a missing ZIP dependency before invoking the audit. It checks all ZIP entries, including additional versions. This check covers the GitHub advisory while it is absent from the RustSec database. The dependency version is patched even though the CLI's PNG/JPEG operations use neither ZIP reader and provide no archive approval or extraction service.

The SDK pin, software inventories and dependency notices use the locked versions. The ZIP guard retains 9.0.5 as its patched minimum.

The SDK upgrade also selects `crypto-bigint 0.7.10`, above the patched minimum 0.7.6 for [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html). Its exception was removed too.

## Rustix update

Reviewed on 13 November 2026. The lock selects `rustix 1.1.6`, which fixes [RUSTSEC-2026-0486](https://rustsec.org/advisories/RUSTSEC-2026-0486.html). Earlier 1.x releases can mark unwritten extended-attribute buffer bytes as initialised when the caller supplies a zero-length buffer. The affected API has not been shown to be reachable through Declawd. The package is updated without an advisory exception, and the dependency notices are regenerated from the lock.

## RSA exception

Reassessed on 2 November 2026. `c2pa 0.91.8` selects `rsa 0.9.10` through `c2pa_raw_crypto 0.2.1`. [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) concerns timing leakage from RSA private-key operations and still has no patched release. The package remains affected. Declawd loads no private keys and does not sign or decrypt.

The reviewed call path is:

- `src/artifact.rs` imports the SDK error type and calls `jumbf_io::load_jumbf_from_memory` and `jumbf_io::remove_jumbf_from_file`.
- Both resolve to asset I/O handlers. The input kind and temporary-file extension restrict them to PNG/JPEG.
- Those handlers read or remove the embedded store without signature validation, ZIP extraction or private-key operations. The module's signing code is test-only.
- Default and network features are disabled. The enabled features are `file_io` and `rust_native_crypto`.

The exception expires on **28 November 2026**. Before applying it, the audit script checks the three reviewed SDK/RSA package versions and a SHA-256 digest of every Rust file under `src/`. Source or package changes require reassessment.

The audit fails after expiry and on any other RustSec vulnerability, with warnings during the final fourteen days. Renewal requires a fresh advisory, dependency-path, source-call and SDK-options review. Remove the exception when the affected dependency can be removed or patched.

## OSV check

CI and releases run OSV-Scanner 2.7.0 against the full Cargo.lock. Its installer verifies the published binary's SHA-256. The inventory must match every locked package, including repeated names at different versions.

Scanner errors, malformed results, missing packages and unreviewed vulnerability records stop the check. An empty scanner configuration and disabled call analysis prevent exclusions or inferred reachability from hiding a dependency finding. CI retains raw results and the review summary. OSV receives locked package names and versions.

The RSA advisory and its recorded aliases use the source, package and expiry guards above. Pull requests also run GitHub dependency review, rejecting introduced high or critical advisories with the same guarded RSA allowance.

OSV's imported [GHSA-qwgh-2vcv-g2f7 record](https://osv.dev/vulnerability/GHSA-qwgh-2vcv-g2f7) flags `block-buffer 0.10.4`. The [maintainer's advisory](https://github.com/RustCrypto/utils/security/advisories/GHSA-qwgh-2vcv-g2f7), updated on 27 October, specifies `>=0.11.0,<0.12.1`. Version 0.10.4 stores its cursor in a separate field outside the block passed to the compression callback.

The OSV check classifies only 0.10.4 with its reviewed crates.io checksum as outside that upstream affected range. Other versions, checksums and aliases require review. The shared guard sets reassessment for 28 November. The lock also contains patched `block-buffer 0.12.1`.

`RUSTSEC-2024-0370` is retained as an informational notice that `proc-macro-error 1.0.4` is unmaintained. The SDK selects it through the `static-regular-grammar 2.0.2` procedural macro used by `iref-core 3.2.2`, both directly through `iref 3.2.2` and through `static-iref 3.0.0`. It executes during compilation. The selected SDK still requires this dependency path. The notice adds no vulnerability exception. A changed classification or another advisory against that package stops the check.

## Python audit

The active Python runner closure was updated on 29 October to certifi 2026.10.23, filelock 4.2.4 and setuptools 84.1.0, with verified wheel hashes. Its direct model libraries, profile, source oracle and trace fixtures are unchanged. Earlier release tags preserve their original dependency locks. The Python audit checks every package in the current 40-package closure and permits no vulnerability exclusions.
