use std::collections::{BTreeMap, BTreeSet};

use declawd::{TextSelectors, clean_text, inspect_text, registry};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct VectorDocument {
    schema: String,
    registry_id: String,
    cases: Vec<InspectCase>,
    transform_cases: Vec<TransformCase>,
}

#[derive(Debug, Deserialize)]
struct InspectCase {
    id: String,
    text: String,
    expected_findings: Vec<ExpectedFinding>,
}

#[derive(Debug, Deserialize)]
struct ExpectedFinding {
    code_point: String,
    name: String,
    class: String,
    scalar_offset: usize,
    line: usize,
    column: usize,
}

#[derive(Debug, Deserialize)]
struct TransformCase {
    id: String,
    text: String,
    operations: VectorOperations,
    expected_text: String,
    expected_changed: bool,
    #[serde(default)]
    expected_findings: Vec<ExpectedTransformFinding>,
}

#[derive(Debug, Deserialize)]
struct ExpectedTransformFinding {
    code_point: String,
    class: String,
    scalar_offset: usize,
    line: usize,
    column: usize,
    disposition: String,
}

#[derive(Debug, Deserialize)]
struct VectorOperations {
    remove_classes: Vec<String>,
    remove: Vec<String>,
    replace: Vec<String>,
}

fn vectors() -> VectorDocument {
    serde_json::from_str(include_str!("../vectors/unicode-v1.json")).unwrap()
}

fn selectors(operations: &VectorOperations) -> TextSelectors {
    TextSelectors {
        remove: operations
            .remove
            .iter()
            .map(|value| declawd::unicode::parse_code_point(value).unwrap())
            .collect(),
        remove_classes: operations.remove_classes.iter().cloned().collect(),
        replacements: operations
            .replace
            .iter()
            .map(|value| {
                let (from, to) = value.split_once('=').unwrap();
                (
                    declawd::unicode::parse_code_point(from).unwrap(),
                    declawd::unicode::parse_code_point(to).unwrap(),
                )
            })
            .collect(),
    }
}

#[test]
fn registry_is_explicit_disjoint_and_has_no_format_umbrella() {
    let registry = registry();
    assert_eq!(registry.schema, "declawd.unicode-registry/v1");
    assert_eq!(registry.entries.len(), 386);
    let scalars = registry
        .entries
        .iter()
        .map(|entry| entry.scalar)
        .collect::<BTreeSet<_>>();
    assert_eq!(scalars.len(), registry.entries.len());
    let class_ids = registry
        .classes
        .iter()
        .map(|class| class.id.as_str())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        class_ids,
        BTreeSet::from([
            "bom",
            "zero-width",
            "join-control",
            "bidi-control",
            "tag-character",
            "variation-selector",
        ])
    );
    let selectable = registry
        .classes
        .iter()
        .filter(|class| class.selectable)
        .map(|class| class.id.as_str())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        selectable,
        BTreeSet::from([
            "zero-width",
            "join-control",
            "bidi-control",
            "tag-character",
            "variation-selector",
        ])
    );
    let ordered_scalars = registry
        .entries
        .iter()
        .map(|entry| entry.scalar)
        .collect::<Vec<_>>();
    assert!(ordered_scalars.windows(2).all(|pair| pair[0] < pair[1]));
    for entry in &registry.entries {
        assert_eq!(entry.code_point, format!("U+{:04X}", entry.scalar));
        assert!(class_ids.contains(entry.class.as_str()));
        assert_ne!(entry.class, "bom", "BOM is positional, not an entry class");
    }
    assert_eq!(registry.positional_rules.len(), 1);
    let bom = &registry.positional_rules[0];
    assert_eq!(bom.code_point, "U+FEFF");
    assert_eq!(bom.when.get("scalar_offset"), Some(&0));
    assert_eq!(bom.class, "bom");
    assert_eq!(bom.otherwise_class, "zero-width");
    assert!(
        registry
            .entries
            .iter()
            .any(|entry| { entry.scalar == 0xfeff && entry.class == "zero-width" })
    );
}

#[test]
fn inspection_matches_every_normative_vector() {
    let vectors = vectors();
    assert_eq!(vectors.schema, "declawd.unicode-vectors/v1");
    assert_eq!(vectors.registry_id, registry().registry_id);
    for case in vectors.cases {
        let actual = inspect_text(&case.text, false).unwrap();
        assert_eq!(actual.len(), case.expected_findings.len(), "{}", case.id);
        for (actual, expected) in actual.iter().zip(case.expected_findings) {
            assert_eq!(
                actual.code_point.as_deref(),
                Some(expected.code_point.as_str()),
                "{}",
                case.id
            );
            assert_eq!(
                actual.name.as_deref(),
                Some(expected.name.as_str()),
                "{}",
                case.id
            );
            assert_eq!(actual.class, expected.class, "{}", case.id);
            assert_eq!(
                actual.scalar_offset,
                Some(expected.scalar_offset),
                "{}",
                case.id
            );
            assert_eq!(actual.line, Some(expected.line), "{}", case.id);
            assert_eq!(actual.column, Some(expected.column), "{}", case.id);
            assert!(actual.context.is_none());
        }
    }
}

