# Declawd 0.3.6

Version 0.3.6 uses OpenSSL 3.5 LTS for C2PA's native backend. It retains the Rust RSA dependency removal from 0.3.5 and preserves the existing PNG/JPEG operations. Earlier releases retain their original bytes.

## LTS build

The four platform binaries statically link the official 3.5 maintenance source at `84dda7853c130429210b37bee9e5b62366ca8bce`. It reports `3.5.10-dev` and includes all five fixes in the [10 November OpenSSL advisory](https://openssl-library.org/news/secadv/20261110.txt). The next upstream releases are scheduled for 1 December. The [3.5 LTS support period](https://openssl-library.org/source/) runs to 8 April 2030.

Each archive includes `openssl-build.json`, identifying the source archive checksum, target, build options and static library hashes. The CycloneDX inventory lists the native OpenSSL source separately from the unused openssl-src Rust helper. The archives also include OpenSSL's Apache-2.0 licence.

## Source installs

Cargo installs now require an explicit patched OpenSSL 3.5 setup. Set `OPENSSL_NO_VENDOR=1` and `OPENSSL_DIR` to that installation. Set `OPENSSL_STATIC=1` for static linking. The [development guide](DEVELOPMENT.md#openssl-setup) has Unix and Windows commands and the pinned source builder. A build guard verifies the pinned development build against its receipt and library hashes. It also accepts stable 3.5 releases from 3.5.10 onwards, rejecting older versions, other series and AWS-LC.

## Checks

CI runs the Rust tests on Linux, macOS and Windows, compiles the Intel Mac target, verifies the crate package and inventories, and checks the full Rust and Python dependency locks. The c2patool comparison retains two signed fixtures and nine public or derived cases. The release workflow repeats validation and supplies checksums and GitHub provenance for all eight payloads.
