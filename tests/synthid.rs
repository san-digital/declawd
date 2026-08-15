use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command as ProcessCommand;

use assert_cmd::Command;
use predicates::prelude::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tempfile::tempdir;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).to_path_buf()
}

fn fixture(name: &str) -> PathBuf {
    root().join("fixtures/synthid").join(name)
}

fn validator(schema_name: &str) -> jsonschema::Validator {
    let schema: Value =
        serde_json::from_slice(&fs::read(root().join("spec").join(schema_name)).unwrap()).unwrap();
    jsonschema::validator_for(&schema).unwrap()
}

#[test]
fn profile_distribution_and_reports_match_their_schemas() {
    let profile: Value =
        serde_json::from_slice(&fs::read(fixture("profile-v1.json")).unwrap()).unwrap();
    validator("synthid-profile-v1.schema.json")
        .validate(&profile)
        .unwrap();
    let distribution: Value =
        serde_json::from_slice(&fs::read(fixture("distribution-v1.json")).unwrap()).unwrap();
    validator("synthid-distribution-v1.schema.json")
        .validate(&distribution)
        .unwrap();
    let candidates = distribution["candidates"].as_array().unwrap();
    let denominator = distribution["mass_denominator"].as_u64().unwrap();
    assert_eq!(
        candidates
            .iter()
            .map(|candidate| candidate["mass_numerator"].as_u64().unwrap())
            .sum::<u64>(),
        denominator
    );
    let ids = candidates
        .iter()
        .map(|candidate| candidate["id"].as_str().unwrap())
        .collect::<std::collections::BTreeSet<_>>();
    let token_ids = candidates
        .iter()
        .map(|candidate| candidate["token_id"].as_u64().unwrap())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(ids.len(), candidates.len());
    assert_eq!(token_ids.len(), candidates.len());
    for draw in distribution["draws"].as_array().unwrap() {
        assert!(ids.contains(draw["first"].as_str().unwrap()));
        assert!(ids.contains(draw["second"].as_str().unwrap()));
        let depth = draw["depth"].as_u64().unwrap() as usize;
        let first = candidates
            .iter()
            .position(|candidate| candidate["id"] == draw["first"])
            .unwrap();
        let second = candidates
            .iter()
            .position(|candidate| candidate["id"] == draw["second"])
            .unwrap();
        let rows = distribution["g_values"].as_array().unwrap();
        let expected =
            if rows[first][depth].as_u64().unwrap() >= rows[second][depth].as_u64().unwrap() {
                &candidates[first]["id"]
            } else {
                &candidates[second]["id"]
            };
        assert_eq!(&draw["winner"], expected);
    }

    for name in [
        "trace-prepared-v1.json",
        "trace-eos-v1.json",
        "gpt2-trace-v1.json",
        "trace-short-v1.json",
    ] {
        let trace: Value = serde_json::from_slice(&fs::read(fixture(name)).unwrap()).unwrap();
        validator("synthid-trace-v1.schema.json")
            .validate(&trace)
            .unwrap();
        let output = Command::cargo_bin("declawd")
            .unwrap()
            .args([
                "lab",
                "synthid",
                "score",
                fixture(name).to_str().unwrap(),
                "--json",
            ])
            .assert()
            .success()
            .get_output()
            .stdout
            .clone();
        let report: Value = serde_json::from_slice(&output).unwrap();
        validator("synthid-score-v1.schema.json")
            .validate(&report)
            .unwrap();
    }
}

#[test]
fn rust_and_python_reports_are_byte_identical() {
    for name in [
        "trace-prepared-v1.json",
        "trace-eos-v1.json",
        "trace-repeated-v1.json",
        "trace-short-v1.json",
        "gpt2-trace-v1.json",
    ] {
        let trace = fixture(name);
        let rust = Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", trace.to_str().unwrap(), "--json"])
            .assert()
            .success()
            .get_output()
            .stdout
            .clone();
        let python = ProcessCommand::new("python3")
            .arg(root().join("reference/synthid_reference.py"))
            .arg(trace)
            .output()
            .unwrap();
        assert!(
            python.status.success(),
            "{name}: {}",
            String::from_utf8_lossy(&python.stderr)
        );
        assert_eq!(
            rust, python.stdout,
            "cross-runtime report differs for {name}"
        );
    }
}

#[test]
fn eos_repetition_and_short_vectors_are_pinned() {
    let cases = [
        ("trace-eos-v1.json", "scored", 2, Some("0.400000000000")),
        (
            "trace-repeated-v1.json",
            "scored",
            5,
            Some("0.560000000000"),
        ),
        ("trace-short-v1.json", "insufficient_data", 0, None),
    ];
    for (name, status, valid, decimal) in cases {
        let output = Command::cargo_bin("declawd")
            .unwrap()
            .args([
                "lab",
                "synthid",
                "score",
                fixture(name).to_str().unwrap(),
                "--json",
            ])
            .assert()
            .success()
            .get_output()
            .stdout
            .clone();
        let report: Value = serde_json::from_slice(&output).unwrap();
        assert_eq!(report["status"], status);
        assert_eq!(report["valid_context_count"], valid);
        if let Some(decimal) = decimal {
            assert_eq!(report["raw_score"]["decimal"], decimal);
        } else {
            assert!(report["raw_score"].is_null());
            assert!(report["weighted_score"].is_null());
        }
    }
}

#[test]
fn expected_mismatch_exits_three() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("mismatch.json");
    let mut trace: Value =
        serde_json::from_slice(&fs::read(fixture("trace-prepared-v1.json")).unwrap()).unwrap();
    trace["expected"]["raw_score"]["numerator"] = json!(130);
    fs::write(&path, serde_json::to_vec_pretty(&trace).unwrap()).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("expected result does not match"));
}

