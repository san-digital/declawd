use serde::{Deserialize, Serialize};

pub const REPORT_SCHEMA: &str = "declawd.report/v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Artifact {
    pub media_type: String,
    pub byte_length: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Context {
    pub before: String,
    pub character: String,
    pub after: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Finding {
    pub carrier: String,
    pub class: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_point: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scalar_offset: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub column: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub byte_length: Option<u64>,
    pub disposition: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<Context>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Action {
    pub action: String,
    pub selector: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub replacement: Option<String>,
    pub matches: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct Verification {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub supported_carriers_remaining: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub embedded_c2pa_absent: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub non_c2pa_bytes_unchanged: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub compressed_image_data_unchanged: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub byte_identical_copy: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Report {
    pub schema: String,
    pub tool_version: String,
    pub operation: String,
    pub changed: bool,
    pub input: Artifact,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output: Option<Artifact>,
    pub findings: Vec<Finding>,
    pub requested_actions: Vec<Action>,
    pub completed_actions: Vec<Action>,
    pub verification: Verification,
    pub untested_channels: Vec<String>,
    pub warnings: Vec<String>,
}

impl Report {
    pub fn new(operation: &str, input: Artifact) -> Self {
        Self {
            schema: REPORT_SCHEMA.to_owned(),
            tool_version: env!("CARGO_PKG_VERSION").to_owned(),
            operation: operation.to_owned(),
            changed: false,
            input,
            output: None,
            findings: Vec::new(),
            requested_actions: Vec::new(),
            completed_actions: Vec::new(),
            verification: Verification::default(),
            untested_channels: vec![
                "statistical token-choice watermarks".to_owned(),
                "pixel-level or perceptual watermarks".to_owned(),
            ],
            warnings: vec![
                "A finding is not evidence that AI was involved.".to_owned(),
                "This tool does not detect or certify removal of Claude's watermark.".to_owned(),
            ],
        }
    }
}
