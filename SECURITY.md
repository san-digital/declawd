# Security policy

Please report security vulnerabilities privately through GitHub's security advisory feature for `san-digital/declawd`. Use that private route for vulnerabilities that could expose a user's content or filesystem.

The CLI makes no network requests and follows no remote C2PA references. It limits input sizes, refuses existing outputs and verifies successful writes before an atomic rename. Keep the CLI updated when handling untrusted files. The [file contract](docs/CLI.md#file-contract) records the limits and output behaviour.

The final input file entry is opened with operating-system no-follow semantics, then checked on the same handle before reading. Symbolic links and Windows reparse points are refused. Parent-directory links remain subject to ordinary operating-system path resolution.

SynthID traces use the same no-follow input boundary, are limited to 8 MiB and 100,000 non-negative i32 token IDs, and reject unknown JSON fields. The lab accepts token traces and uses no production keys or detector threshold.

## ZIP fix

The 0.3.3 release uses c2pa 0.91.8, ZIP 9.2.2 and typed-path 0.13.0, with Rust 1.96 as its minimum. [GHSA-m665-v7pm-7grj](https://github.com/advisories/GHSA-m665-v7pm-7grj) concerns disagreement between ZIP central-directory inspection and streaming extraction. Its first patched release was ZIP 9.0.5, selected by the preceding 29 October SDK update. That update also removed exceptions for three earlier ZIP advisories.

`scripts/check-security-advisories.sh` rejects every ZIP version below 9.0.5, prerelease versions and a missing ZIP dependency before invoking the audit. It checks all ZIP entries, including additional versions. This check covers the GitHub advisory while it is absent from the RustSec database. The dependency version is patched even though the CLI's PNG/JPEG operations use neither ZIP reader and provide no archive approval or extraction service.

Current source selects c2pa 0.92.1, ZIP 9.5.1 and c2pa_raw_crypto 0.3.0. Version 0.92.1 is a non-yanked crates.io release with a stable semantic version, while its GitHub release is labelled pre-release. The update tightens incomplete APP11 handling and retains the PNG/JPEG preservation tests. The SDK pin, software inventories and dependency notices use the locked versions. The ZIP guard retains 9.0.5 as its patched minimum.

The OpenSSL backend also removes `crypto-bigint` from the current lock. The preceding SDK update had selected 0.7.10, above the patched minimum 0.7.6 for [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html), and removed its exception.

## Rustix update

Reviewed on 13 November 2026. The lock selects `rustix 1.1.6`, which fixes [RUSTSEC-2026-0486](https://rustsec.org/advisories/RUSTSEC-2026-0486.html). Earlier 1.x releases can mark unwritten extended-attribute buffer bytes as initialised when the caller supplies a zero-length buffer. The affected API has not been shown to be reachable through Declawd. The package is updated without an advisory exception, and the dependency notices are regenerated from the lock.

## RSA removal

`c2pa 0.92.1` selects its OpenSSL API backend, with Rust OpenSSL configured to use OpenSSL 3.5 LTS. It contains no `rsa` crate. [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) identifies RSA 0.10.0 as patched, but the published C2PA Rust-crypto backend still requires 0.9.10. Selecting this backend removes that dependency without changing the CLI's PNG/JPEG inspection and removal operations.

Version 0.3.5 removed the Rust RSA dependency using AWS-LC. Version 0.3.6 selects OpenSSL LTS and retains that removal. A build check accepts stable OpenSSL 3.5 releases from 3.5.10 onwards, or the pinned 3.5.10-dev build with a matching source receipt and verified static library hashes. It rejects other development builds, older versions, other series and AWS-LC. The RustSec audit and GitHub dependency review have no RSA exclusions. The OSV reviewer blocks the advisory and every alias. The dependency guard rejects any reintroduced RSA version below 0.10.0, including prereleases, before invoking the audit.

Published release 0.3.4 retains its original Rust-crypto dependency and historical exception. A source merge does not change that crate or its binary archives. Its immutable release notes and dependency inventory remain the record for that version.

## Native backend

Release 0.3.6 statically links OpenSSL from the supported 3.5 LTS branch, pinned to official commit `84dda7853c130429210b37bee9e5b62366ca8bce`. Its source reports `3.5.10-dev`. The source archive hash, five November advisory fix commits and support date are recorded in [native/openssl-lts.json](native/openssl-lts.json). Each platform archive includes an `openssl-build.json` receipt with the target and static library hashes, plus OpenSSL's Apache-2.0 licence.

OpenSSL 3.5 is [supported until 8 April 2030](https://openssl-library.org/source/). The [10 November advisory](https://openssl-library.org/news/secadv/20261110.txt) publishes five fixes and schedules the next releases for 1 December. The pinned maintenance commit includes all five fixes. This is a build from that branch, rather than a claim that the scheduled 3.5.10 release already exists.

C2PA enables the vendored feature, leaving the openssl-src 300.6.1+3.6.3 Rust build helper in Cargo.lock. Source builds must set `OPENSSL_NO_VENDOR=1` to bypass it and select a patched OpenSSL installation. The release builder also sets `OPENSSL_STATIC=1`. The unused native 3.6 source is neither compiled nor linked. The inventory lists the selected native C source separately from that Rust helper. Cargo users are responsible for the provenance and updates of their selected LTS installation.

## OSV check

CI and releases run OSV-Scanner 2.7.0 against the full Cargo.lock. Its installer verifies the published binary's SHA-256. The inventory must match every locked package, including repeated names at different versions.

Scanner errors, malformed results, missing packages and unreviewed vulnerability records stop the check. An empty scanner configuration and disabled call analysis prevent exclusions or inferred reachability from hiding a dependency finding. CI retains raw results and the review summary. OSV receives locked package names and versions.

Pull requests also run GitHub dependency review, rejecting introduced high or critical advisories without an RSA allowance. The RustSec and OSV checks block unreviewed vulnerabilities at every severity.

OSV's imported [GHSA-qwgh-2vcv-g2f7 record](https://osv.dev/vulnerability/GHSA-qwgh-2vcv-g2f7) flags `block-buffer 0.10.4`. The [maintainer's advisory](https://github.com/RustCrypto/utils/security/advisories/GHSA-qwgh-2vcv-g2f7), updated on 27 October, specifies `>=0.11.0,<0.12.1`. Version 0.10.4 stores its cursor in a separate field outside the block passed to the compression callback.

The OSV check classifies only 0.10.4 with its reviewed crates.io checksum as outside that upstream affected range. Other versions, checksums and aliases require review. This exact package-range classification is reviewed separately through 28 November 2026 and becomes blocking after that date. The lock also contains patched `block-buffer 0.12.1`.

`RUSTSEC-2024-0370` is retained as an informational notice that `proc-macro-error 1.0.4` is unmaintained. The SDK selects it through the `static-regular-grammar 2.0.2` procedural macro used by `iref-core 3.2.2`, both directly through `iref 3.2.2` and through `static-iref 3.0.0`. It executes during compilation. The selected SDK still requires this dependency path. The notice adds no vulnerability exception. A changed classification or another advisory against that package stops the check.

## Python audit

The active Python runner closure was updated on 29 October to certifi 2026.10.23, filelock 4.2.4 and setuptools 84.1.0, with verified wheel hashes. Its direct model libraries, profile, source oracle and trace fixtures are unchanged. Earlier release tags preserve their original dependency locks. The Python audit checks every package in the current 40-package closure and permits no vulnerability exclusions.
