# Declawd 0.3.2

This release updates the crate and platform binaries with the dependency fixes merged since 0.3.1. It requires Rust 1.96 or newer. The SDK is pinned to c2pa 0.91.7 and the lock selects ZIP 9.0.5, which fixes the critical GHSA-m665-v7pm-7grj advisory. The upgrade also resolves the three earlier ZIP advisories and the crypto-bigint advisory. The reviewed RSA exception remains limited to the recorded source, dependency versions and 28 November expiry.

CI now checks every Cargo.lock package against OSV and runs GitHub dependency review on pull requests. Nine additional C2PA cases cover public JPEG fixtures, invalid signatures and bindings, and malformed PNG/JPEG containers. The existing independent c2patool checks verify removal and retained bytes.

The separate TrustMark Q experiment records twelve generated PNG/JPEG cases. The matching decoder recovered ten exact payloads before C2PA was added and the same ten after removal. Both tiled images were missed throughout. Every cleaned file was byte-identical to its marked version from before signing. The plan, inputs and model hashes were committed before encoding. These results concern the fixed images and decoder settings.

The registered Declawd v1/v2 and SynthID scoring contracts retain their original bytes. The TrustMark model runtime is separate from the CLI and excluded from the Rust crate. The macOS and Windows binaries carry GitHub build attestations and remain unsigned by operating-system signing services.
