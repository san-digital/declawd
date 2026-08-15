//! Exact, educational scoring for the public SynthID-Text reference profile.
//!
//! This module reproduces a small, pinned part of DeepMind's public 0.2.1
//! reference implementation. It does not implement Anthropic's production
//! watermark, a detector threshold or an authorship decision.

use std::collections::{HashMap, VecDeque};
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

pub const TRACE_LIMIT: u64 = 8 * 1024 * 1024;
pub const TOKEN_LIMIT: usize = 100_000;
pub const PROFILE_ID: &str = "declawd.synthid-profile/v1";
pub const PROFILE_SHA256: &str = "3fcb8947cc6e267a653196571d9e43434de405b2977838cf95167c94c0ac8e08";
pub const TRACE_SCHEMA: &str = "declawd.synthid-trace/v1";
pub const SCORE_SCHEMA: &str = "declawd.synthid-score/v1";
pub const TOKEN_ID_MAX: u32 = i32::MAX as u32;

const WARNINGS: [&str; 2] = [
    "public-reference-profile-only",
    "no-detector-threshold-or-authorship-verdict",
];

const NGRAM_LEN: usize = 5;
const DEPTH: usize = 30;
const CONTEXT_HISTORY_SIZE: usize = 1024;
const TABLE_SIZE: usize = 65_536;
const HASH_MULTIPLIER: i64 = 6_364_136_223_846_793_005;
const HASH_INCREMENT: i64 = 1;
const WEIGHT_SUM: u64 = 4_785;
const KEYS: [i64; DEPTH] = [
    654, 400, 836, 123, 340, 443, 597, 160, 57, 29, 590, 639, 13, 715, 468, 990, 966, 226, 324,
    585, 118, 504, 421, 521, 129, 669, 732, 225, 90, 960,
];
const SAMPLING_TABLE: &[u8; TABLE_SIZE / 8] =
    include_bytes!("../fixtures/synthid/sampling-table-v1.bin");

#[derive(Debug, Error)]
pub enum SynthIdError {
    #[error("{0}")]
    Input(String),
    #[error("{0}")]
    ExpectedMismatch(String),
}

