# Security policy

Please report security vulnerabilities privately through GitHub's security
advisory feature for `san-digital/declawd`. Do not open a public issue for a
vulnerability that could expose a user's content or filesystem.

The CLI performs no network requests and never follows remote C2PA references.
Inputs are size-limited, existing outputs are refused, and successful writes
are verified before an atomic rename. Treat untrusted files as hostile and keep
the CLI updated.

The final input file entry is opened with operating-system no-follow semantics,
then checked on the same handle before reading. Symbolic links and Windows
reparse points are refused. Parent-directory links remain subject to ordinary
operating-system path resolution.

SynthID traces use the same no-follow input boundary, are limited to 8 MiB and
100,000 non-negative i32 token IDs, and reject unknown JSON fields. The lab
does not accept prose, make network requests, load production keys or expose a
detector threshold.

## Advisory exceptions

Reassessed on 29 October 2026. The pinned `c2pa 0.90.22` selects `rsa 0.9.10`, `crypto-bigint 0.5.5` through `elliptic-curve`, and `zip 8.6.0`. RustSec reports five vulnerabilities in those dependencies. The exceptions below concern operations outside this CLI's current code paths. The packages remain affected.

| Advisory | Affected operation | Current scope |
|---|---|---|
| [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) | Timing leakage from RSA private-key operations | The CLI loads no private keys and does not sign or decrypt |
| [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html) | Timing variability in cryptographic arithmetic on secret integers | The CLI performs no cryptographic operation on secret integers |
| [RUSTSEC-2026-0367](https://rustsec.org/advisories/RUSTSEC-2026-0367.html) | Privileged Unix permissions retained during ZIP extraction | The CLI accepts PNG/JPEG for C2PA operations and extracts no ZIP archives |
| [RUSTSEC-2026-0368](https://rustsec.org/advisories/RUSTSEC-2026-0368.html) | ZIP extraction creates links to targets outside the destination | The CLI extracts no ZIP archives and creates no archive links |
| [RUSTSEC-2026-0369](https://rustsec.org/advisories/RUSTSEC-2026-0369.html) | ZIP extraction applies permissions through unconfined links | The CLI extracts no ZIP archives and applies no archive permissions |

`src/artifact.rs` imports the SDK error type and calls only `jumbf_io::load_jumbf_from_memory` and `jumbf_io::remove_jumbf_from_file`. Both resolve to asset I/O handlers. The input kind and temporary-file extension restrict these calls to the PNG/JPEG handlers. They read or remove the embedded store without validating signatures, loading keys or using ZIP extraction. The signing code in the SDK's `jumbf_io` module is test-only. A source inspection found no ZIP extraction call in the SDK paths used here.

The RSA advisory still has no patched release. The arithmetic advisory requires `crypto-bigint >=0.7.6`, while the pinned SDK's elliptic-curve dependencies select 0.5.5. The ZIP advisories require `zip >=9.0.0`. The current SDK release, 0.91.7, selects ZIP 9.0.4 but requires Rust 1.96.0, above this crate's declared Rust 1.88 minimum. That SDK upgrade needs a separate compatibility review. Removing the cryptographic backend is not supported by the pinned SDK, which requires either its OpenSSL or Rust native backend at compile time.

These five exceptions expire on 28 November 2026. `scripts/check-security-advisories.sh` checks the four reviewed package versions and a SHA-256 digest of all Rust files under `src/` before applying the exact advisory IDs. A source or package change requires reassessment. CI fails after expiry and on any other vulnerability, and warns during the final fourteen days. Recheck the advisory database, dependency paths, source calls and available SDK/toolchain options before renewing. Remove an exception when its affected dependency can be removed or patched.
