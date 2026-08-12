use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

use crate::report::{Action, Context, Finding};

pub const REGISTRY_SCHEMA: &str = "declawd.unicode-registry/v1";
pub const MAX_FINDINGS: usize = 10_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistryClass {
    pub id: String,
    pub selectable: bool,
    pub description: String,
    pub warning: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistryEntry {
    pub code_point: String,
    pub scalar: u32,
    pub name: String,
    pub class: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PositionalRule {
    pub code_point: String,
    pub when: BTreeMap<String, usize>,
    pub class: String,
    pub otherwise_class: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PositionModel {
    pub scalar_offset: String,
    pub line: String,
    pub column: String,
    pub newline_position: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnicodeRegistry {
    pub schema: String,
    pub registry_id: String,
    pub unicode_names_from: String,
    pub classes: Vec<RegistryClass>,
    pub positional_rules: Vec<PositionalRule>,
    pub position_model: PositionModel,
    pub entries: Vec<RegistryEntry>,
}

struct RegistryIndex {
    document: UnicodeRegistry,
    by_scalar: HashMap<u32, usize>,
    selectable_classes: BTreeSet<String>,
}

fn index() -> &'static RegistryIndex {
    static INDEX: OnceLock<RegistryIndex> = OnceLock::new();
    INDEX.get_or_init(|| {
        let document: UnicodeRegistry =
            serde_json::from_str(include_str!("../spec/unicode-registry-v1.json"))
                .expect("the embedded Unicode registry must be valid JSON");
        assert_eq!(document.schema, REGISTRY_SCHEMA);
        let by_scalar = document
            .entries
            .iter()
            .enumerate()
            .map(|(position, entry)| (entry.scalar, position))
            .collect::<HashMap<_, _>>();
        assert_eq!(by_scalar.len(), document.entries.len());
        let selectable_classes = document
            .classes
            .iter()
            .filter(|class| class.selectable)
            .map(|class| class.id.clone())
            .collect();
        RegistryIndex {
            document,
            by_scalar,
            selectable_classes,
        }
    })
}

pub fn registry() -> &'static UnicodeRegistry {
    &index().document
}

pub fn parse_code_point(value: &str) -> Result<u32, String> {
    let Some(hex) = value
        .strip_prefix("U+")
        .or_else(|| value.strip_prefix("u+"))
    else {
        return Err(format!("expected U+XXXX, got {value:?}"));
    };
    if !(4..=6).contains(&hex.len()) || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(format!("expected U+XXXX, got {value:?}"));
    }
    let scalar =
        u32::from_str_radix(hex, 16).map_err(|_| format!("invalid code point {value:?}"))?;
    if char::from_u32(scalar).is_none() {
        return Err(format!("not a Unicode scalar value: {value:?}"));
    }
    Ok(scalar)
}

pub fn format_code_point(scalar: u32) -> String {
    format!("U+{scalar:04X}")
}

fn registry_entry(scalar: u32) -> Option<&'static RegistryEntry> {
    index()
        .by_scalar
        .get(&scalar)
        .map(|position| &index().document.entries[*position])
}

pub fn is_registered_scalar(scalar: u32) -> bool {
    registry_entry(scalar).is_some()
}

fn normative_class(scalar: u32, scalar_offset: usize) -> Option<&'static str> {
    if scalar == 0xfeff && scalar_offset == 0 {
        return Some("bom");
    }
    registry_entry(scalar).map(|entry| entry.class.as_str())
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TextSelectors {
    pub remove: BTreeSet<u32>,
    pub remove_classes: BTreeSet<String>,
    pub replacements: BTreeMap<u32, u32>,
}