#[test]
fn transformations_match_every_normative_vector() {
    for case in vectors().transform_cases {
        let result = clean_text(&case.text, &selectors(&case.operations)).unwrap();
        assert_eq!(result.text, case.expected_text, "{}", case.id);
        assert_eq!(result.changed, case.expected_changed, "{}", case.id);
        if !case.expected_findings.is_empty() {
            assert_eq!(
                result.findings.len(),
                case.expected_findings.len(),
                "{}",
                case.id
            );
        }
        for (actual, expected) in result.findings.iter().zip(case.expected_findings.iter()) {
            assert_eq!(
                actual.code_point.as_deref(),
                Some(expected.code_point.as_str()),
                "{}",
                case.id
            );
            assert_eq!(actual.class, expected.class, "{}", case.id);
            assert_eq!(
                actual.scalar_offset,
                Some(expected.scalar_offset),
                "{}",
                case.id
            );
            assert_eq!(actual.line, Some(expected.line), "{}", case.id);
            assert_eq!(actual.column, Some(expected.column), "{}", case.id);
            assert_eq!(actual.disposition, expected.disposition, "{}", case.id);
        }
    }
}

#[test]
fn explicit_unregistered_selector_reports_scalar_positions() {
    let text = "😀a\u{202f}b\r\nc\u{202f}d\re\u{202f}f\ng\u{202f}";
    let selectors = TextSelectors {
        remove: BTreeSet::new(),
        remove_classes: BTreeSet::new(),
        replacements: BTreeMap::from([(0x202f, 0x20)]),
    };
    let result = clean_text(text, &selectors).unwrap();
    let positions = result
        .findings
        .iter()
        .map(|finding| {
            (
                finding.scalar_offset.unwrap(),
                finding.line.unwrap(),
                finding.column.unwrap(),
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(
        positions,
        vec![(2, 1, 3), (7, 2, 2), (11, 3, 2), (15, 4, 2)]
    );
    assert_eq!(result.text, "😀a b\r\nc d\re f\ng ");
}

#[test]
fn explicit_lf_in_crlf_uses_the_pre_break_scalar_column() {
    let selectors = TextSelectors {
        remove: BTreeSet::from([0x000a]),
        remove_classes: BTreeSet::new(),
        replacements: BTreeMap::new(),
    };
    let result = clean_text("a\r\nb", &selectors).unwrap();
    assert_eq!(result.text, "a\rb");
    assert_eq!(result.findings.len(), 1);
    assert_eq!(result.findings[0].scalar_offset, Some(2));
    assert_eq!(result.findings[0].line, Some(1));
    assert_eq!(result.findings[0].column, Some(3));
}

#[test]
fn include_context_is_bounded_to_32_scalars() {
    let text = format!("{}\u{200b}{}", "a".repeat(40), "b".repeat(40));
    let finding = inspect_text(&text, true).unwrap().pop().unwrap();
    let context = finding.context.unwrap();
    assert_eq!(context.before.chars().count(), 32);
    assert_eq!(context.after.chars().count(), 32);
}

#[test]
fn selector_conflicts_and_identity_replacements_are_refused() {
    let conflict = TextSelectors {
        remove: BTreeSet::from([0x200b]),
        remove_classes: BTreeSet::new(),
        replacements: BTreeMap::from([(0x200b, 0x20)]),
    };
    assert!(
        conflict
            .validate()
            .unwrap_err()
            .contains("both removed and replaced")
    );
    let identity = TextSelectors {
        remove: BTreeSet::new(),
        remove_classes: BTreeSet::new(),
        replacements: BTreeMap::from([(0x202f, 0x202f)]),
    };
    assert!(
        identity
            .validate()
            .unwrap_err()
            .contains("replaced with itself")
    );
    let target_removed = TextSelectors {
        remove: BTreeSet::from([0x200b]),
        remove_classes: BTreeSet::new(),
        replacements: BTreeMap::from([(0x202f, 0x200b)]),
    };
    assert!(
        target_removed
            .validate()
            .unwrap_err()
            .contains("replacement target U+200B")
    );
    let target_class_removed = TextSelectors {
        remove: BTreeSet::new(),
        remove_classes: BTreeSet::from(["zero-width".to_owned()]),
        replacements: BTreeMap::from([(0x202f, 0x200b)]),
    };
    assert!(
        target_class_removed
            .validate()
            .unwrap_err()
            .contains("replacement target U+200B")
    );
}
