/* SARIF 2.1.0 output for `inspect`, so a finding can be read by the code
scanning tools a repository already runs.

Two things about this conversion are deliberate.

The report carries no path. `Artifact` is a media type, a byte length and a
SHA-256, and nothing else, because a report describes bytes rather than a
place on somebody's disk. SARIF results need a location, so the caller
supplies the one it was invoked with. That is the invocation's knowledge,
not the report's.

And a run that finds nothing is not a run that verified anything. Declawd
reads an explicit registry of Unicode carriers and embedded C2PA stores; it
does not read statistical token-choice watermarks, and there is no provider
verifier behind it. An empty SARIF file rendered in a security dashboard
reads as a clean bill of health, so every untested channel is emitted as a
`notApplicable` result and the invocation carries the same statement in its
notifications. The reader is told what was not looked at, in the same file
that tells them what was. Viewers may omit these informational results; the
raw SARIF and a CI summary must remain available. */
use serde_json::{Value, json};
use std::fmt::Write;
use std::path::Path;

use crate::report::{Finding, Report};

const SARIF_VERSION: &str = "2.1.0";
const SARIF_SCHEMA: &str = "https://json.schemastore.org/sarif-2.1.0.json";
const INFORMATION_URI: &str = "https://github.com/san-digital/declawd";

fn rule_id(finding: &Finding) -> String {
    format!("{}/{}", finding.carrier, finding.class)
}

fn rule_description(carrier: &str, class: &str) -> String {
    match (carrier, class) {
        ("embedded-c2pa", _) => "An embedded C2PA/JUMBF store is present in this file.".to_owned(),
        (_, class) => format!(
            "A registered {class} Unicode carrier is present in this text. \
             Its presence is not evidence that a model wrote the text."
        ),
    }
}

/// Convert a filesystem path to an escaped URI reference. Explicit SARIF URI
/// overrides bypass this conversion and must already be valid URI references.
pub fn path_uri(path: &Path) -> String {
    #[cfg(windows)]
    let normalised = path.to_string_lossy().replace('\\', "/");
    #[cfg(windows)]
    let normalised = if let Some(unc) = normalised.strip_prefix("//?/UNC/") {
        format!("//{unc}")
    } else {
        normalised
            .strip_prefix("//?/")
            .unwrap_or(&normalised)
            .to_owned()
    };
    #[cfg(windows)]
    let bytes = normalised.as_bytes();
    #[cfg(not(windows))]
    let bytes = path.as_os_str().as_encoded_bytes();

    let mut uri = String::new();
    if path.is_absolute() {
        #[cfg(not(windows))]
        uri.push_str("file://");
        #[cfg(windows)]
        uri.push_str(if bytes.starts_with(b"//") {
            "file:"
        } else {
            "file:///"
        });
    }
    for (index, byte) in bytes.iter().copied().enumerate() {
        let drive_colon = cfg!(windows) && path.is_absolute() && index == 1 && byte == b':';
        if byte.is_ascii_alphanumeric() || b"-._~/".contains(&byte) || drive_colon {
            uri.push(char::from(byte));
        } else {
            write!(uri, "%{byte:02X}").expect("writing to a string cannot fail");
        }
    }
    uri
}

fn region(finding: &Finding, leading_bom: bool) -> Option<Value> {
    // SARIF positions exclude a leading BOM. The report contract includes it,
    // so keep the BOM itself at artifact level and adjust subsequent positions.
    if leading_bom && finding.scalar_offset == Some(0) {
        return None;
    }
    let mut region = json!({});
    if let Some(line) = finding.line {
        region["startLine"] = json!(line);
    }
    if let Some(column) = finding.column {
        let column = column - usize::from(leading_bom && finding.line == Some(1));
        region["startColumn"] = json!(column);
        region["endColumn"] = json!(column + 1);
    }
    if let Some(offset) = finding.scalar_offset {
        region["charOffset"] = json!(offset - usize::from(leading_bom));
        region["charLength"] = json!(1);
    }
    // A C2PA store length does not identify its position in the container.
    // Without a byte offset there is no valid binary region to report.
    if region.as_object().is_some_and(|fields| fields.is_empty()) {
        return None;
    }
    Some(region)
}

fn message(finding: &Finding) -> String {
    match (&finding.code_point, &finding.name) {
        (Some(code_point), Some(name)) => {
            format!("{code_point} {name} ({}) is present.", finding.class)
        }
        _ => format!(
            "A {} {} carrier is present.",
            finding.carrier, finding.class
        ),
    }
}

