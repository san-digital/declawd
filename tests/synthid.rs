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
fn profile_schema_pins_key_and_weight_values_and_order() {
    let profile: Value =
        serde_json::from_slice(&fs::read(fixture("profile-v1.json")).unwrap()).unwrap();
    let validator = validator("synthid-profile-v1.schema.json");

    let mut changed_key = profile.clone();
    changed_key["parameters"]["keys"][0] = json!(655);
    assert!(validator.validate(&changed_key).is_err());

    let mut reordered_keys = profile.clone();
    reordered_keys["parameters"]["keys"]
        .as_array_mut()
        .unwrap()
        .swap(0, 1);
    assert!(validator.validate(&reordered_keys).is_err());

    let mut changed_weight = profile.clone();
    changed_weight["scoring"]["weighted_weights"][0] = json!(289);
    assert!(validator.validate(&changed_weight).is_err());

    let mut reordered_weights = profile;
    reordered_weights["scoring"]["weighted_weights"]
        .as_array_mut()
        .unwrap()
        .swap(0, 1);
    assert!(validator.validate(&reordered_weights).is_err());

    let mut changed_limitation: Value =
        serde_json::from_slice(&fs::read(fixture("profile-v1.json")).unwrap()).unwrap();
    changed_limitation["reference"]["transfer_limitation"] = json!("different claim");
    assert!(validator.validate(&changed_limitation).is_err());
}

#[test]
fn profile_bytes_and_runtime_constants_are_bound_together() {
    let bytes = fs::read(fixture("profile-v1.json")).unwrap();
    assert_eq!(
        hex::encode(Sha256::digest(&bytes)),
        declawd::synthid::PROFILE_SHA256
    );
    let profile: Value = serde_json::from_slice(&bytes).unwrap();
    let keys = profile["parameters"]["keys"]
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_i64().unwrap())
        .collect::<Vec<_>>();
    let weights = profile["scoring"]["weighted_weights"]
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_u64().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(keys, declawd::synthid::KEYS);
    assert_eq!(weights, declawd::synthid::WEIGHTS);
    assert_eq!(
        profile["sampling_table"]["sha256"],
        declawd::synthid::SAMPLING_TABLE_SHA256
    );

    let python = ProcessCommand::new("python3")
        .arg("-c")
        .arg("import sys; sys.path.insert(0, 'reference'); import synthid_reference as s; print(s.PROFILE_SHA256); print(','.join(map(str, s.KEYS))); print(','.join(map(str, s.WEIGHTS)))")
        .current_dir(root())
        .output()
        .unwrap();
    assert!(python.status.success());
    let lines = String::from_utf8(python.stdout).unwrap();
    let mut lines = lines.lines();
    assert_eq!(lines.next(), Some(declawd::synthid::PROFILE_SHA256));
    let expected_keys = declawd::synthid::KEYS
        .iter()
        .map(i64::to_string)
        .collect::<Vec<_>>()
        .join(",");
    let expected_weights = declawd::synthid::WEIGHTS
        .iter()
        .map(u64::to_string)
        .collect::<Vec<_>>()
        .join(",");
    assert_eq!(lines.next(), Some(expected_keys.as_str()));
    assert_eq!(lines.next(), Some(expected_weights.as_str()));
}

#[test]
fn fixed_distribution_schema_rejects_every_fabricated_contract_field() {
    let distribution: Value =
        serde_json::from_slice(&fs::read(fixture("distribution-v1.json")).unwrap()).unwrap();
    let validator = validator("synthid-distribution-v1.schema.json");
    for changed in [
        {
            let mut value = distribution.clone();
            value["candidates"][1]["id"] = json!("cedar");
            value
        },
        {
            let mut value = distribution.clone();
            value["candidates"][0]["mass_numerator"] = json!(399);
            value
        },
        {
            let mut value = distribution.clone();
            value["g_values"][0][0] = json!(0);
            value
        },
        {
            let mut value = distribution;
            value["draws"][0]["winner"] = json!("fern");
            value
        },
    ] {
        assert!(validator.validate(&changed).is_err());
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
    let python = ProcessCommand::new("python3")
        .arg(root().join("reference/synthid_reference.py"))
        .arg(&path)
        .output()
        .unwrap();
    assert_eq!(python.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&python.stderr).contains("expected result does not match"));
}

