use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

use assert_cmd::Command;
use declawd::{TextSelectors, clean_text_file, inspect_file};
use serde_json::Value;
use tempfile::tempdir;

fn assert_valid_against_schema(value: &Value) {
    let schema: Value =
        serde_json::from_str(include_str!("../spec/report-v1.schema.json")).unwrap();
    let validator = jsonschema::validator_for(&schema).expect("report schema compiles");
    if let Err(error) = validator.validate(value) {
        panic!("report does not match spec/report-v1.schema.json: {error}");
    }
}

fn assert_report_shape(value: &Value) {
    let object = value.as_object().expect("report is an object");
    for required in [
        "schema",
        "tool_version",
        "operation",
        "changed",
        "input",
        "findings",
        "requested_actions",
        "completed_actions",
        "verification",
        "untested_channels",
        "warnings",
    ] {
        assert!(object.contains_key(required), "missing {required}");
    }
    assert_eq!(value["schema"], "declawd.report/v1");
    assert!(
        value["input"]["sha256"]
            .as_str()
            .is_some_and(|digest| digest.len() == 64)
    );
    let allowed_actions = BTreeSet::from([
        "remove-code-point",
        "remove-class",
        "replace-code-point",
        "remove-embedded-c2pa",
    ]);
    for action in value["requested_actions"]
        .as_array()
        .expect("actions array")
    {
        assert!(allowed_actions.contains(action["action"].as_str().unwrap()));
    }
    assert_valid_against_schema(value);
}

#[test]
fn normative_report_vector_matches_the_contract() {
    let schema: Value =
        serde_json::from_str(include_str!("../spec/report-v1.schema.json")).unwrap();
    assert_eq!(
        schema["$schema"],
        "https://json-schema.org/draft/2020-12/schema"
    );
    let vector: Value = serde_json::from_str(include_str!("../vectors/report-v1.json")).unwrap();
    assert_report_shape(&vector);
}

#[test]
fn inspect_and_clean_text_reports_match_the_contract() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    let output = directory.path().join("output.txt");
    fs::write(&input, "a\u{200b}b").unwrap();

    let inspect = serde_json::to_value(inspect_file(&input, false).unwrap()).unwrap();
    assert_report_shape(&inspect);

    let mut selectors = TextSelectors::default();
    selectors.remove.insert(0x200b);
    let clean =
        serde_json::to_value(clean_text_file(&input, &output, &selectors, false).unwrap()).unwrap();
    assert_report_shape(&clean);
}

#[test]
fn inspect_and_clean_c2pa_reports_match_the_contract() {
    let directory = tempdir().unwrap();
    let input = Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures/c2pa/signed.png");
    let output = directory.path().join("cleaned.png");

    let inspect = serde_json::to_value(inspect_file(&input, false).unwrap()).unwrap();
    assert_report_shape(&inspect);

    let clean =
        serde_json::to_value(declawd::clean_c2pa_file(&input, &output, false).unwrap()).unwrap();
    assert_report_shape(&clean);
}

#[test]
fn cli_json_inspect_matches_the_contract() {
    let directory = tempdir().unwrap();
    let input = directory.path().join("input.txt");
    fs::write(&input, "plain text").unwrap();
    let bytes = Command::cargo_bin("declawd")
        .unwrap()
        .args(["inspect", input.to_str().unwrap(), "--json"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let report: Value = serde_json::from_slice(&bytes).unwrap();
    assert_report_shape(&report);
}