impl TextSelectors {
    pub fn validate(&self) -> Result<(), String> {
        if self.remove.is_empty() && self.remove_classes.is_empty() && self.replacements.is_empty()
        {
            return Err(
                "at least one --remove, --remove-class or --replace selector is required"
                    .to_owned(),
            );
        }
        for class in &self.remove_classes {
            if !index().selectable_classes.contains(class) {
                let allowed = index()
                    .selectable_classes
                    .iter()
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(", ");
                return Err(format!(
                    "class {class:?} is not selectable; selectable classes: {allowed}"
                ));
            }
        }
        for (scalar, target) in &self.replacements {
            if scalar == target {
                return Err(format!(
                    "{} cannot be replaced with itself",
                    format_code_point(*scalar)
                ));
            }
            if self.remove.contains(scalar) {
                return Err(format!(
                    "{} cannot be both removed and replaced",
                    format_code_point(*scalar)
                ));
            }
            if let Some(entry) = registry_entry(*scalar)
                && self.remove_classes.contains(&entry.class)
            {
                return Err(format!(
                    "{} cannot be replaced while class {:?} is removed",
                    entry.code_point, entry.class
                ));
            }
            let target_class = registry_entry(*target).map(|entry| entry.class.as_str());
            if self.remove.contains(target)
                || self.replacements.contains_key(target)
                || target_class.is_some_and(|class| self.remove_classes.contains(class))
            {
                return Err(format!(
                    "replacement target {} is also selected for removal or replacement",
                    format_code_point(*target)
                ));
            }
        }
        Ok(())
    }
}