#[test]
fn malformed_expected_values_are_input_errors_in_both_runtimes() {
    let base: Value =
        serde_json::from_slice(&fs::read(fixture("trace-prepared-v1.json")).unwrap()).unwrap();
    let cases = [
        {
            let mut value = base.clone();
            value["expected"] = Value::Null;
            ("null", value)
        },
        {
            let mut value = base.clone();
            value["expected"]["unknown"] = json!(1);
            ("unknown", value)
        },
        {
            let mut value = base.clone();
            value["expected"]
                .as_object_mut()
                .unwrap()
                .remove("raw_score");
            ("missing", value)
        },
        {
            let mut value = base.clone();
            value["expected"]["token_count"] = json!("12");
            ("wrong-type", value)
        },
        {
            let mut value = base.clone();
            value["expected"]["status"] = json!("insufficient_data");
            ("bad-status-relation", value)
        },
        {
            let mut value = base;
            value["expected"]["raw_score"]["decimal"] = json!("2.000000000000");
            ("bad-decimal", value)
        },
    ];
    let directory = tempdir().unwrap();
    for (name, document) in cases {
        let path = directory.path().join(format!("{name}.json"));
        fs::write(&path, serde_json::to_vec(&document).unwrap()).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
            .assert()
            .code(2);
        let python = ProcessCommand::new("python3")
            .arg(root().join("reference/synthid_reference.py"))
            .arg(&path)
            .output()
            .unwrap();
        assert_eq!(python.status.code(), Some(2), "Python accepted {name}");
    }
}

#[test]
fn required_nullable_fields_cannot_be_omitted() {
    let prepared: Value =
        serde_json::from_slice(&fs::read(fixture("trace-prepared-v1.json")).unwrap()).unwrap();
    let short: Value =
        serde_json::from_slice(&fs::read(fixture("trace-short-v1.json")).unwrap()).unwrap();
    let cases = [
        {
            let mut value = prepared.clone();
            value["tokenizer"]
                .as_object_mut()
                .unwrap()
                .remove("eos_token_id");
            ("missing-eos-token-id", value)
        },
        {
            let mut value = prepared;
            value["expected"]
                .as_object_mut()
                .unwrap()
                .remove("first_eos_index");
            ("missing-first-eos-index", value)
        },
        {
            let mut value = short.clone();
            value["expected"]
                .as_object_mut()
                .unwrap()
                .remove("raw_score");
            ("missing-null-raw-score", value)
        },
        {
            let mut value = short;
            value["expected"]
                .as_object_mut()
                .unwrap()
                .remove("weighted_score");
            ("missing-null-weighted-score", value)
        },
    ];
    let directory = tempdir().unwrap();
    for (name, document) in cases {
        let path = directory.path().join(format!("{name}.json"));
        fs::write(&path, serde_json::to_vec(&document).unwrap()).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
            .assert()
            .code(2);
        let python = ProcessCommand::new("python3")
            .arg(root().join("reference/synthid_reference.py"))
            .arg(&path)
            .output()
            .unwrap();
        assert_eq!(python.status.code(), Some(2), "Python accepted {name}");
    }
}

#[test]
fn non_object_json_roots_are_input_errors_in_both_runtimes() {
    let directory = tempdir().unwrap();
    for (name, source) in [
        ("null", "null"),
        ("true", "true"),
        ("number", "1"),
        ("array", "[]"),
    ] {
        let path = directory.path().join(format!("{name}.json"));
        fs::write(&path, source).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
            .assert()
            .code(2);
        let python = ProcessCommand::new("python3")
            .arg(root().join("reference/synthid_reference.py"))
            .arg(&path)
            .output()
            .unwrap();
        assert_eq!(python.status.code(), Some(2), "Python accepted {name}");
        assert!(
            String::from_utf8_lossy(&python.stderr).contains("trace must be a JSON object"),
            "Python returned the wrong error for {name}: {}",
            String::from_utf8_lossy(&python.stderr)
        );
    }
}

