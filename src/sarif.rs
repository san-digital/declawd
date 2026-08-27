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
that tells them what was. */
use serde_json::{Value, json};

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

fn region(finding: &Finding) -> Option<Value> {
    let mut region = json!({});
    if let Some(line) = finding.line {
        region["startLine"] = json!(line);
    }
    if let Some(column) = finding.column {
        region["startColumn"] = json!(column);
    }
    /* charOffset counts Unicode scalars, which is what scalar_offset holds and
    what SARIF means by a character. byte_length is bytes and belongs to the
    byte-oriented pair, so it is reported as byteLength rather than being
    mixed into a character region. */
    if let Some(offset) = finding.scalar_offset {
        region["charOffset"] = json!(offset);
        region["charLength"] = json!(1);
    }
    if let Some(length) = finding.byte_length {
        region["byteLength"] = json!(length);
    }
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
            "defaultConfiguration": { "level": "note" },
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
            if let Some(region) = region(finding) {
                location["physicalLocation"]["region"] = region;
            }
            json!({
                "ruleId": rule_id(finding),
                "level": "note",
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

    json!({
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
    })
}
