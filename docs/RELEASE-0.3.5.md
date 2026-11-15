# Release 0.3.5

This release removes the vulnerable Rust RSA dependency by selecting C2PA's supported vendored OpenSSL backend. The CLI commands, report formats and recorded experiment bytes retain their existing contracts.

## Security

The crate and binaries contain no `rsa` crate. RustSec and GitHub dependency review no longer exclude the RSA advisories. The dependency guard rejects any future RSA version below patched 0.10.0, and the full OSV scan blocks unreviewed findings. The existing proc-macro-error maintenance notice remains informational.

## Builds

The release uses C2PA 0.92.1, ZIP 9.5.1, Rustix 1.1.6 and Rust 1.96. Source builds need a C compiler, make and Perl for vendored OpenSSL. Windows source builds need Visual Studio C++ and Perl. Platform archives include the dependency notices, source contract and checksums. GitHub build attestations identify the workflow and source commit. Mac and Windows archives have no operating-system signing or notarisation.

## Publication

Verify the exact release commit, crate package, four platform archives, source contract, both CycloneDX inventories and SynthID teaching bundle before updating the download page. The registry package and eight payloads must identify the same tag commit. Earlier releases retain their original dependencies and bytes.

If verification fails, withhold the affected downloads and investigate the release record. A published crate version is immutable, so a corrected crate needs a new version. Keep the previous site deployment available until the new downloads pass their checks.
