# Release 0.3.4

This release patches Rustix to 1.1.6 and updates C2PA to 0.92.1 with ZIP 9.5.1. It adds regression checks for truncated and oversized APP11 stores and updates crc32fast, img-parts and the release actions. The CLI command and report contracts remain unchanged.

## Security

Rustix no longer needs an advisory exception. The C2PA crypto dependency still selects RSA 0.9.10. RSA 0.10.0 is patched, but the upstream requirement has not migrated. The existing source and exact-version exception remains bounded to 28 November 2026. Read SECURITY.md for the reviewed operations and limits.

## Publication

Build and test the exact release commit with Rust 1.96. Verify the crate package, regenerated notices and both CycloneDX inventories. Publish the crate from the owner account, then create the matching v0.3.4 tag and verify all four platform archives, eight payload checksums and build attestations. Update the site download record only from those observed release assets. The registry and release assets must agree on their source commit.

## Evidence

Existing released snapshots and registered experiment bytes remain unchanged. Optional TrustMark experiments keep their own model and runtime records and are excluded from the crate package. The text null study stores its complete result as a compressed artifact, while the expanded local JSON is excluded from packaging.