#[test]
fn non_canonical_json_encodings_are_input_errors_in_both_runtimes() {
    let source = fs::read(fixture("trace-short-v1.json")).unwrap();
    let utf8 = String::from_utf8(source.clone()).unwrap();
    let duplicate_top_level = utf8.replacen(
        "\"schema\": \"declawd.synthid-trace/v1\"",
        "\"schema\": \"declawd.synthid-trace/v1\",\n  \"schema\": \"declawd.synthid-trace/v1\"",
        1,
    );
    let duplicate_nested = utf8.replacen(
        "\"model_id\": \"declawd/model-neutral-token-ids\"",
        "\"model_id\": \"declawd/model-neutral-token-ids\",\n    \"model_id\": \"declawd/model-neutral-token-ids\"",
        1,
    );
    let duplicate_expected = utf8.replacen(
        "\"status\": \"insufficient_data\"",
        "\"status\": \"insufficient_data\",\n    \"status\": \"insufficient_data\"",
        1,
    );
    let duplicate_expected_digest = utf8.replacen(
        "\"sha256\": \"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\"",
        "\"sha256\": \"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\",\n      \"sha256\": \"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\"",
        1,
    );
    let non_finite = utf8.replacen("\"token_ids\": [", "\"token_ids\": [NaN,", 1);
    let utf16_le = utf8
        .encode_utf16()
        .flat_map(u16::to_le_bytes)
        .collect::<Vec<_>>();
    let utf16_be = utf8
        .encode_utf16()
        .flat_map(u16::to_be_bytes)
        .collect::<Vec<_>>();
    let utf32_le = utf8
        .chars()
        .flat_map(|character| u32::from(character).to_le_bytes())
        .collect::<Vec<_>>();
    let utf32_be = utf8
        .chars()
        .flat_map(|character| u32::from(character).to_be_bytes())
        .collect::<Vec<_>>();
    let cases = [
        ("duplicate-top-level", duplicate_top_level.into_bytes()),
        ("duplicate-nested", duplicate_nested.into_bytes()),
        ("duplicate-expected", duplicate_expected.into_bytes()),
        (
            "duplicate-expected-digest",
            duplicate_expected_digest.into_bytes(),
        ),
        ("non-finite", non_finite.into_bytes()),
        (
            "utf8-bom",
            [b"\xef\xbb\xbf".as_slice(), source.as_slice()].concat(),
        ),
        (
            "utf16-le",
            [b"\xff\xfe".as_slice(), utf16_le.as_slice()].concat(),
        ),
        (
            "utf16-be",
            [b"\xfe\xff".as_slice(), utf16_be.as_slice()].concat(),
        ),
        (
            "utf32-le",
            [b"\xff\xfe\x00\x00".as_slice(), utf32_le.as_slice()].concat(),
        ),
        (
            "utf32-be",
            [b"\x00\x00\xfe\xff".as_slice(), utf32_be.as_slice()].concat(),
        ),
        (
            "deeply-nested",
            ["[".repeat(2_000), "0".to_owned(), "]".repeat(2_000)]
                .concat()
                .into_bytes(),
        ),
    ];
    let directory = tempdir().unwrap();
    for (name, bytes) in cases {
        let path = directory.path().join(format!("{name}.json"));
        fs::write(&path, bytes).unwrap();
        Command::cargo_bin("declawd")
            .unwrap()
            .args(["lab", "synthid", "score", path.to_str().unwrap(), "--json"])
            .assert()
            .code(2);
        let python = ProcessCommand::new("python3")
            .arg(root().join("reference/synthid_reference.py"))
            .arg(&path)
            .output()
            .unwrap();
        assert_eq!(python.status.code(), Some(2), "Python accepted {name}");
    }
}

