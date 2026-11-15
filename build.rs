pub fn backend_is_supported(aws_lc: Option<&str>, fips: Option<&str>) -> bool {
    aws_lc == Some("true") && fips != Some("true")
}

fn main() {
    let aws_lc = std::env::var("DEP_OPENSSL_AWSLC").ok();
    let fips = std::env::var("DEP_OPENSSL_AWSLC_FIPS").ok();
    assert!(
        backend_is_supported(aws_lc.as_deref(), fips.as_deref()),
        "Declawd requires the reviewed AWS-LC backend through openssl-sys. Check Cargo features before building."
    );
}
