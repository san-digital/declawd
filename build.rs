pub fn backend_is_supported(version: Option<&str>, aws_lc: Option<&str>) -> bool {
    let Some(version) = version.and_then(|value| u64::from_str_radix(value, 16).ok()) else {
        return false;
    };
    aws_lc != Some("true") && (0x3050_00a0..0x3060_0000).contains(&version)
}

fn main() {
    let version = std::env::var("DEP_OPENSSL_VERSION_NUMBER").ok();
    let aws_lc = std::env::var("DEP_OPENSSL_AWSLC").ok();
    assert!(
        backend_is_supported(version.as_deref(), aws_lc.as_deref()),
        "Declawd requires OpenSSL 3.5 LTS with the November 2026 fixes (3.5.10-dev or newer in the 3.5 series). Set OPENSSL_NO_VENDOR=1 and OPENSSL_DIR to your patched installation. See docs/DEVELOPMENT.md."
    );
}
