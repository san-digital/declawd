# Contributing

Contributions are welcome when they preserve the project's evidence and safety
boundaries. Please include tests and explain the supported carrier precisely.

Before opening a pull request, run:

```sh
python3 -m unittest discover -s reference -p 'test_*.py'
cargo fmt -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets
./scripts/check-c2pa-pin.sh
./scripts/check-security-advisories.sh
./scripts/check-third-party-licences.sh
./scripts/check-c2patool-fixtures.sh
```

Do not add claims of compatibility with an undisclosed production watermark
without reproducible ground truth from its provider.
