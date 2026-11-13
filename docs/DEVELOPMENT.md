# Development

Use Rust 1.96 or newer, Python 3.12 and the committed dependency locks. Start with [contribution rules](../CONTRIBUTING.md), [responsible use](../ETHICS.md) and the [security policy](../SECURITY.md). Recorded experiments have additional [frozen boundaries](EVIDENCE.md#frozen-boundaries).

## Local checks

Run the checks relevant to your change from the repository root:

```sh
python3 -B -m unittest discover -s reference -p 'test_*.py' -v
cargo fmt -- --check
cargo clippy --all-targets --all-features --locked -- -D warnings
cargo test --all-targets --locked
./scripts/check-c2pa-pin.sh
./scripts/check-security-advisories.sh
./scripts/check-third-party-licences.sh
./scripts/check-c2patool-fixtures.sh
python3 scripts/check-python-runtime-lock.py
./scripts/check-synthid-bundle.sh
```

`check-third-party-licences.sh` needs cargo-about 0.8.4. The C2PA oracle needs c2patool 0.27.12. The [CI workflow](../.github/workflows/ci.yml) pins these tools and shows their installation steps. [Experiment reproduction](EVIDENCE.md#reproduce) and the [future-guard tests](FUTURE-REGISTRATION.md#checks) are separate from the root reference suite.

## Dependency audits

CI audits every package in Cargo.lock, including repeated names at different versions, with the pinned OSV scanner:

```sh
python3 scripts/install-osv-scanner.py /tmp/declawd-osv-scanner
OSV_SCANNER=/tmp/declawd-osv-scanner python3 scripts/check-rust-osv.py --output /tmp/declawd-rust-osv.json
```

The scanner receives locked package names and versions. [SECURITY.md](../SECURITY.md) explains the guarded RSA exception, the upstream affected-range review and the informational unmaintained dependency. Scanner failures and unreviewed advisories stop the check.

The Python audit covers the complete frozen 40-package runner closure, with no vulnerability exclusions. Install [the pinned audit tool](../reference/python-audit-tool-requirements.txt) in a separate environment, then run `python3 scripts/check-python-advisories.py` with that environment on PATH. Run `check-python-runtime-lock.py` after any lock change.

## Software inventories

Install cargo-cyclonedx 0.5.9 and the exact [Python inventory tools](../reference/sbom-tool-requirements.txt), then run:

```sh
./scripts/check-sbom.sh
./scripts/check-python-sbom.sh
./scripts/check-sboms-clean-checkouts.sh
```

The Rust inventory covers runtime and build dependencies, excluding test-only dependencies. The Python inventory covers the reviewed runner closure and records the excluded DeepMind source reference separately. The clean-checkout test checks reproducibility across separate source directories.

## Release checks

The 0.3.4 release uses the patched Rustix and C2PA dependencies. Publish only after the exact release commit passes CI, the crate package is verified and the version tag matches Cargo.toml. The tagged workflow builds four platform archives, a source contract, two CycloneDX 1.5 inventories and the deterministic SynthID teaching bundle, each with a checksum and GitHub provenance. The published 0.3.3 assets retain their original bytes.

After publishing, verify the crate version and every release payload before updating the site's pinned download record. Historical experiment pins retain their original release identities.

Download a payload and its checksum together. Verify using the tool available on your platform:

```sh
# Linux, or another shell with sha256sum
sha256sum --check declawd-v0.3.4-<target>.tar.gz.sha256
sha256sum --check declawd-v0.3.4-x86_64-pc-windows-msvc.zip.sha256

# macOS
shasum -a 256 --check declawd-v0.3.4-<target>.tar.gz.sha256

# The same check applies to inventories and the teaching bundle
sha256sum --check declawd-v0.3.4.cdx.json.sha256
sha256sum --check declawd-v0.3.4-python.cdx.json.sha256
sha256sum --check declawd-v0.3.4-synthid-contracts.tar.gz.sha256

gh attestation verify declawd-v0.3.4-<target>.tar.gz --repo san-digital/declawd
```

Replace `<target>` with the archive's actual target. For an inventory, source contract, teaching bundle or Windows ZIP, give `gh attestation verify` that filename instead. The source contract embedded in every platform archive should match the standalone contract.

GitHub provenance identifies the workflow and source revision. Mac and Windows archives have no operating-system signing or notarisation. Build from the tagged source when local policy requires a different signing arrangement.

## Related work

[demark](https://github.com/jcsuen/demark) informed the inspection workflow and its stated limits. Its code was not copied, forked or executed here. Its PolyForm Noncommercial licence is incompatible with code reuse in this Apache-2.0 project. Dataset, fixture, model and dependency licences remain separate from the original project licence.
