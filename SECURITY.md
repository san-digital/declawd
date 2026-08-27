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

## Temporary advisory exception

`c2pa 0.90.15` selects `rsa 0.9.10` through its pinned `rust_native_crypto`
backend. That release is affected by `RUSTSEC-2023-0071`, a timing side channel
in RSA private-key operations for which no patched `rsa` release exists. This
CLI does not load private keys, sign, decrypt, expose a network service or call
RSA private-key operations. It uses the SDK's JUMBF inspection/removal API.

The exception is limited to `RUSTSEC-2023-0071` and expires on 12 September
2026. CI still fails on every other vulnerability, and it fails once the
exception expires. Reassess the `c2pa` pin and crypto backend before that date.
Remove the exception as soon as the dependency can be removed or patched.
