#[allow(dead_code)]
#[path = "../build.rs"]
mod build_policy;

#[test]
fn accepts_the_reviewed_aws_lc_backend() {
    assert!(build_policy::backend_is_supported(Some("true"), None));
}

#[test]
fn rejects_a_missing_backend_or_unreviewed_fips_variant() {
    assert!(!build_policy::backend_is_supported(None, None));
    assert!(!build_policy::backend_is_supported(Some("false"), None));
    assert!(!build_policy::backend_is_supported(
        Some("true"),
        Some("true")
    ));
}
