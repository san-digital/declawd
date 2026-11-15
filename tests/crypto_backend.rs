#[allow(dead_code)]
#[path = "../build.rs"]
mod build_policy;

#[test]
fn accepts_patched_openssl_lts() {
    for version in ["305000a0", "305000af", "305000bf"] {
        assert!(build_policy::backend_is_supported(Some(version), None));
    }
}

#[test]
fn rejects_old_unsupported_and_other_backends() {
    for version in [
        None,
        Some("invalid"),
        Some("3050009f"),
        Some("3060003f"),
        Some("4000000f"),
    ] {
        assert!(!build_policy::backend_is_supported(version, None));
    }
    assert!(!build_policy::backend_is_supported(
        Some("305000af"),
        Some("true")
    ));
}