#[test]
fn traces_reject_prose_floats_unknown_fields_and_oversize_input() {
    let directory = tempdir().unwrap();
    let base: Value =
        serde_json::from_slice(&fs::read(fixture("trace-short-v1.json")).unwrap()).unwrap();
    let mut prose = base.clone();
    prose["text"] = json!("not accepted");
    let mut floating = base;
    floating["token_ids"] = json!([1, 2, 3, 4, 5.5]);
    for (name, document, message) in [
        ("prose.json", prose, "unknown field"),
        ("float.json", floating, "invalid type"),
    ] {
        let path = directory.path().join(name);
        fs::write(&path, serde_json::to_vec(&document).unwrap()).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap()])
            .assert()
            .code(2)
            .stderr(predicate::str::contains(message));
    }

    let oversized = directory.path().join("oversized.json");
    let file = fs::File::create(&oversized).unwrap();
    file.set_len(declawd::synthid::TRACE_LIMIT + 1).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", oversized.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("8388608-byte limit"));
}

#[cfg(unix)]
#[test]
fn trace_symlinks_are_refused() {
    use std::os::unix::fs::symlink;
    let directory = tempdir().unwrap();
    let link = directory.path().join("trace.json");
    symlink(fixture("trace-short-v1.json"), &link).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", link.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("symlink inputs are refused"));
}

#[test]
fn committed_sampling_table_is_exact() {
    let bytes = fs::read(fixture("sampling-table-v1.bin")).unwrap();
    assert_eq!(bytes.len(), 8192);
    assert_eq!(
        hex::encode(Sha256::digest(&bytes)),
        "4b2efa3fbbaa5f77facce45f2c2af38ba36436b2b2b81f950005fa8af266fd3c"
    );
}

fn trace_document(trace_id: &str, token_ids: Value, eos_token_id: Value) -> Value {
    json!({
        "schema": "declawd.synthid-trace/v1",
        "trace_id": trace_id,
        "profile": {
            "id": "declawd.synthid-profile/v1",
            "file_sha256": "3fcb8947cc6e267a653196571d9e43434de405b2977838cf95167c94c0ac8e08"
        },
        "sequence_role": "generated_output_only",
        "tokenizer": {
            "model_id": "declawd/model-neutral-token-ids",
            "revision": "v1",
            "eos_token_id": eos_token_id
        },
        "token_ids": token_ids
    })
}

fn run_trace(document: &Value) -> Value {
    let directory = tempdir().unwrap();
    let path = directory.path().join("trace.json");
    fs::write(&path, serde_json::to_vec(document).unwrap()).unwrap();
    let output = Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

#[test]
fn repetition_history_expires_after_1024_contexts() {
    let mut tokens = (0..1031).collect::<Vec<u32>>();
    tokens.extend([0, 1, 2, 3, 99]);
    let report = run_trace(&trace_document(
        "history-eviction",
        json!(tokens),
        Value::Null,
    ));
    assert_eq!(report["candidate_context_count"], 1032);
    assert_eq!(report["repetition_excluded_count"], 0);
    assert_eq!(report["valid_context_count"], 1032);
}

#[test]
fn eos_before_the_first_complete_ngram_yields_null_scores() {
    let report = run_trace(&trace_document(
        "early-eos",
        json!([999, 1, 2, 3, 4, 5]),
        json!(999),
    ));
    assert_eq!(report["first_eos_index"], 0);
    assert_eq!(report["candidate_context_count"], 2);
    assert_eq!(report["eos_excluded_count"], 2);
    assert_eq!(report["valid_context_count"], 0);
    assert_eq!(report["status"], "insufficient_data");
    assert!(report["raw_score"].is_null());
}

#[test]
fn token_id_and_token_count_bounds_are_enforced() {
    let accepted = run_trace(&trace_document(
        "i32-boundary",
        json!(vec![2_147_483_647u32; 5]),
        Value::Null,
    ));
    assert_eq!(accepted["token_count"], 5);

    let directory = tempdir().unwrap();
    for (name, document, message) in [
        (
            "too-large.json",
            trace_document("too-large", json!(vec![2_147_483_648u64; 5]), Value::Null),
            "token IDs must be from 0 to 2147483647",
        ),
        (
            "negative.json",
            trace_document("negative", json!([-1, 2, 3, 4, 5]), Value::Null),
            "invalid value",
        ),
        (
            "too-many.json",
            trace_document("too-many", json!(vec![0; 100_001]), Value::Null),
            "more than 100000 token IDs",
        ),
    ] {
        let path = directory.path().join(name);
        fs::write(&path, serde_json::to_vec(&document).unwrap()).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap()])
            .assert()
            .code(2)
            .stderr(predicate::str::contains(message));
    }
}

#[test]
fn tokenizer_metadata_uses_the_schema_character_limit() {
    let accepted = trace_document("unicode-metadata", json!([1, 2, 3, 4, 5]), Value::Null);
    let mut accepted = accepted;
    accepted["tokenizer"]["model_id"] = json!("é".repeat(256));
    let report = run_trace(&accepted);
    assert_eq!(report["token_count"], 5);

    let directory = tempdir().unwrap();
    let path = directory.path().join("metadata-too-long.json");
    accepted["tokenizer"]["model_id"] = json!("é".repeat(257));
    fs::write(&path, serde_json::to_vec(&accepted).unwrap()).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", path.to_str().unwrap()])
        .assert()
        .code(2)
        .stderr(predicate::str::contains("1 to 256"));
}
