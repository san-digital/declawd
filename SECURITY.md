# Security policy

Please report security vulnerabilities privately through GitHub's security advisory feature for `san-digital/declawd`. Use that private route for vulnerabilities that could expose a user's content or filesystem.

The CLI performs no network requests and follows no remote C2PA references. Inputs have size limits, existing outputs are refused, and successful writes are verified before an atomic rename. Treat untrusted files as hostile and keep the CLI updated.

The final input file entry is opened with operating-system no-follow semantics, then checked on the same handle before reading. Symbolic links and Windows reparse points are refused. Parent-directory links remain subject to ordinary operating-system path resolution.

SynthID traces use the same no-follow input boundary, are limited to 8 MiB and 100,000 non-negative i32 token IDs, and reject unknown JSON fields. The lab accepts token traces and uses no production keys or detector threshold.

## ZIP fix

On 29 October 2026, the SDK was upgraded from `c2pa 0.90.22` to `0.91.7` and the Rust minimum raised to 1.96. The lock now selects `zip 9.0.5`, the first patched release for [GHSA-m665-v7pm-7grj](https://github.com/advisories/GHSA-m665-v7pm-7grj). The advisory concerns disagreement between ZIP central-directory inspection and streaming extraction. The upgrade also resolves the three earlier RustSec ZIP advisories, so their audit exceptions were removed.

`scripts/check-security-advisories.sh` rejects every ZIP version below 9.0.5, prerelease versions and a missing ZIP dependency before invoking the audit. It checks all ZIP entries, including additional versions. This check covers the GitHub advisory while it is absent from the RustSec database. The dependency version is patched even though the CLI's PNG/JPEG operations use neither ZIP reader and provide no archive approval or extraction service.

The SDK upgrade also selects `crypto-bigint 0.7.10`, above the patched minimum 0.7.6 for [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html). Its exception was removed too.

## RSA exception

Reassessed on 29 October 2026. `c2pa 0.91.7` selects `rsa 0.9.10` through `c2pa_raw_crypto 0.2.1`. [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) concerns timing leakage from RSA private-key operations and still has no patched release. The package remains affected. Declawd loads no private keys and does not sign or decrypt.

`src/artifact.rs` imports the SDK error type and calls only `jumbf_io::load_jumbf_from_memory` and `jumbf_io::remove_jumbf_from_file`. Both resolve to asset I/O handlers. The input kind and temporary-file extension restrict these calls to the PNG/JPEG handlers. They read or remove the embedded store without validating signatures or loading keys. The SDK's signing code in the `jumbf_io` module is test-only. The reviewed paths use no ZIP extraction or private-key operation. Default and network features remain disabled, with only `file_io` and `rust_native_crypto` enabled.

The RSA exception expires on 28 November 2026. The audit script checks the three reviewed SDK and RSA package versions and a SHA-256 digest of all Rust files under `src/` before applying this advisory ID. Source or package changes require reassessment. The audit fails after expiry and on any other RustSec vulnerability, and warns during the final fourteen days. Recheck the advisory, dependency path, source calls and available SDK options before renewing. Remove the exception when the affected dependency can be removed or patched.

## Python audit

The active Python runner closure was updated on 29 October to certifi 2026.10.23, filelock 4.2.4 and setuptools 84.1.0, with verified wheel hashes. Its direct model libraries, profile, source oracle and trace fixtures are unchanged. Earlier release tags preserve their original dependency locks. The Python audit checks every package in the current 40-package closure and permits no vulnerability exclusions.
