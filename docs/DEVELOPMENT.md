# Development

Use Rust 1.96 or newer, Python 3.12 and the committed dependency locks. Source builds require a C compiler and patched OpenSSL 3.5 LTS libraries. Windows builds need Visual Studio C++ and Perl. Start with [contribution rules](../CONTRIBUTING.md), [responsible use](../ETHICS.md) and the [security policy](../SECURITY.md). Recorded experiments have additional [frozen boundaries](EVIDENCE.md#frozen-boundaries).

## OpenSSL setup

The builder verifies the source archive hash in `native/openssl-lts.json`, builds static libraries and writes `openssl-build.json`. It selects the official 3.5 maintenance commit with all five public November fixes. The source calls itself `3.5.10-dev`, ahead of the release scheduled for 1 December. Published binaries include these libraries.

On macOS or Linux, with a C compiler, Make and Perl installed:

```sh
python3 scripts/build-openssl-lts.py --prefix /tmp/declawd-openssl
export OPENSSL_NO_VENDOR=1 OPENSSL_STATIC=1 OPENSSL_DIR=/tmp/declawd-openssl
cargo install --path . --locked
```

On Windows, use an x64 Visual Studio developer PowerShell with Perl and Python 3.12 available:

```powershell
python scripts/build-openssl-lts.py --prefix C:/declawd-openssl
$env:OPENSSL_NO_VENDOR = "1"
$env:OPENSSL_STATIC = "1"
$env:OPENSSL_DIR = "C:/declawd-openssl"
cargo install --path . --locked
```

For a registry install, use `cargo install declawd --locked --version 0.3.6` after the same setup. An existing patched OpenSSL 3.5 installation can be selected with these variables. The build guard rejects versions below 3.5.10-dev and other series. The builder requires a fresh prefix and supports the four published targets. Cross compilation on macOS needs a separate target prefix, selected with the target-specific OpenSSL environment variable.

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

The scanner receives locked package names and versions. [SECURITY.md](../SECURITY.md) explains RSA removal, the upstream affected-range review and the informational unmaintained dependency. Scanner failures and unreviewed advisories stop the check.

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

The 0.3.6 release selects C2PA's OpenSSL API with a pinned static build from the supported 3.5 LTS branch, retaining the Rust RSA dependency removal from 0.3.5. Publish only after the exact release commit passes CI, the crate package is verified and the version tag matches Cargo.toml. The tagged workflow builds four platform archives, a source contract, two CycloneDX 1.5 inventories and the deterministic SynthID teaching bundle, each with a checksum and GitHub provenance. Published 0.3.5 and earlier assets retain their original bytes.

After publishing, verify the crate version and every release payload before updating the site's pinned download record. Historical experiment pins retain their original release identities.

Download a payload and its checksum together. Verify using the tool available on your platform:

```sh
# Linux, or another shell with sha256sum
sha256sum --check declawd-v0.3.6-<target>.tar.gz.sha256
sha256sum --check declawd-v0.3.6-x86_64-pc-windows-msvc.zip.sha256

# macOS
shasum -a 256 --check declawd-v0.3.6-<target>.tar.gz.sha256

# The same check applies to inventories and the teaching bundle
sha256sum --check declawd-v0.3.6.cdx.json.sha256
sha256sum --check declawd-v0.3.6-python.cdx.json.sha256
sha256sum --check declawd-v0.3.6-synthid-contracts.tar.gz.sha256

gh attestation verify declawd-v0.3.6-<target>.tar.gz --repo san-digital/declawd
```

Replace `<target>` with the archive's actual target. For an inventory, source contract, teaching bundle or Windows ZIP, give `gh attestation verify` that filename instead. The source contract embedded in every platform archive should match the standalone contract.

GitHub provenance identifies the workflow and source revision. Mac and Windows archives have no operating-system signing or notarisation. Build from the tagged source when local policy requires a different signing arrangement.

## Related work

[demark](https://github.com/jcsuen/demark) informed the inspection workflow and its stated limits. Its code was not copied, forked or executed here. Its PolyForm Noncommercial licence is incompatible with code reuse in this Apache-2.0 project. Dataset, fixture, model and dependency licences remain separate from the original project licence.
