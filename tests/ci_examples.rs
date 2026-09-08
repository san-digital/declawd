#![cfg(unix)]

use std::fs;
use std::path::Path;
use std::process::{Command, Output};

use serde_json::Value;
use tempfile::tempdir;

fn git(directory: &Path, args: &[&str]) -> Output {
    let output = Command::new("git")
        .current_dir(directory)
        .args([
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
        ])
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

fn command(program: &str, directory: &Path) -> Command {
    let mut paths = vec![
        assert_cmd::cargo::cargo_bin("declawd")
            .parent()
            .unwrap()
            .to_owned(),
    ];
    paths.extend(std::env::split_paths(&std::env::var_os("PATH").unwrap()));
    let mut command = Command::new(program);
    command
        .current_dir(directory)
        .env("PATH", std::env::join_paths(paths).unwrap());
    command
}

#[test]
fn hook_reads_staged_names_and_content_even_when_working_file_is_absent() {
    let directory = tempdir().unwrap();
    git(directory.path(), &["init", "-q"]);
    let file = "space and\nnewline.txt";
    fs::write(directory.path().join(file), "a\u{200b}").unwrap();
    git(directory.path(), &["add", "--", file]);
    fs::remove_file(directory.path().join(file)).unwrap();
    let hook = Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/ci/pre-commit-hook.sh");
    let result = command("bash", directory.path())
        .arg(&hook)
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stdout).contains("registered carriers"));

    fs::write(directory.path().join(file), "plain staged text").unwrap();
    git(directory.path(), &["add", "--", file]);
    fs::write(directory.path().join(file), "a\u{200b}").unwrap();
    assert!(
        command("bash", directory.path())
            .arg(hook)
            .status()
            .unwrap()
            .success()
    );
}

#[test]
fn hook_identifies_input_failures_separately_from_carriers() {
    let directory = tempdir().unwrap();
    git(directory.path(), &["init", "-q"]);
    fs::write(directory.path().join("invalid.txt"), [0xff, 0xfe]).unwrap();
    git(directory.path(), &["add", "invalid.txt"]);
    let hook = Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/ci/pre-commit-hook.sh");
    let result = command("bash", directory.path())
        .arg(hook)
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    let stdout = String::from_utf8_lossy(&result.stdout);
    assert!(stdout.contains("could not inspect staged content"));
    assert!(!stdout.contains("registered carriers in"));
}

#[test]
fn ci_helper_combines_artifact_locations_and_preserves_notifications() {
    let directory = tempdir().unwrap();
    git(directory.path(), &["init", "-q"]);
    git(
        directory.path(),
        &["commit", "--allow-empty", "-qm", "baseline"],
    );
    fs::create_dir(directory.path().join("a")).unwrap();
    for file in ["a_b.txt", "a/b.txt", "space and\nnewline.txt"] {
        fs::write(directory.path().join(file), "a\u{200b}").unwrap();
    }
    fs::write(directory.path().join("z-bom.txt"), "\u{feff}a\u{200b}").unwrap();
    git(directory.path(), &["add", "."]);
    git(directory.path(), &["commit", "-qm", "text"]);
    let helper = Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/ci/inspect-changed.py");
    let result = command("python3", directory.path())
        .arg(helper)
        .args(["--base-ref", "HEAD~1", "--output", "out.sarif"])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let sarif: Value =
        serde_json::from_slice(&fs::read(directory.path().join("out.sarif")).unwrap()).unwrap();
    assert_eq!(sarif["runs"].as_array().unwrap().len(), 1);
    let run = &sarif["runs"][0];
    assert_eq!(run["artifacts"].as_array().unwrap().len(), 4);
    for result in run["results"].as_array().unwrap() {
        let location = &result["locations"][0]["physicalLocation"]["artifactLocation"];
        let index = location["index"].as_u64().unwrap() as usize;
        assert_eq!(location["uri"], run["artifacts"][index]["location"]["uri"]);
    }
    assert!(
        run["invocations"][0]["toolExecutionNotifications"]
            .as_array()
            .unwrap()
            .iter()
            .any(|note| note["message"]["text"]
                .as_str()
                .unwrap()
                .contains("leading UTF-8 BOM"))
    );
}

#[test]
fn ci_helper_has_no_upload_when_no_text_changed_and_does_not_hide_git_errors() {
    let directory = tempdir().unwrap();
    git(directory.path(), &["init", "-q"]);
    git(
        directory.path(),
        &["commit", "--allow-empty", "-qm", "baseline"],
    );
    let helper = Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/ci/inspect-changed.py");
    fs::write(directory.path().join("out.sarif"), "stale report").unwrap();
    let result = command("python3", directory.path())
        .arg(&helper)
        .args(["--base-ref", "HEAD", "--output", "out.sarif"])
        .output()
        .unwrap();
    assert!(result.status.success());
    assert!(!directory.path().join("out.sarif").exists());
    assert!(
        !command("python3", directory.path())
            .arg(helper)
            .args(["--base-ref", "missing-ref", "--output", "out.sarif"])
            .output()
            .unwrap()
            .status
            .success()
    );
}