pub fn selected_count(text: &str, selectors: &TextSelectors) -> usize {
    text.chars()
        .enumerate()
        .filter(|(offset, character)| {
            let scalar = *character as u32;
            selectors.remove.contains(&scalar)
                || selectors.replacements.contains_key(&scalar)
                || normative_class(scalar, *offset)
                    .is_some_and(|class| selectors.remove_classes.contains(class))
        })
        .count()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TextCleanResult {
    pub text: String,
    pub changed: bool,
    pub findings: Vec<Finding>,
    pub requested_actions: Vec<Action>,
    pub completed_actions: Vec<Action>,
}

fn context(chars: &[char], offset: usize) -> Context {
    let start = offset.saturating_sub(32);
    let end = (offset + 33).min(chars.len());
    Context {
        before: chars[start..offset].iter().collect(),
        character: chars[offset].to_string(),
        after: chars[offset + 1..end].iter().collect(),
    }
}

pub fn inspect_text(text: &str, include_context: bool) -> Result<Vec<Finding>, String> {
    let chars = text.chars().collect::<Vec<_>>();
    let mut findings = Vec::new();
    let mut line = 1usize;
    let mut column = 1usize;
    let mut previous_was_cr = false;

    for (scalar_offset, character) in chars.iter().copied().enumerate() {
        if previous_was_cr && character != '\n' {
            line += 1;
            column = 1;
        }
        let scalar = character as u32;
        if let Some(class) = normative_class(scalar, scalar_offset) {
            let entry = registry_entry(scalar).expect("classified scalars have registry entries");
            findings.push(Finding {
                carrier: "unicode".to_owned(),
                class: class.to_owned(),
                code_point: Some(entry.code_point.clone()),
                name: Some(entry.name.clone()),
                scalar_offset: Some(scalar_offset),
                line: Some(line),
                column: Some(column),
                byte_length: None,
                disposition: "reported".to_owned(),
                context: include_context.then(|| context(&chars, scalar_offset)),
            });
            if findings.len() > MAX_FINDINGS {
                return Err(format!(
                    "input contains more than {MAX_FINDINGS} supported Unicode findings; refusing an unbounded report"
                ));
            }
        }

        match character {
            '\r' => {
                column += 1;
                previous_was_cr = true;
            }
            '\n' => {
                line += 1;
                column = 1;
                previous_was_cr = false;
            }
            _ => {
                column += 1;
                previous_was_cr = false;
            }
        }
    }
    Ok(findings)
}

fn scalar_positions(text: &str) -> Vec<(usize, usize)> {
    let mut positions = Vec::with_capacity(text.chars().count());
    let mut line = 1usize;
    let mut column = 1usize;
    let mut previous_was_cr = false;
    for character in text.chars() {
        if previous_was_cr && character != '\n' {
            line += 1;
            column = 1;
        }
        positions.push((line, column));
        match character {
            '\r' => {
                column += 1;
                previous_was_cr = true;
            }
            '\n' => {
                line += 1;
                column = 1;
                previous_was_cr = false;
            }
            _ => {
                column += 1;
                previous_was_cr = false;
            }
        }
    }
    positions
}

pub fn clean_text(text: &str, selectors: &TextSelectors) -> Result<TextCleanResult, String> {
    selectors.validate()?;
    let inspected = inspect_text(text, false)?;
    let positions = inspected
        .iter()
        .filter_map(|finding| {
            finding
                .scalar_offset
                .map(|offset| (offset, finding.clone()))
        })
        .collect::<HashMap<_, _>>();
    let all_positions = scalar_positions(text);

    let mut remove_matches = selectors
        .remove
        .iter()
        .map(|scalar| (*scalar, 0usize))
        .collect::<BTreeMap<_, _>>();
    let mut class_matches = selectors
        .remove_classes
        .iter()
        .map(|class| (class.clone(), 0usize))
        .collect::<BTreeMap<_, _>>();
    let mut replace_matches = selectors
        .replacements
        .keys()
        .map(|scalar| (*scalar, 0usize))
        .collect::<BTreeMap<_, _>>();
    let mut findings = Vec::new();
    let mut output = String::with_capacity(text.len());

    for (scalar_offset, character) in text.chars().enumerate() {
        let scalar = character as u32;
        let class = normative_class(scalar, scalar_offset);
        let replacement = selectors.replacements.get(&scalar).copied();
        let remove_explicitly = selectors.remove.contains(&scalar);
        let remove_by_class = class.is_some_and(|id| selectors.remove_classes.contains(id));
        let disposition = if remove_explicitly || remove_by_class {
            if remove_explicitly {
                *remove_matches
                    .get_mut(&scalar)
                    .expect("selector was initialised") += 1;
            }
            if let Some(id) = class
                && remove_by_class
            {
                *class_matches.get_mut(id).expect("selector was initialised") += 1;
            }
            "removed"
        } else if let Some(target) = replacement {
            *replace_matches
                .get_mut(&scalar)
                .expect("selector was initialised") += 1;
            output.push(char::from_u32(target).expect("validated replacement scalar"));
            "replaced"
        } else {
            output.push(character);
            "preserved"
        };

        if disposition != "preserved" {
            let mut finding = positions.get(&scalar_offset).cloned().unwrap_or(Finding {
                carrier: "unicode".to_owned(),
                class: "explicit-code-point".to_owned(),
                code_point: Some(format_code_point(scalar)),
                name: None,
                scalar_offset: Some(scalar_offset),
                line: Some(all_positions[scalar_offset].0),
                column: Some(all_positions[scalar_offset].1),
                byte_length: None,
                disposition: String::new(),
                context: None,
            });
            finding.disposition = disposition.to_owned();
            findings.push(finding);
            if findings.len() > MAX_FINDINGS {
                return Err(format!(
                    "selection matches more than {MAX_FINDINGS} Unicode scalars; split the input or narrow the selectors"
                ));
            }
        }
    }

    let requested_actions = actions(&remove_matches, &class_matches, &replace_matches, selectors);
    let completed_actions = requested_actions
        .iter()
        .filter(|action| action.matches > 0)
        .cloned()
        .collect();
    let changed = output != text;
    Ok(TextCleanResult {
        text: output,
        changed,
        findings,
        requested_actions,
        completed_actions,
    })
}

fn actions(
    remove_matches: &BTreeMap<u32, usize>,
    class_matches: &BTreeMap<String, usize>,
    replace_matches: &BTreeMap<u32, usize>,
    selectors: &TextSelectors,
) -> Vec<Action> {
    let mut actions = Vec::new();
    for (scalar, matches) in remove_matches {
        actions.push(Action {
            action: "remove-code-point".to_owned(),
            selector: format_code_point(*scalar),
            replacement: None,
            matches: *matches,
        });
    }
    for (class, matches) in class_matches {
        actions.push(Action {
            action: "remove-class".to_owned(),
            selector: class.clone(),
            replacement: None,
            matches: *matches,
        });
    }
    for (scalar, matches) in replace_matches {
        actions.push(Action {
            action: "replace-code-point".to_owned(),
            selector: format_code_point(*scalar),
            replacement: selectors
                .replacements
                .get(scalar)
                .map(|target| format_code_point(*target)),
            matches: *matches,
        });
    }
    actions
}