impl SynthIdError {
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::Input(_) => 2,
            Self::ExpectedMismatch(_) => 3,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SynthIdTrace {
    pub schema: String,
    pub trace_id: String,
    pub profile: ProfileReference,
    pub sequence_role: String,
    pub tokenizer: TokenizerReference,
    pub token_ids: Vec<u32>,
    #[serde(default)]
    pub expected: Option<ExpectedScore>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProfileReference {
    pub id: String,
    pub file_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TokenizerReference {
    pub model_id: String,
    pub revision: String,
    pub eos_token_id: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExpectedScore {
    pub status: ScoreStatus,
    pub token_count: u64,
    pub candidate_context_count: u64,
    pub first_eos_index: Option<u64>,
    pub repetition_excluded_count: u64,
    pub eos_excluded_count: u64,
    pub valid_context_count: u64,
    pub g_value_one_count: u64,
    pub weighted_g_value_sum: u64,
    pub g_values: BitDigest,
    pub masks: ScoreMasks,
    pub raw_score: Option<ExactScore>,
    pub weighted_score: Option<ExactScore>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreStatus {
    Scored,
    InsufficientData,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BitDigest {
    pub bit_length: u64,
    pub byte_length: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ScoreMasks {
    pub repetition: BitDigest,
    pub eos: BitDigest,
    pub valid: BitDigest,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExactScore {
    pub numerator: u64,
    pub denominator: u64,
    pub decimal: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ScoreReport {
    pub schema: &'static str,
    pub trace_id: String,
    pub profile: ProfileReference,
    pub trace_sha256: String,
    pub status: ScoreStatus,
    pub token_count: u64,
    pub candidate_context_count: u64,
    pub first_eos_index: Option<u64>,
    pub repetition_excluded_count: u64,
    pub eos_excluded_count: u64,
    pub valid_context_count: u64,
    pub g_value_one_count: u64,
    pub weighted_g_value_sum: u64,
    pub g_values: BitDigest,
    pub masks: ScoreMasks,
    pub raw_score: Option<ExactScore>,
    pub weighted_score: Option<ExactScore>,
    pub warnings: Vec<&'static str>,
}

impl ScoreReport {
    fn expected(&self) -> ExpectedScore {
        ExpectedScore {
            status: self.status,
            token_count: self.token_count,
            candidate_context_count: self.candidate_context_count,
            first_eos_index: self.first_eos_index,
            repetition_excluded_count: self.repetition_excluded_count,
            eos_excluded_count: self.eos_excluded_count,
            valid_context_count: self.valid_context_count,
            g_value_one_count: self.g_value_one_count,
            weighted_g_value_sum: self.weighted_g_value_sum,
            g_values: self.g_values.clone(),
            masks: self.masks.clone(),
            raw_score: self.raw_score.clone(),
            weighted_score: self.weighted_score.clone(),
        }
    }
}

pub fn score_trace_file(path: &Path) -> Result<ScoreReport, SynthIdError> {
    let bytes = read_trace(path)?;
    let trace: SynthIdTrace = serde_json::from_slice(&bytes)
        .map_err(|error| SynthIdError::Input(format!("invalid trace JSON: {error}")))?;
    let expected = trace.expected.clone();
    let report = score_trace(&trace, &bytes)?;
    if let Some(expected) = expected
        && expected != report.expected()
    {
        return Err(SynthIdError::ExpectedMismatch(
            "trace expected result does not match the computed score".to_owned(),
        ));
    }
    Ok(report)
}

pub fn score_trace(trace: &SynthIdTrace, source_bytes: &[u8]) -> Result<ScoreReport, SynthIdError> {
    validate_trace(trace)?;
    let token_count = trace.token_ids.len();
    let candidate_context_count = token_count.saturating_sub(NGRAM_LEN - 1);
    let mut repetition = Vec::with_capacity(candidate_context_count);
    let mut eos = Vec::with_capacity(candidate_context_count);
    let mut valid = Vec::with_capacity(candidate_context_count);
    let mut g_values = Vec::with_capacity(candidate_context_count * DEPTH);
    let mut history = VecDeque::from(vec![0i64; CONTEXT_HISTORY_SIZE]);
    let mut history_counts = HashMap::from([(0i64, CONTEXT_HISTORY_SIZE)]);
    let first_eos = trace
        .tokenizer
        .eos_token_id
        .and_then(|eos_id| trace.token_ids.iter().position(|token| *token == eos_id));
    let mut raw_numerator = 0u64;
    let mut weighted_numerator = 0u64;
    let mut valid_count = 0u64;

    for position in 0..candidate_context_count {
        let context_hash = accumulate_hash(1, &trace.token_ids[position..position + NGRAM_LEN - 1]);
        let repetition_bit = !history_counts.contains_key(&context_hash);
        history.push_front(context_hash);
        *history_counts.entry(context_hash).or_insert(0) += 1;
        let evicted = history.pop_back().expect("fixed history is non-empty");
        let remaining = history_counts
            .get_mut(&evicted)
            .expect("evicted context has a count");
        *remaining -= 1;
        if *remaining == 0 {
            history_counts.remove(&evicted);
        }
        let final_token_position = position + NGRAM_LEN - 1;
        let eos_bit = first_eos.is_none_or(|index| final_token_position < index);
        let valid_bit = repetition_bit && eos_bit;
        repetition.push(repetition_bit);
        eos.push(eos_bit);
        valid.push(valid_bit);
        if valid_bit {
            valid_count += 1;
        }

        let ngram_hash = accumulate_hash(1, &trace.token_ids[position..position + NGRAM_LEN]);
        for (depth, key) in KEYS.iter().enumerate() {
            let keyed_hash = accumulate_hash_i64(ngram_hash, *key);
            let table_index = keyed_hash.rem_euclid(TABLE_SIZE as i64) as usize;
            let g = sampling_bit(table_index);
            g_values.push(g);
            if valid_bit && g {
                raw_numerator += 1;
                weighted_numerator += (290 - 9 * depth) as u64;
            }
        }
    }

    let g_digest = bit_digest(&g_values);
    let masks = ScoreMasks {
        repetition: bit_digest(&repetition),
        eos: bit_digest(&eos),
        valid: bit_digest(&valid),
    };
    let status = if valid_count == 0 {
        ScoreStatus::InsufficientData
    } else {
        ScoreStatus::Scored
    };
    let raw_score =
        (valid_count > 0).then(|| exact_score(raw_numerator, DEPTH as u64 * valid_count));
    let weighted_score =
        (valid_count > 0).then(|| exact_score(weighted_numerator, WEIGHT_SUM * valid_count));

    Ok(ScoreReport {
        schema: SCORE_SCHEMA,
        trace_id: trace.trace_id.clone(),
        profile: trace.profile.clone(),
        trace_sha256: sha256(source_bytes),
        status,
        token_count: token_count as u64,
        candidate_context_count: candidate_context_count as u64,
        first_eos_index: first_eos.map(|index| index as u64),
        repetition_excluded_count: repetition.iter().filter(|bit| !**bit).count() as u64,
        eos_excluded_count: eos.iter().filter(|bit| !**bit).count() as u64,
        valid_context_count: valid_count,
        g_value_one_count: raw_numerator,
        weighted_g_value_sum: weighted_numerator,
        g_values: g_digest,
        masks,
        raw_score,
        weighted_score,
        warnings: WARNINGS.to_vec(),
    })
}

fn validate_trace(trace: &SynthIdTrace) -> Result<(), SynthIdError> {
    if trace.schema != TRACE_SCHEMA {
        return Err(SynthIdError::Input(format!(
            "unsupported trace schema {:?}; expected {TRACE_SCHEMA}",
            trace.schema
        )));
    }
    if trace.profile.id != PROFILE_ID || trace.profile.file_sha256 != PROFILE_SHA256 {
        return Err(SynthIdError::Input(format!(
            "unsupported SynthID profile reference; expected {PROFILE_ID} at {PROFILE_SHA256}"
        )));
    }
    if trace.sequence_role != "generated_output_only" {
        return Err(SynthIdError::Input(
            "sequence_role must be generated_output_only".to_owned(),
        ));
    }
    if trace.trace_id.is_empty()
        || trace.trace_id.len() > 128
        || !trace
            .trace_id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    {
        return Err(SynthIdError::Input(
            "trace_id must contain 1 to 128 lowercase ASCII letters, digits or hyphens".to_owned(),
        ));
    }
    if trace.tokenizer.model_id.is_empty()
        || trace.tokenizer.model_id.chars().count() > 256
        || trace.tokenizer.revision.is_empty()
        || trace.tokenizer.revision.chars().count() > 256
    {
        return Err(SynthIdError::Input(
            "tokenizer model_id and revision must contain 1 to 256 bytes".to_owned(),
        ));
    }
    if trace.token_ids.len() > TOKEN_LIMIT {
        return Err(SynthIdError::Input(format!(
            "trace has more than {TOKEN_LIMIT} token IDs"
        )));
    }
    if trace.token_ids.iter().any(|token| *token > TOKEN_ID_MAX)
        || trace
            .tokenizer
            .eos_token_id
            .is_some_and(|token| token > TOKEN_ID_MAX)
    {
        return Err(SynthIdError::Input(format!(
            "token IDs must be from 0 to {TOKEN_ID_MAX}"
        )));
    }
    Ok(())
}

fn accumulate_hash(mut current: i64, data: &[u32]) -> i64 {
    for value in data {
        current = accumulate_hash_i64(current, i64::from(*value));
    }
    current
}

fn accumulate_hash_i64(current: i64, value: i64) -> i64 {
    current
        .wrapping_add(value)
        .wrapping_mul(HASH_MULTIPLIER)
        .wrapping_add(HASH_INCREMENT)
}

fn sampling_bit(index: usize) -> bool {
    (SAMPLING_TABLE[index / 8] >> (index % 8)) & 1 == 1
}

fn bit_digest(bits: &[bool]) -> BitDigest {
    let mut packed = vec![0u8; bits.len().div_ceil(8)];
    for (index, bit) in bits.iter().enumerate() {
        if *bit {
            packed[index / 8] |= 1 << (index % 8);
        }
    }
    BitDigest {
        bit_length: bits.len() as u64,
        byte_length: packed.len() as u64,
        sha256: sha256(&packed),
    }
}

fn exact_score(numerator: u64, denominator: u64) -> ExactScore {
    ExactScore {
        numerator,
        denominator,
        decimal: decimal_half_even(numerator, denominator, 12),
    }
}

fn decimal_half_even(numerator: u64, denominator: u64, places: u32) -> String {
    debug_assert!(denominator > 0);
    let scale = 10u128.pow(places);
    let scaled = u128::from(numerator) * scale;
    let quotient = scaled / u128::from(denominator);
    let remainder = scaled % u128::from(denominator);
    let twice_remainder = remainder * 2;
    let rounded = if twice_remainder > u128::from(denominator)
        || (twice_remainder == u128::from(denominator) && quotient % 2 == 1)
    {
        quotient + 1
    } else {
        quotient
    };
    let integer = rounded / scale;
    let fraction = rounded % scale;
    format!("{integer}.{fraction:0width$}", width = places as usize)
}

fn sha256(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn read_trace(path: &Path) -> Result<Vec<u8>, SynthIdError> {
    let file = open_no_follow(path)?;
    let metadata = file
        .metadata()
        .map_err(|error| SynthIdError::Input(format!("cannot stat {}: {error}", path.display())))?;
    if handle_is_symlink(&metadata) {
        return Err(SynthIdError::Input(format!(
            "symlink inputs are refused: {}",
            path.display()
        )));
    }
    if !metadata.is_file() {
        return Err(SynthIdError::Input(format!(
            "input is not a regular file: {}",
            path.display()
        )));
    }
    if metadata.len() > TRACE_LIMIT {
        return Err(SynthIdError::Input(format!(
            "trace exceeds the {TRACE_LIMIT}-byte limit"
        )));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.take(TRACE_LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| SynthIdError::Input(format!("cannot read {}: {error}", path.display())))?;
    if bytes.len() as u64 > TRACE_LIMIT {
        return Err(SynthIdError::Input(format!(
            "trace exceeds the {TRACE_LIMIT}-byte limit"
        )));
    }
    Ok(bytes)
}

#[cfg(unix)]
fn open_no_follow(path: &Path) -> Result<File, SynthIdError> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|error| {
            if error.raw_os_error() == Some(libc::ELOOP) {
                SynthIdError::Input(format!("symlink inputs are refused: {}", path.display()))
            } else {
                SynthIdError::Input(format!("cannot read {}: {error}", path.display()))
            }
        })
}

#[cfg(windows)]
fn open_no_follow(path: &Path) -> Result<File, SynthIdError> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT;
    OpenOptions::new()
        .read(true)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
        .map_err(|error| SynthIdError::Input(format!("cannot read {}: {error}", path.display())))
}

#[cfg(windows)]
fn handle_is_symlink(metadata: &std::fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn handle_is_symlink(_metadata: &std::fs::Metadata) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_wraps_and_uses_euclidean_modulo() {
        let hash = accumulate_hash(1, &[u32::MAX, 2, 3, 4, 5]);
        assert!(hash < 0);
        assert_eq!(hash.rem_euclid(TABLE_SIZE as i64), 16_035);
    }

    #[test]
    fn half_even_rounding_handles_ties() {
        assert_eq!(decimal_half_even(1, 8, 2), "0.12");
        assert_eq!(decimal_half_even(3, 8, 2), "0.38");
        assert_eq!(decimal_half_even(1, 2, 12), "0.500000000000");
    }

    #[test]
    fn empty_bit_vector_hashes_zero_bytes() {
        assert_eq!(
            bit_digest(&[]).sha256,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }
}
