use std::fs;

use assert_cmd::Command;
use declawd::{MAX_FINDINGS, TEXT_LIMIT};
use predicates::prelude::*;
use serde_json::Value;
use tempfile::tempdir;

#[test]
fn inspect_findings_exit_one_and_exit_zero_is_available() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    fs::write(&input, "a\u{200b}b").unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap(), "--json"])
        .assert()
        .code(1)
        .stdout(predicate::str::contains(
            "\"schema\": \"declawd.report/v1\"",
        ));
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap(), "--exit-zero"])
        .assert()
        .success();
}

#[test]
fn human_reports_name_every_untested_channel() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    fs::write(&input, "plain text").unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap()])
        .assert()
        .success()
        .stdout(predicate::str::contains(
            "Not tested: statistical token-choice watermarks",
        ))
        .stdout(predicate::str::contains(
            "Not tested: pixel-level or perceptual watermarks",
        ));
}

#[test]
fn selective_text_cleaning_emits_report_and_never_overwrites() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    fs::write(&input, "a\u{202f}b\u{200b}c").unwrap();
    let result = Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--replace",
            "U+202F=U+0020",
            "--remove",
            "U+200B",
            "--json",
        ])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    assert_eq!(fs::read_to_string(&output).unwrap(), "a bc");
    let report: Value = serde_json::from_slice(&result).unwrap();
    assert_eq!(report["changed"], true);
    assert_eq!(report["verification"]["supported_carriers_remaining"], 0);

    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove",
            "U+200B",
        ])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("refusing to overwrite"));
}

#[test]
fn text_no_op_requires_allow_empty_to_create_output() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    fs::write(&input, "plain text\r\n").unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove-class",
            "zero-width",
            "--json",
        ])
        .assert()
        .success();
    assert!(!output.exists());

    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove-class",
            "zero-width",
            "--allow-empty",
        ])
        .assert()
        .success();
    assert_eq!(fs::read(output).unwrap(), b"plain text\r\n");
}

#[test]
fn invalid_utf8_utf16_and_selector_conflicts_exit_two() {
    let directory = tempdir().unwrap();
    let invalid = directory.path().join("invalid.txt");
    fs::write(&invalid, [0xff, 0xfe, b'a', 0]).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", invalid.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("not valid UTF-8"));

    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    fs::write(&input, "a\u{200b}b").unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove",
            "U+200B",
            "--replace",
            "U+200B=U+0020",
        ])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("both removed and replaced"));
}

#[test]
fn format_control_is_not_a_selectable_class() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    fs::write(&input, "a\u{200c}b").unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove-class",
            "format-control",
        ])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("not selectable"));
}

#[cfg(unix)]
#[test]
fn symlink_inputs_are_refused() {
    use std::os::unix::fs::symlink;

    let directory = tempdir().unwrap();
    let target = directory.path().join("target.txt");
    let input = directory.path().join("input.txt");
    fs::write(&target, "plain text").unwrap();
    symlink(&target, &input).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("symlink inputs are refused"));
}

#[test]
fn reading_preserves_the_first_eight_bytes() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    let text = "12345678plain text";
    fs::write(&input, text).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "clean",
            "text",
            input.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
            "--remove-class",
            "zero-width",
            "--allow-empty",
        ])
        .assert()
        .success();
    assert_eq!(fs::read_to_string(output).unwrap(), text);
}

#[test]
fn oversized_text_is_rejected_before_processing() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("oversized.txt");
    let file = fs::File::create(&input).unwrap();
    file.set_len(TEXT_LIMIT + 1).unwrap();

    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("limit is 10485760 bytes"));
}

#[test]
fn dense_unicode_findings_fail_at_the_report_bound() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("dense.txt");
    fs::write(&input, "\u{200b}".repeat(MAX_FINDINGS + 1)).unwrap();

    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap(), "--json", "--exit-zero"])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("more than 10000"));
}

#[test]
fn json_escapes_registered_controls_in_opt_in_context() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("bidi.txt");
    fs::write(&input, "prefix \u{202e} txt").unwrap();
    let stdout = Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "inspect",
            input.to_str().unwrap(),
            "--json",
            "--include-context",
            "--exit-zero",
        ])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    assert!(stdout.windows(6).any(|window| window == br"\u202e"));
    assert!(!stdout.windows(3).any(|window| window == [0xe2, 0x80, 0xae]));
    let parsed: Value = serde_json::from_slice(&stdout).unwrap();
    assert_eq!(parsed["findings"][0]["context"]["character"], "\u{202e}");
}
