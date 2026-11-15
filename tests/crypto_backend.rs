#[allow(dead_code)]
#[path = "../build.rs"]
mod build_policy;

#[test]
fn accepts_patched_openssl_lts() {
    assert!(build_policy::backend_is_supported(
        Some("305000a0"),
        None,
        true
    ));
    for version in ["305000af", "305000bf"] {
        assert!(build_policy::backend_is_supported(
            Some(version),
            None,
            false
        ));
    }
}

#[test]
fn rejects_old_unsupported_and_unverified_backends() {
    for version in [
        None,
        Some("invalid"),
        Some("3050009f"),
        Some("3060003f"),
        Some("4000000f"),
        Some("305000a0"),
    ] {
        assert!(!build_policy::backend_is_supported(version, None, false));
    }
    assert!(!build_policy::backend_is_supported(
        Some("305000af"),
        Some("true"),
        true
    ));
}

#[test]
fn verifies_snapshot_source_target_and_library_bytes() {
    use sha2::{Digest, Sha256};
    let directory = tempfile::tempdir().unwrap();
    let prefix = directory.path();
    std::fs::create_dir(prefix.join("lib")).unwrap();
    let mut receipt: serde_json::Value =
        serde_json::from_str(include_str!("../native/openssl-lts.json")).unwrap();
    receipt["target"] = "aarch64-apple-darwin".into();
    for name in ["libcrypto.a", "libssl.a"] {
        std::fs::write(prefix.join("lib").join(name), name.as_bytes()).unwrap();
        receipt["libraries"][name] = hex::encode(Sha256::digest(name.as_bytes())).into();
    }
    let pin: serde_json::Value =
        serde_json::from_str(include_str!("../native/openssl-lts.json")).unwrap();
    std::fs::write(
        prefix.join("openssl-build.json"),
        serde_json::to_vec(&receipt).unwrap(),
    )
    .unwrap();
    assert!(build_policy::snapshot_is_reviewed(
        prefix,
        "aarch64-apple-darwin",
        &pin
    ));
    assert!(!build_policy::snapshot_is_reviewed(
        prefix,
        "x86_64-apple-darwin",
        &pin
    ));
    std::fs::write(prefix.join("lib/libcrypto.a"), b"modified").unwrap();
    assert!(!build_policy::snapshot_is_reviewed(
        prefix,
        "aarch64-apple-darwin",
        &pin
    ));
}
