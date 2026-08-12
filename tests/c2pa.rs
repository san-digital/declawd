use std::fs;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD;
use declawd::{clean_c2pa_file, inspect_file};
use tempfile::tempdir;

const PNG: &str = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAJWlDQ1BJQ0MgUHJvZmlsZQAAeJwrSS0u0c1MTtYtKMpPy8xJBQA0wAY7S2eyQwAAAB50RVh0Q29weXJpZ2h0AERlY2xhd2QgdGVzdCBmaXh0dXJlXLv0HwAAACt0RVh0RGVzY3JpcHRpb24AdW5yZWxhdGVkIG1ldGFkYXRhIG11c3Qgc3Vydml2ZYJvXpgAAAASSURBVHicY+RRsmBgYGBiAAMABMYAapYtOQQAAAAASUVORK5CYII=";
const JPEG: &str = "/9j/4AAQSkZJRgABAQAAAQABAAD/4QBERXhpZgAATU0AKgAAAAgAAgESAAMAAAABAAYAAIKYAAIAAAAVAAAAJgAAAABEZWNsYXdkIHRlc3QgZml4dHVyZQAA/+IAIElDQ19QUk9GSUxFAAEBdGVzdC1pY2MtcHJvZmlsZf/+ACF1bnJlbGF0ZWQgbWV0YWRhdGEgbXVzdCBzdXJ2aXZl/9sAQwADAgIDAgIDAwMDBAMDBAUIBQUEBAUKBwcGCAwKDAwLCgsLDQ4SEA0OEQ4LCxAWEBETFBUVFQwPFxgWFBgSFBUU/9sAQwEDBAQFBAUJBQUJFA0LDRQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU/8AAEQgAAgACAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYSQVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz9PX29/j5+v/aAAwDAQACEQMRAD8A/PqiiivqD5w//9k=";

fn minimal_c2pa_jumbf() -> Vec<u8> {
    let mut store = Vec::new();
    store.extend_from_slice(&37u32.to_be_bytes());
    store.extend_from_slice(b"jumb");
    store.extend_from_slice(&29u32.to_be_bytes());
    store.extend_from_slice(b"jumd");
    store.extend_from_slice(b"c2pa");
    store.extend_from_slice(&[0u8; 12]);
    store.push(0);
    store
}

fn exercise(kind: &str, encoded: &str) {
    let directory = tempdir().unwrap();
    let input = directory.path().join(format!("input.{kind}"));
    let marked = directory.path().join(format!("marked.{kind}"));
    let cleaned = directory.path().join(format!("cleaned.{kind}"));
    fs::write(&input, STANDARD.decode(encoded).unwrap()).unwrap();
    let store = minimal_c2pa_jumbf();
    c2pa::jumbf_io::save_jumbf_to_file(&store, &input, Some(&marked)).unwrap();
    assert_eq!(
        c2pa::jumbf_io::load_jumbf_from_file(&marked).unwrap(),
        store
    );

    let inspected = inspect_file(&marked, false).unwrap();
    assert_eq!(inspected.findings.len(), 1);
    assert_eq!(inspected.findings[0].class, "c2pa-jumbf");

    let report = clean_c2pa_file(&marked, &cleaned, false).unwrap();
    assert!(report.changed);
    assert_eq!(report.verification.embedded_c2pa_absent, Some(true));
    assert_eq!(report.verification.non_c2pa_bytes_unchanged, Some(true));
    assert_eq!(
        report.verification.compressed_image_data_unchanged,
        Some(true)
    );
    assert!(matches!(
        c2pa::jumbf_io::load_jumbf_from_file(&cleaned),
        Err(c2pa::Error::JumbfNotFound)
    ));
    assert!(inspect_file(&cleaned, false).unwrap().findings.is_empty());
}

#[test]
fn removes_only_embedded_c2pa_from_png() {
    exercise("png", PNG);
}

#[test]
fn removes_only_embedded_c2pa_from_jpeg() {
    exercise("jpg", JPEG);
}

