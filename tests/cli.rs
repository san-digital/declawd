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
fn bare_output_filename_is_written_in_the_current_directory() {
    let directory = tempdir().unwrap();
    fs::write(directory.path().join("input.txt"), "a\u{200b}b").unwrap();

    Command::cargo_bin("declawd")
        .unwrap()
        .current_dir(directory.path())
        .args([
            "clean",
            "text",
            "input.txt",
            "--output",
            "output.txt",
            "--remove",
            "U+200B",
        ])
        .assert()
        .success();

    assert_eq!(
        fs::read_to_string(directory.path().join("output.txt")).unwrap(),
        "ab"
    );
}

#[test]
fn bare_input_and_dot_relative_output_alias_is_refused() {
    let directory = tempdir().unwrap();
    fs::write(directory.path().join("input.txt"), "plain text").unwrap();

    Command::cargo_bin("declawd")
        .unwrap()
        .current_dir(directory.path())
        .args([
            "clean",
            "text",
            "input.txt",
            "--output",
            "./input.txt",
            "--remove",
            "U+200B",
        ])
        .assert()
        .failure()
        .code(2)
        .stderr(predicate::str::contains(
            "input and output resolve to the same path",
        ));

    assert_eq!(
        fs::read_to_string(directory.path().join("input.txt")).unwrap(),
        "plain text"
    );
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
fn encoding_contract_distinguishes_bom_markers_from_valid_utf8_with_nuls() {
    let directory = tempdir().unwrap();
    let bomless = directory.path().join("bomless.txt");
    fs::write(&bomless, [b'A', 0, b'B', 0]).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", bomless.to_str().unwrap()])
        .assert()
        .success();

    Command::cargo_bin("declawd")
        .unwrap()
        .args(["clean", "text", "--help"])
        .assert()
        .success()
        .stdout(predicate::str::contains("UTF-16 with a BOM"));
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

#[test]
fn standard_input_is_inspected_and_matches_the_same_bytes_from_a_file() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    fs::write(&input, "a\u{200b}b").unwrap();
    let from_file = Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap(), "--json", "--exit-zero"])
        .assert()
        .success();
    let from_stdin = Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-", "--json", "--exit-zero"])
        .write_stdin("a\u{200b}b")
        .assert()
        .success();
    // The report describes bytes, so the same bytes give the same report
    // whichever way they arrived. Nothing in it names a path.
    let file_report: Value = serde_json::from_slice(&from_file.get_output().stdout).unwrap();
    let stdin_report: Value = serde_json::from_slice(&from_stdin.get_output().stdout).unwrap();
    assert_eq!(file_report, stdin_report);
}

#[test]
fn standard_input_reports_findings_through_the_exit_code() {
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-"])
        .write_stdin("a\u{200b}b")
        .assert()
        .code(1);
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-"])
        .write_stdin("plain text")
        .assert()
        .success();
}

#[test]
fn standard_input_keeps_the_limits_a_file_has() {
    // The cap cannot be read from metadata here, so it is counted while reading.
    let over = "a".repeat(TEXT_LIMIT as usize + 1);
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-"])
        .write_stdin(over)
        .assert()
        .failure()
        .stderr(predicate::str::contains("standard input exceeds"));
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-"])
        .write_stdin(vec![0xff, 0xfe, 0x41, 0x00])
        .assert()
        .failure()
        .stderr(predicate::str::contains("not valid UTF-8"));
}

#[test]
fn sarif_places_a_finding_and_says_what_was_not_read() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    fs::write(&input, "a\u{200b}b").unwrap();
    let assertion = Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "inspect",
            input.to_str().unwrap(),
            "--sarif",
            "--sarif-uri",
            "docs/page.txt",
            "--exit-zero",
        ])
        .assert()
        .success();
    let sarif: Value = serde_json::from_slice(&assertion.get_output().stdout).unwrap();
    assert_eq!(sarif["version"], "2.1.0");
    let run = &sarif["runs"][0];
    assert_eq!(run["tool"]["driver"]["name"], "declawd");

    // The report carries no path, so the location is the one the caller gave.
    let artifact = &run["artifacts"][0];
    assert_eq!(artifact["location"]["uri"], "docs/page.txt");
    assert_eq!(artifact["hashes"]["sha-256"].as_str().unwrap().len(), 64);

    let results = run["results"].as_array().unwrap();
    let finding = results
        .iter()
        .find(|result| result["ruleId"] == "unicode/zero-width")
        .expect("the zero-width carrier is reported");
    assert_eq!(finding["kind"], "review");
    let region = &finding["locations"][0]["physicalLocation"]["region"];
    assert_eq!(region["startLine"], 1);
    assert_eq!(region["startColumn"], 2);
    assert_eq!(
        finding["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
        "docs/page.txt"
    );

    /* An empty results array in a security dashboard reads as a clean bill of
    health, so every channel this run did not read is stated rather than
    left to be inferred from silence. */
    let untested: Vec<&Value> = results
        .iter()
        .filter(|result| result["ruleId"] == "declawd/untested-channel")
        .collect();
    assert_eq!(untested.len(), 2);
    assert!(
        untested
            .iter()
            .all(|result| result["kind"] == "notApplicable")
    );
    let notifications = run["invocations"][0]["toolExecutionNotifications"]
        .as_array()
        .unwrap();
    assert!(
        notifications.iter().any(|note| note["message"]["text"]
            .as_str()
            .unwrap()
            .contains("No provider verifier ran")),
        "the run says that nothing was verified"
    );
}

#[test]
fn sarif_defaults_its_location_to_the_argument_and_reads_standard_input() {
    let assertion = Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-", "--sarif", "--exit-zero"])
        .write_stdin("plain text")
        .assert()
        .success();
    let sarif: Value = serde_json::from_slice(&assertion.get_output().stdout).unwrap();
    assert_eq!(sarif["runs"][0]["artifacts"][0]["location"]["uri"], "-");
    // Nothing found, and the file still says what it did not look at.
    let results = sarif["runs"][0]["results"].as_array().unwrap();
    assert!(!results.is_empty());
    assert!(
        results
            .iter()
            .all(|result| result["kind"] == "notApplicable")
    );
}

#[test]
fn sarif_and_json_cannot_both_be_asked_for() {
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", "-", "--json", "--sarif"])
        .write_stdin("plain text")
        .assert()
        .failure();
}
