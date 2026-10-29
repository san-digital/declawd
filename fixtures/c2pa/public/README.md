# C2PA cases

This set adds six unmodified JPEG assets created by Adobe from [c2pa-org/public-testfiles](https://github.com/c2pa-org/public-testfiles/tree/22beccc075707475b038d8789d0136c009e43143/legacy/1.4/image/jpeg), pinned at revision `22beccc075707475b038d8789d0136c009e43143`. They retain [CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0.txt). The Apache-2.0 project licence applies to the local controls and test code. The [manifest](../public-fixture-manifest.json) records each asset's original URL, creator, licence, input hash and expected output hash.

| Case | Container | Expected result |
|---|---|---|
| `adobe-20220124-A` | JPEG | No embedded claim, byte-identical copy with `--allow-empty` |
| `adobe-20220124-C` | JPEG | One manifest with a matching binding and signature, remove its store |
| `adobe-20220124-CA` | JPEG | Manifest with a parent ingredient, remove its store |
| `adobe-20220124-E-dat-CA` | JPEG | Binding mismatch, remove its store |
| `adobe-20220124-E-sig-CA` | JPEG | Signature mismatch, remove its store |
| `adobe-20220124-E-uri-CA` | JPEG | Assertion hash mismatch, remove its store |
| `png-binding-mismatch` | PNG | Changed pixels with the old manifest, remove its store |
| `png-bad-crc` | PNG | Refuse the malformed container and write no output |
| `jpeg-truncated` | JPEG | Refuse the malformed container and write no output |

The PNG binding case changes the first sample byte in the decoded IDAT stream of `../signed.png` with XOR `0x10`, recompresses it with zlib and recalculates the chunk CRC. The bad-CRC control changes byte 20 of `../source.png` with XOR `0x01` and leaves the CRC untouched. The truncated JPEG retains the first 32 bytes of `../source.jpg`. These controls have no dependency on the v1 or v2 text experiments. The pinned public collection's PNG directories contain no image assets, so its JPEG files are the upstream interoperability cases.

`cargo test --locked --test c2pa` checks every input hash, store presence, removal or rejection, retained output bytes, input preservation and repeated cleaning. `scripts/check-c2patool-fixtures.sh` additionally runs `c2patool 0.27.12` to check the expected signature, binding and assertion results, then independently confirms claim absence after cleaning. Bad signatures and bindings remain distinct from malformed image containers. Certificate expiry and public trust-list acceptance are outside these assertions.