#[test]
fn no_op_writes_nothing_without_allow_empty() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.png");
    let output = directory.path().join("output.png");
    fs::write(&input, STANDARD.decode(PNG).unwrap()).unwrap();
    let report = clean_c2pa_file(&input, &output, false).unwrap();
    assert!(!report.changed);
    assert!(report.output.is_none());
    assert!(!output.exists());
}

#[test]
fn allow_empty_writes_byte_identical_image() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.jpg");
    let output = directory.path().join("output.jpg");
    let bytes = STANDARD.decode(JPEG).unwrap();
    fs::write(&input, &bytes).unwrap();
    let report = clean_c2pa_file(&input, &output, true).unwrap();
    assert!(!report.changed);
    assert_eq!(report.verification.byte_identical_copy, Some(true));
    assert_eq!(fs::read(output).unwrap(), bytes);
}

#[test]
fn malformed_images_fail_closed_even_with_allow_empty() {
    let directory = tempdir().unwrap();
    for (name, bytes) in [
        ("bad.png", b"\x89PNG\r\n\x1a\n".as_slice()),
        ("bad.jpg", b"\xff\xd8\xff".as_slice()),
    ] {
        let input = directory.path().join(name);
        let output = directory.path().join(format!("{name}.out"));
        fs::write(&input, bytes).unwrap();
        assert!(clean_c2pa_file(&input, &output, true).is_err());
        assert!(!output.exists());
    }
}

#[test]
fn structural_corruption_and_bad_crc_fail_closed() {
    let directory = tempdir().unwrap();
    let mut png = STANDARD.decode(PNG).unwrap();
    png[20] ^= 1;
    let mut jpeg = STANDARD.decode(JPEG).unwrap();
    jpeg.truncate(8);
    for (name, bytes) in [("bad-crc.png", png), ("truncated.jpg", jpeg)] {
        let input = directory.path().join(name);
        let output = directory.path().join(format!("{name}.out"));
        fs::write(&input, bytes).unwrap();
        assert!(inspect_file(&input, false).is_err());
        assert!(clean_c2pa_file(&input, &output, true).is_err());
        assert!(!output.exists());
    }
}

#[test]
fn required_png_chunks_and_jpeg_eoi_are_enforced() {
    let directory = tempdir().unwrap();
    let iend_only = STANDARD.decode("iVBORw0KGgoAAAAASUVORK5CYII=").unwrap();
    let unterminated_scan = vec![0xff, 0xd8, 0xff, 0xda, 0x00, 0x02, 0x00];
    for (name, bytes) in [
        ("iend-only.png", iend_only),
        ("unterminated.jpg", unterminated_scan),
    ] {
        let input = directory.path().join(name);
        let output = directory.path().join(format!("{name}.out"));
        fs::write(&input, bytes).unwrap();
        assert!(inspect_file(&input, false).is_err());
        assert!(clean_c2pa_file(&input, &output, true).is_err());
        assert!(!output.exists());
    }
}

#[test]
fn jpeg_marker_fill_change_is_detected_and_output_refused() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.jpg");
    let marked = directory.path().join("marked.jpg");
    let filled = directory.path().join("filled.jpg");
    let output = directory.path().join("output.jpg");
    fs::write(&input, STANDARD.decode(JPEG).unwrap()).unwrap();
    c2pa::jumbf_io::save_jumbf_to_file(&minimal_c2pa_jumbf(), &input, Some(&marked)).unwrap();
    let marked_bytes = fs::read(marked).unwrap();
    let mut fill_bytes = Vec::with_capacity(marked_bytes.len() + 1);
    fill_bytes.extend_from_slice(&marked_bytes[..2]);
    fill_bytes.push(0xff);
    fill_bytes.extend_from_slice(&marked_bytes[2..]);
    fs::write(&filled, fill_bytes).unwrap();

    let error = clean_c2pa_file(&filled, &output, false).unwrap_err();
    assert_eq!(error.exit_code(), 3);
    assert!(
        error
            .to_string()
            .contains("outside the embedded C2PA carrier changed")
    );
    assert!(!output.exists());
}