#[test]
fn schemas_reject_impossible_expected_and_report_bounds() {
    let trace: Value =
        serde_json::from_slice(&fs::read(fixture("trace-prepared-v1.json")).unwrap()).unwrap();
    let trace_validator = validator("synthid-trace-v1.schema.json");
    let mut too_many_contexts = trace.clone();
    too_many_contexts["expected"]["candidate_context_count"] = json!(99_997);
    assert!(trace_validator.validate(&too_many_contexts).is_err());
    let mut bad_decimal = trace;
    bad_decimal["expected"]["weighted_score"]["decimal"] = json!("1.000000000001");
    assert!(trace_validator.validate(&bad_decimal).is_err());

    let output = Command::cargo_bin("declawd")
        .unwrap()
        .args([
            "lab",
            "synthid",
            "score",
            fixture("trace-prepared-v1.json").to_str().unwrap(),
            "--json",
        ])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let report: Value = serde_json::from_slice(&output).unwrap();
    let report_validator = validator("synthid-score-v1.schema.json");
    let mut oversized_digest = report.clone();
    oversized_digest["g_values"]["bit_length"] = json!(2_999_881);
    assert!(report_validator.validate(&oversized_digest).is_err());
    let mut oversized_weight = report;
    oversized_weight["weighted_g_value_sum"] = json!(478_480_861u64);
    assert!(report_validator.validate(&oversized_weight).is_err());
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

#[cfg(unix)]
#[test]
fn trace_fifos_are_refused_without_blocking() {
    use std::ffi::CString;

    let directory = tempdir().unwrap();
    let fifo = directory.path().join("trace.fifo");
    let fifo_path = CString::new(fifo.to_str().unwrap()).unwrap();
    assert_eq!(unsafe { libc::mkfifo(fifo_path.as_ptr(), 0o600) }, 0);
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", fifo.to_str().unwrap()])
        .assert()
        .code(2);
    let python = ProcessCommand::new("python3")
        .arg(root().join("reference/synthid_reference.py"))
        .arg(&fifo)
        .output()
        .unwrap();
    assert_eq!(python.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&python.stderr).contains("regular file"));
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

#[test]
fn registered_token_substitutions_have_exact_score_effects() {
    let vector: Value =
        serde_json::from_slice(&fs::read(fixture("registered-edits-v1.json")).unwrap()).unwrap();
    assert_eq!(
        vector
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect::<std::collections::BTreeSet<_>>(),
        [
            "application",
            "profile",
            "schema",
            "source",
            "source_scores",
            "substitutions"
        ]
        .into_iter()
        .map(str::to_owned)
        .collect()
    );
    assert_eq!(vector["schema"], "declawd.synthid-registered-edits/v1");
    let source_bytes = fs::read(fixture("trace-prepared-v1.json")).unwrap();
    assert_eq!(
        vector["source"]["file_sha256"],
        hex::encode(Sha256::digest(&source_bytes))
    );
    let mut source: Value = serde_json::from_slice(&source_bytes).unwrap();
    assert_eq!(vector["source"]["trace_id"], source["trace_id"]);
    source.as_object_mut().unwrap().remove("expected");
    let source_report = run_trace(&source);
    assert_eq!(
        vector["source_scores"]["raw_score"],
        source_report["raw_score"]
    );
    assert_eq!(
        vector["source_scores"]["weighted_score"],
        source_report["weighted_score"]
    );
    let source_raw = vector["source_scores"]["raw_score"]["numerator"]
        .as_i64()
        .unwrap();
    let source_weighted = vector["source_scores"]["weighted_score"]["numerator"]
        .as_i64()
        .unwrap();
    let mut ids = std::collections::BTreeSet::new();
    let mut indices = std::collections::BTreeSet::new();
    for edit in vector["substitutions"].as_array().unwrap() {
        assert_eq!(
            edit.as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>(),
            [
                "after_token_id",
                "before_token_id",
                "expected_effect",
                "id",
                "token_index"
            ]
            .into_iter()
            .map(str::to_owned)
            .collect()
        );
        assert!(ids.insert(edit["id"].as_str().unwrap()));
        let index = edit["token_index"].as_u64().unwrap() as usize;
        assert!(indices.insert(index));
        assert_eq!(source["token_ids"][index], edit["before_token_id"]);
        assert_ne!(edit["before_token_id"], edit["after_token_id"]);
        let mut changed = source.clone();
        changed["trace_id"] = json!(format!("registered-{}", edit["id"].as_str().unwrap()));
        changed["token_ids"][index] = edit["after_token_id"].clone();
        let report = run_trace(&changed);
        assert_eq!(report["raw_score"], edit["expected_effect"]["raw_score"]);
        assert_eq!(
            report["weighted_score"],
            edit["expected_effect"]["weighted_score"]
        );
        assert_eq!(
            report["raw_score"]["numerator"].as_i64().unwrap() - source_raw,
            edit["expected_effect"]["raw_numerator_delta"]
        );
        assert_eq!(
            report["weighted_score"]["numerator"].as_i64().unwrap() - source_weighted,
            edit["expected_effect"]["weighted_numerator_delta"]
        );
    }
    assert_eq!(ids.len(), 3);
    assert_eq!(indices.len(), 3);
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
        .stderr(predicate::str::contains(
            "tokenizer model_id and revision must contain 1 to 256 characters",
        ));
}

#[test]
fn lone_surrogate_metadata_is_rejected_by_both_runtimes() {
    let source = fs::read_to_string(fixture("trace-short-v1.json")).unwrap();
    let source = source.replacen(
        "declawd/model-neutral-token-ids",
        "declawd/\\ud800-tokenizer",
        1,
    );
    let directory = tempdir().unwrap();
    let path = directory.path().join("surrogate.json");
    fs::write(&path, source).unwrap();
    Command::cargo_bin("declawd")
        .unwrap()
        .args(["lab", "synthid", "score", path.to_str().unwrap()])
        .assert()
        .code(2);
    let python = ProcessCommand::new("python3")
        .arg(root().join("reference/synthid_reference.py"))
        .arg(path)
        .output()
        .unwrap();
    assert_eq!(python.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&python.stderr).contains("1 to 256 characters"));
}
