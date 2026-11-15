use sha2::{Digest, Sha256};
use std::path::Path;

pub fn backend_is_supported(
    version: Option<&str>,
    aws_lc: Option<&str>,
    reviewed_snapshot: bool,
) -> bool {
    let Some(version) = version.and_then(|value| u64::from_str_radix(value, 16).ok()) else {
        return false;
    };
    let stable_lts = (0x3050_00af..0x3060_0000).contains(&version) && version & 0xf == 0xf;
    aws_lc != Some("true") && (stable_lts || (version == 0x3050_00a0 && reviewed_snapshot))
}

pub fn snapshot_is_reviewed(prefix: &Path, target: &str, pin: &serde_json::Value) -> bool {
    let verify = || -> Option<bool> {
        let receipt: serde_json::Value =
            serde_json::from_slice(&std::fs::read(prefix.join("openssl-build.json")).ok()?).ok()?;
        if receipt["source_revision"] != pin["source_revision"]
            || receipt["sha256"] != pin["sha256"]
            || receipt["version"] != pin["version"]
            || receipt["backend"] != "openssl-lts"
            || receipt["target"] != target
        {
            return Some(false);
        }
        let libraries = if target.ends_with("windows-msvc") {
            ["libcrypto.lib", "libssl.lib"]
        } else {
            ["libcrypto.a", "libssl.a"]
        };
        for library in libraries {
            let bytes = std::fs::read(prefix.join("lib").join(library)).ok()?;
            let digest = hex::encode(Sha256::digest(bytes));
            if receipt["libraries"][library].as_str() != Some(&digest) {
                return Some(false);
            }
        }
        Some(true)
    };
    verify() == Some(true)
}

fn main() {
    let version = std::env::var("DEP_OPENSSL_VERSION_NUMBER").ok();
    let aws_lc = std::env::var("DEP_OPENSSL_AWSLC").ok();
    let include = std::env::var("DEP_OPENSSL_INCLUDE").ok();
    let target = std::env::var("TARGET").unwrap_or_default();
    let pin: serde_json::Value = serde_json::from_str(include_str!("native/openssl-lts.json"))
        .expect("valid OpenSSL source pin");
    let reviewed = include
        .as_deref()
        .and_then(|path| Path::new(path).parent())
        .is_some_and(|prefix| {
            println!(
                "cargo:rerun-if-changed={}",
                prefix.join("openssl-build.json").display()
            );
            let libraries = if target.ends_with("windows-msvc") {
                ["libcrypto.lib", "libssl.lib"]
            } else {
                ["libcrypto.a", "libssl.a"]
            };
            for library in libraries {
                println!(
                    "cargo:rerun-if-changed={}",
                    prefix.join("lib").join(library).display()
                );
            }
            snapshot_is_reviewed(prefix, &target, &pin)
        });
    assert!(
        backend_is_supported(version.as_deref(), aws_lc.as_deref(), reviewed),
        "Declawd requires patched OpenSSL 3.5 LTS. Use the pinned source builder for 3.5.10-dev, or a stable 3.5.10 or later release in the 3.5 series. Set OPENSSL_NO_VENDOR=1 and OPENSSL_DIR. See docs/DEVELOPMENT.md."
    );
}