/// Render an inspection report as SARIF 2.1.0. `uri` is the location the tool
/// was pointed at, which the report itself does not record.
pub fn to_sarif(report: &Report, uri: &str) -> Value {
    let leading_bom = report.findings.iter().any(|finding| {
        finding.scalar_offset == Some(0) && finding.code_point.as_deref() == Some("U+FEFF")
    });
    let mut rules: Vec<Value> = Vec::new();
    let mut seen: Vec<String> = Vec::new();
    for finding in &report.findings {
        let id = rule_id(finding);
        if seen.contains(&id) {
            continue;
        }
        seen.push(id.clone());
        rules.push(json!({
            "id": id,
            "name": format!("{}{}", finding.carrier, finding.class),
            "shortDescription": { "text": format!("Registered {} carrier", finding.class) },
            "fullDescription": { "text": rule_description(&finding.carrier, &finding.class) },
            "defaultConfiguration": { "level": "none" },
            "helpUri": INFORMATION_URI,
            "help": {
                "text": "Declawd reports an explicit registry of carriers. A finding is not \
                         evidence that AI was involved, and this tool does not detect or \
                         certify removal of Claude's watermark.",
            },
        }));
    }

    let results: Vec<Value> = report
        .findings
        .iter()
        .map(|finding| {
            let mut location = json!({
                "physicalLocation": {
                    "artifactLocation": { "uri": uri, "index": 0 },
                },
            });
            if let Some(region) = region(finding, leading_bom) {
                location["physicalLocation"]["region"] = region;
            }
            json!({
                "ruleId": rule_id(finding),
                "level": "none",
                // Not a defect: a carrier is something a person has to look at.
                "kind": "review",
                "message": { "text": message(finding) },
                "locations": [location],
            })
        })
        // Every channel this run did not read, said out loud rather than left
        // to an empty results array.
        .chain(report.untested_channels.iter().map(|channel| {
            json!({
                "ruleId": "declawd/untested-channel",
                "level": "none",
                "kind": "notApplicable",
                "message": { "text": format!("Not tested by this run: {channel}.") },
                "locations": [{
                    "physicalLocation": { "artifactLocation": { "uri": uri, "index": 0 } },
                }],
            })
        }))
        .collect();

    if !report.untested_channels.is_empty() {
        rules.push(json!({
            "id": "declawd/untested-channel",
            "name": "untestedChannel",
            "shortDescription": { "text": "A channel this run did not read" },
            "fullDescription": {
                "text": "Declawd reads a registry of Unicode carriers and embedded C2PA stores. \
                         Anything listed here was not examined, so no result about it can be \
                         drawn from this run.",
            },
            "defaultConfiguration": { "level": "none" },
            "helpUri": INFORMATION_URI,
        }));
    }

    let mut notifications: Vec<Value> = report
        .warnings
        .iter()
        .map(|warning| json!({ "level": "note", "message": { "text": warning } }))
        .collect();
    notifications.push(json!({
        "level": "note",
        "message": {
            "text": "No provider verifier ran. This run reports the carriers it reads and \
                     verifies nothing about any vendor's watermark, so an absence of results \
                     is not a verified result.",
        },
    }));
    notifications.extend(report.untested_channels.iter().map(|channel| {
        json!({ "level": "note", "message": { "text": format!("Not tested by this run: {channel}.") } })
    }));

    let mut sarif = json!({
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": "declawd",
                    "version": report.tool_version,
                    "informationUri": INFORMATION_URI,
                    "rules": rules,
                },
            },
            "invocations": [{
                "executionSuccessful": true,
                "toolExecutionNotifications": notifications,
            }],
            "artifacts": [{
                "location": { "uri": uri },
                "length": report.input.byte_length,
                "mimeType": report.input.media_type,
                "hashes": { "sha-256": report.input.sha256 },
            }],
            "results": results,
        }],
    });
    if report.input.media_type.starts_with("text/") {
        sarif["runs"][0]["columnKind"] = json!("unicodeCodePoints");
        sarif["runs"][0]["defaultEncoding"] = json!("utf-8");
        sarif["runs"][0]["newlineSequences"] = json!(["\r\n", "\r", "\n"]);
    }
    sarif
}

#[cfg(all(test, windows))]
mod windows_tests {
    use super::path_uri;
    use std::path::Path;

    #[test]
    fn drive_and_unc_paths_are_file_uris() {
        for path in [r"C:\a b.txt", r"\\?\C:\a b.txt"] {
            assert_eq!(path_uri(Path::new(path)), "file:///C:/a%20b.txt");
        }
        for path in [r"\\server\share\a b.txt", r"\\?\UNC\server\share\a b.txt"] {
            assert_eq!(path_uri(Path::new(path)), "file://server/share/a%20b.txt");
        }
    }
}
