use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::Path;

use c2pa::Error as C2paError;
use img_parts::jpeg::markers;
use sha2::{Digest, Sha256};
use tempfile::{Builder as TempBuilder, TempPath};
use thiserror::Error;

use crate::report::{Action, Artifact, Finding, Report};
use crate::unicode::{TextSelectors, clean_text, inspect_text, selected_count};

pub const TEXT_LIMIT: u64 = 10 * 1024 * 1024;
pub const IMAGE_LIMIT: u64 = 100 * 1024 * 1024;

const PNG_SIGNATURE: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MediaKind {
    Text,
    Png,
    Jpeg,
}

impl MediaKind {
    pub fn media_type(self) -> &'static str {
        match self {
            Self::Text => "text/plain; charset=utf-8",
            Self::Png => "image/png",
            Self::Jpeg => "image/jpeg",
        }
    }

    fn c2pa_type(self) -> Option<&'static str> {
        match self {
            Self::Png => Some("png"),
            Self::Jpeg => Some("jpg"),
            Self::Text => None,
        }
    }

    fn suffix(self) -> &'static str {
        match self {
            Self::Text => ".txt",
            Self::Png => ".png",
            Self::Jpeg => ".jpg",
        }
    }
}

#[derive(Debug, Error)]
pub enum ToolError {
    #[error("{0}")]
    Usage(String),
    #[error("{0}")]
    Input(String),
    #[error("{0}")]
    Verification(String),
}

impl ToolError {
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::Usage(_) | Self::Input(_) => 2,
            Self::Verification(_) => 3,
        }
    }
}

struct InputData {
    bytes: Vec<u8>,
    kind: MediaKind,
    artifact: Artifact,
}

fn sha256(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn artifact(kind: MediaKind, bytes: &[u8]) -> Artifact {
    Artifact {
        media_type: kind.media_type().to_owned(),
        byte_length: bytes.len() as u64,
        sha256: sha256(bytes),
    }
}

#[cfg(unix)]
fn open_input_no_follow(path: &Path) -> Result<File, ToolError> {
    use std::os::unix::fs::OpenOptionsExt;

    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|error| {
            if error.raw_os_error() == Some(libc::ELOOP) {
                ToolError::Input(format!("symlink inputs are refused: {}", path.display()))
            } else {
                ToolError::Input(format!("cannot read {}: {error}", path.display()))
            }
        })
}

#[cfg(windows)]
fn open_input_no_follow(path: &Path) -> Result<File, ToolError> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT;

    OpenOptions::new()
        .read(true)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
        .map_err(|error| ToolError::Input(format!("cannot read {}: {error}", path.display())))
}

#[cfg(windows)]
fn handle_is_symlink(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn handle_is_symlink(_metadata: &fs::Metadata) -> bool {
    false
}

fn read_input(path: &Path) -> Result<InputData, ToolError> {
    let mut prefix = [0u8; 8];
    let mut file = open_input_no_follow(path)?;
    let metadata = file
        .metadata()
        .map_err(|error| ToolError::Input(format!("cannot stat {}: {error}", path.display())))?;
    if handle_is_symlink(&metadata) {
        return Err(ToolError::Input(format!(
            "symlink inputs are refused: {}",
            path.display()
        )));
    }
    if !metadata.is_file() {
        return Err(ToolError::Input(format!(
            "input is not a regular file: {}",
            path.display()
        )));
    }
    let prefix_len = file
        .read(&mut prefix)
        .map_err(|error| ToolError::Input(format!("cannot read {}: {error}", path.display())))?;
    let prefix = &prefix[..prefix_len];
    let mut kind = MediaKind::Text;
    let mut limit = TEXT_LIMIT;
    if prefix.starts_with(PNG_SIGNATURE) {
        kind = MediaKind::Png;
        limit = IMAGE_LIMIT;
    } else if prefix.starts_with(&[0xff, 0xd8, 0xff]) {
        kind = MediaKind::Jpeg;
        limit = IMAGE_LIMIT;
    }
    if metadata.len() > limit {
        return Err(ToolError::Input(format!(
            "{} is {} bytes; the {} limit is {} bytes",
            path.display(),
            metadata.len(),
            kind.media_type(),
            limit
        )));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.rewind()
        .map_err(|error| ToolError::Input(format!("cannot rewind {}: {error}", path.display())))?;
    Read::by_ref(&mut file)
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| ToolError::Input(format!("cannot read {}: {error}", path.display())))?;
    if bytes.len() as u64 > limit {
        return Err(ToolError::Input(format!(
            "{} grew beyond the {} byte {} limit while it was read",
            path.display(),
            limit,
            kind.media_type()
        )));
    }
    if kind == MediaKind::Text {
        std::str::from_utf8(&bytes).map_err(|error| {
            ToolError::Input(format!(
                "{} is not valid UTF-8 (UTF-16 is not supported): {error}",
                path.display()
            ))
        })?;
    }
    let input_artifact = artifact(kind, &bytes);
    Ok(InputData {
        bytes,
        kind,
        artifact: input_artifact,
    })
}

fn c2pa_store(bytes: &[u8], kind: MediaKind) -> Result<Option<Vec<u8>>, ToolError> {
    let media = kind
        .c2pa_type()
        .ok_or_else(|| ToolError::Input("C2PA cleaning supports PNG and JPEG only".to_owned()))?;
    match c2pa::jumbf_io::load_jumbf_from_memory(media, bytes) {
        Ok(store) => Ok(Some(store)),
        Err(C2paError::JumbfNotFound) => Ok(None),
        Err(error) => Err(ToolError::Input(format!(
            "invalid or unsupported {} asset: {error}",
            kind.media_type()
        ))),
    }
}

fn validate_image(bytes: &[u8], kind: MediaKind) -> Result<(), ToolError> {
    match kind {
        MediaKind::Png => {
            png_without_c2pa(bytes)?;
        }
        MediaKind::Jpeg => {
            jpeg_without_c2pa_raw(bytes)?;
        }
        MediaKind::Text => unreachable!("image validation called for text"),
    }
    Ok(())
}

pub fn inspect_file(path: &Path, include_context: bool) -> Result<Report, ToolError> {
    let input = read_input(path)?;
    let mut report = Report::new("inspect", input.artifact);
    match input.kind {
        MediaKind::Text => {
            let text = std::str::from_utf8(&input.bytes).expect("UTF-8 validated while reading");
            report.findings = inspect_text(text, include_context).map_err(ToolError::Input)?;
            if text.starts_with('\u{feff}') {
                report.warnings.push(
                    "A leading UTF-8 BOM is reported and preserved by class operations.".to_owned(),
                );
            }
        }
        MediaKind::Png | MediaKind::Jpeg => {
            validate_image(&input.bytes, input.kind)?;
            if let Some(store) = c2pa_store(&input.bytes, input.kind)? {
                report.findings.push(Finding {
                    carrier: "embedded-c2pa".to_owned(),
                    class: "c2pa-jumbf".to_owned(),
                    code_point: None,
                    name: None,
                    scalar_offset: None,
                    line: None,
                    column: None,
                    byte_length: Some(store.len() as u64),
                    disposition: "reported".to_owned(),
                    context: None,
                });
            }
            report.untested_channels.extend([
                "remote C2PA references were not followed".to_owned(),
                "soft bindings were not tested".to_owned(),
            ]);
        }
    }
    Ok(report)
}

pub fn clean_text_file(
    input_path: &Path,
    output_path: &Path,
    selectors: &TextSelectors,
    allow_empty: bool,
) -> Result<Report, ToolError> {
    ensure_distinct_paths(input_path, output_path)?;
    let input = read_input(input_path)?;
    if input.kind != MediaKind::Text {
        return Err(ToolError::Input(format!(
            "{} is {}; clean text accepts UTF-8 text only",
            input_path.display(),
            input.kind.media_type()
        )));
    }
    ensure_output_available(output_path)?;
    let text = std::str::from_utf8(&input.bytes).expect("UTF-8 validated while reading");
    let clean = clean_text(text, selectors).map_err(ToolError::Usage)?;
    let mut report = Report::new("clean-text", input.artifact);
    report.changed = clean.changed;
    report.findings = clean.findings;
    report.requested_actions = clean.requested_actions;
    report.completed_actions = clean.completed_actions;

    if clean.changed || allow_empty {
        let output_bytes = clean.text.as_bytes();
        let temporary = write_temporary(output_path, MediaKind::Text, output_bytes)?;
        let verified_bytes = fs::read(&temporary).map_err(|error| {
            ToolError::Verification(format!("could not verify temporary output: {error}"))
        })?;
        if verified_bytes != output_bytes {
            return Err(ToolError::Verification(
                "refusing output: temporary text bytes do not match the requested result"
                    .to_owned(),
            ));
        }
        let verified_text = std::str::from_utf8(&verified_bytes).map_err(|error| {
            ToolError::Verification(format!("temporary text output is not valid UTF-8: {error}"))
        })?;
        let remaining = selected_count(verified_text, selectors);
        if remaining > 0 {
            return Err(ToolError::Verification(format!(
                "refusing output: {remaining} selected supported carriers remain"
            )));
        }
        report.verification.supported_carriers_remaining = Some(remaining);
        report.verification.byte_identical_copy = Some(!clean.changed);
        sync_temporary(&temporary)?;
        persist(temporary, output_path)?;
        report.output = Some(artifact(MediaKind::Text, &verified_bytes));
    } else {
        report.warnings.push(
            "No selected target was found; no output was created. Use --allow-empty for a byte-identical copy."
                .to_owned(),
        );
    }
    Ok(report)
}

pub fn clean_c2pa_file(
    input_path: &Path,
    output_path: &Path,
    allow_empty: bool,
) -> Result<Report, ToolError> {
    ensure_distinct_paths(input_path, output_path)?;
    let input = read_input(input_path)?;
    if input.kind == MediaKind::Text {
        return Err(ToolError::Input(format!(
            "{} is UTF-8 text; clean c2pa accepts PNG or JPEG only",
            input_path.display()
        )));
    }
    ensure_output_available(output_path)?;
    validate_image(&input.bytes, input.kind)?;
    let store = c2pa_store(&input.bytes, input.kind)?;
    let mut report = Report::new("clean-c2pa", input.artifact);
    report.requested_actions.push(Action {
        action: "remove-embedded-c2pa".to_owned(),
        selector: "c2pa-jumbf".to_owned(),
        replacement: None,
        matches: usize::from(store.is_some()),
    });
    report.untested_channels.extend([
        "remote C2PA references were not followed or removed".to_owned(),
        "soft bindings were not tested or removed".to_owned(),
    ]);

    if let Some(store) = store {
        report.changed = true;
        report.findings.push(Finding {
            carrier: "embedded-c2pa".to_owned(),
            class: "c2pa-jumbf".to_owned(),
            code_point: None,
            name: None,
            scalar_offset: None,
            line: None,
            column: None,
            byte_length: Some(store.len() as u64),
            disposition: "removed".to_owned(),
            context: None,
        });
        report.completed_actions = report.requested_actions.clone();
        let temporary = write_temporary(output_path, input.kind, &input.bytes)?;
        c2pa::jumbf_io::remove_jumbf_from_file(&temporary).map_err(|error| {
            ToolError::Verification(format!("could not remove embedded C2PA store: {error}"))
        })?;
        let output_bytes = fs::read(&temporary).map_err(|error| {
            ToolError::Verification(format!("could not verify temporary output: {error}"))
        })?;
        if c2pa_store(&output_bytes, input.kind)?.is_some() {
            return Err(ToolError::Verification(
                "refusing output: an embedded C2PA store remains".to_owned(),
            ));
        }
        let preserved = preserved_non_c2pa(&input.bytes, &output_bytes, input.kind)?;
        if !preserved {
            return Err(ToolError::Verification(
                "refusing output: bytes outside the embedded C2PA carrier changed".to_owned(),
            ));
        }
        report.verification.embedded_c2pa_absent = Some(true);
        report.verification.non_c2pa_bytes_unchanged = Some(true);
        report.verification.compressed_image_data_unchanged = Some(true);
        sync_temporary(&temporary)?;
        persist(temporary, output_path)?;
        report.output = Some(artifact(input.kind, &output_bytes));
    } else if allow_empty {
        let temporary = write_temporary(output_path, input.kind, &input.bytes)?;
        let output_bytes = fs::read(&temporary).map_err(|error| {
            ToolError::Verification(format!("could not verify temporary output: {error}"))
        })?;
        if output_bytes != input.bytes {
            return Err(ToolError::Verification(
                "refusing output: temporary image bytes do not match the input".to_owned(),
            ));
        }
        validate_image(&output_bytes, input.kind)?;
        sync_temporary(&temporary)?;
        persist(temporary, output_path)?;
        report.verification.embedded_c2pa_absent = Some(true);
        report.verification.non_c2pa_bytes_unchanged = Some(true);
        report.verification.compressed_image_data_unchanged = Some(true);
        report.verification.byte_identical_copy = Some(true);
        report.output = Some(artifact(input.kind, &output_bytes));
    } else {
        report.warnings.push(
            "No embedded C2PA store was found; no output was created. Use --allow-empty for a byte-identical copy."
                .to_owned(),
        );
    }
    Ok(report)
}

fn ensure_distinct_paths(input: &Path, output: &Path) -> Result<(), ToolError> {
    if input == output {
        return Err(ToolError::Usage(
            "input and output must be different paths".to_owned(),
        ));
    }
    if let Ok(canonical_input) = input.canonicalize()
        && let Some(parent) = output.parent()
        && let Ok(canonical_parent) = parent.canonicalize()
        && output.file_name().is_some()
        && canonical_input == canonical_parent.join(output.file_name().expect("checked"))
    {
        return Err(ToolError::Usage(
            "input and output resolve to the same path".to_owned(),
        ));
    }
    Ok(())
}

fn ensure_output_available(output: &Path) -> Result<(), ToolError> {
    if output.exists() {
        return Err(ToolError::Input(format!(
            "refusing to overwrite existing output: {}",
            output.display()
        )));
    }
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    if !parent.is_dir() {
        return Err(ToolError::Input(format!(
            "output directory does not exist: {}",
            parent.display()
        )));
    }
    Ok(())
}

fn write_temporary(output: &Path, kind: MediaKind, bytes: &[u8]) -> Result<TempPath, ToolError> {
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    let mut file = TempBuilder::new()
        .prefix(".declawd-")
        .suffix(kind.suffix())
        .tempfile_in(parent)
        .map_err(|error| ToolError::Input(format!("cannot create temporary output: {error}")))?;
    file.write_all(bytes)
        .and_then(|()| file.flush())
        .and_then(|()| file.as_file().sync_all())
        .map_err(|error| ToolError::Input(format!("cannot write temporary output: {error}")))?;
    Ok(file.into_temp_path())
}

fn persist(temporary: TempPath, output: &Path) -> Result<(), ToolError> {
    temporary.persist_noclobber(output).map_err(|error| {
        ToolError::Input(format!(
            "cannot atomically publish {}: {}",
            output.display(),
            error.error
        ))
    })?;
    if let Some(parent) = output.parent() {
        sync_directory(parent)?;
    }
    Ok(())
}

fn sync_temporary(temporary: &Path) -> Result<(), ToolError> {
    OpenOptions::new()
        .read(true)
        .write(true)
        .open(temporary)
        .and_then(|file| file.sync_all())
        .map_err(|error| {
            ToolError::Verification(format!("cannot flush verified temporary output: {error}"))
        })
}

#[cfg(unix)]
fn sync_directory(path: &Path) -> Result<(), ToolError> {
    fs::File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| ToolError::Input(format!("cannot sync output directory: {error}")))
}

#[cfg(not(unix))]
fn sync_directory(_path: &Path) -> Result<(), ToolError> {
    Ok(())
}

fn preserved_non_c2pa(before: &[u8], after: &[u8], kind: MediaKind) -> Result<bool, ToolError> {
    match kind {
        MediaKind::Png => Ok(png_without_c2pa(before)? == after),
        MediaKind::Jpeg => Ok(jpeg_without_c2pa_raw(before)? == after),
        MediaKind::Text => unreachable!("C2PA preservation is image-only"),
    }
}

fn jpeg_without_c2pa_raw(bytes: &[u8]) -> Result<Vec<u8>, ToolError> {
    if !bytes.starts_with(&[0xff, 0xd8]) {
        return Err(ToolError::Input("invalid JPEG signature".to_owned()));
    }
    let mut output = bytes[..2].to_vec();
    let mut cursor = 2usize;
    let mut active_instance: Option<[u8; 2]> = None;
    while cursor < bytes.len() {
        let marker_start = cursor;
        if bytes[cursor] != 0xff {
            return Err(ToolError::Input(
                "invalid JPEG marker before scan data".to_owned(),
            ));
        }
        while cursor < bytes.len() && bytes[cursor] == 0xff {
            cursor += 1;
        }
        if cursor >= bytes.len() {
            return Err(ToolError::Input("truncated JPEG marker".to_owned()));
        }
        let marker = bytes[cursor];
        cursor += 1;
        if marker == markers::SOS {
            if cursor + 2 > bytes.len() {
                return Err(ToolError::Input("truncated JPEG scan header".to_owned()));
            }
            let length = u16::from_be_bytes([bytes[cursor], bytes[cursor + 1]]) as usize;
            if length < 2 || cursor + length > bytes.len() {
                return Err(ToolError::Input(
                    "invalid JPEG scan-header length".to_owned(),
                ));
            }
            validate_jpeg_scans(bytes, cursor + length)?;
            output.extend_from_slice(&bytes[marker_start..]);
            return Ok(output);
        }
        if marker == markers::EOI {
            return Err(ToolError::Input("JPEG has no scan data".to_owned()));
        }
        let standalone = marker == 0x01 || (0xd0..=0xd9).contains(&marker);
        if standalone {
            output.extend_from_slice(&bytes[marker_start..cursor]);
            continue;
        }
        if cursor + 2 > bytes.len() {
            return Err(ToolError::Input("truncated JPEG segment length".to_owned()));
        }
        let length = u16::from_be_bytes([bytes[cursor], bytes[cursor + 1]]) as usize;
        if length < 2 || cursor + length > bytes.len() {
            return Err(ToolError::Input("invalid JPEG segment length".to_owned()));
        }
        let payload_start = cursor + 2;
        let segment_end = cursor + length;
        let payload = &bytes[payload_start..segment_end];
        let mut is_c2pa = false;
        if marker == markers::APP11 && payload.len() > 16 {
            let instance = [payload[2], payload[3]];
            if active_instance == Some(instance) {
                is_c2pa = true;
            } else if payload.len() >= 28 && &payload[24..28] == b"c2pa" {
                active_instance = Some(instance);
                is_c2pa = true;
            }
        }
        if !is_c2pa {
            output.extend_from_slice(&bytes[marker_start..segment_end]);
        }
        cursor = segment_end;
    }
    Err(ToolError::Input("JPEG has no scan data".to_owned()))
}

fn validate_jpeg_scans(bytes: &[u8], mut cursor: usize) -> Result<(), ToolError> {
    loop {
        while cursor < bytes.len() {
            if bytes[cursor] != 0xff {
                cursor += 1;
                continue;
            }
            let marker_start = cursor;
            while cursor < bytes.len() && bytes[cursor] == 0xff {
                cursor += 1;
            }
            if cursor >= bytes.len() {
                return Err(ToolError::Input(
                    "JPEG scan does not terminate with EOI".to_owned(),
                ));
            }
            let marker = bytes[cursor];
            cursor += 1;
            match marker {
                0x00 | 0xd0..=0xd7 => continue,
                markers::EOI => {
                    if cursor != bytes.len() {
                        return Err(ToolError::Input(
                            "JPEG has trailing bytes after EOI".to_owned(),
                        ));
                    }
                    return Ok(());
                }
                markers::SOS => {
                    if cursor + 2 > bytes.len() {
                        return Err(ToolError::Input("truncated JPEG scan header".to_owned()));
                    }
                    let length = u16::from_be_bytes([bytes[cursor], bytes[cursor + 1]]) as usize;
                    if length < 2 || cursor + length > bytes.len() {
                        return Err(ToolError::Input(
                            "invalid JPEG scan-header length".to_owned(),
                        ));
                    }
                    cursor += length;
                    break;
                }
                markers::SOI => {
                    return Err(ToolError::Input(
                        "unexpected JPEG SOI after scan data".to_owned(),
                    ));
                }
                _ => {
                    let standalone = marker == 0x01 || (0xd0..=0xd7).contains(&marker);
                    if standalone {
                        continue;
                    }
                    if cursor + 2 > bytes.len() {
                        return Err(ToolError::Input(
                            "truncated JPEG segment after scan data".to_owned(),
                        ));
                    }
                    let length = u16::from_be_bytes([bytes[cursor], bytes[cursor + 1]]) as usize;
                    if length < 2 || cursor + length > bytes.len() {
                        return Err(ToolError::Input(
                            "invalid JPEG segment after scan data".to_owned(),
                        ));
                    }
                    cursor += length;
                    if marker_start >= cursor {
                        return Err(ToolError::Input("invalid JPEG marker progress".to_owned()));
                    }
                }
            }
        }
        if cursor >= bytes.len() {
            return Err(ToolError::Input(
                "JPEG scan does not terminate with EOI".to_owned(),
            ));
        }
    }
}

fn png_without_c2pa(bytes: &[u8]) -> Result<Vec<u8>, ToolError> {
    if !bytes.starts_with(PNG_SIGNATURE) {
        return Err(ToolError::Input("invalid PNG signature".to_owned()));
    }
    let mut output = PNG_SIGNATURE.to_vec();
    let mut cursor = PNG_SIGNATURE.len();
    let mut saw_end = false;
    let mut saw_ihdr = false;
    let mut saw_idat = false;
    let mut chunk_index = 0usize;
    while cursor < bytes.len() {
        let header_end = cursor
            .checked_add(8)
            .ok_or_else(|| ToolError::Input("PNG chunk position overflow".to_owned()))?;
        if header_end > bytes.len() {
            return Err(ToolError::Input("truncated PNG chunk header".to_owned()));
        }
        let length = u32::from_be_bytes(
            bytes[cursor..cursor + 4]
                .try_into()
                .expect("four-byte length"),
        ) as usize;
        let end = header_end
            .checked_add(length)
            .and_then(|value| value.checked_add(4))
            .ok_or_else(|| ToolError::Input("PNG chunk length overflow".to_owned()))?;
        if end > bytes.len() {
            return Err(ToolError::Input("truncated PNG chunk".to_owned()));
        }
        let chunk_type = &bytes[cursor + 4..cursor + 8];
        let expected_crc = u32::from_be_bytes(
            bytes[end - 4..end]
                .try_into()
                .expect("four-byte PNG checksum"),
        );
        let actual_crc = crc32fast::hash(&bytes[cursor + 4..end - 4]);
        if actual_crc != expected_crc {
            return Err(ToolError::Input(format!(
                "PNG chunk {} has an invalid CRC",
                String::from_utf8_lossy(chunk_type)
            )));
        }
        match chunk_type {
            b"IHDR" => {
                if chunk_index != 0 || saw_ihdr || length != 13 {
                    return Err(ToolError::Input(
                        "PNG requires one 13-byte IHDR as its first chunk".to_owned(),
                    ));
                }
                let width = u32::from_be_bytes(
                    bytes[header_end..header_end + 4]
                        .try_into()
                        .expect("four-byte PNG width"),
                );
                let height = u32::from_be_bytes(
                    bytes[header_end + 4..header_end + 8]
                        .try_into()
                        .expect("four-byte PNG height"),
                );
                if width == 0 || height == 0 {
                    return Err(ToolError::Input(
                        "PNG width and height must be non-zero".to_owned(),
                    ));
                }
                saw_ihdr = true;
            }
            b"IDAT" => {
                if !saw_ihdr {
                    return Err(ToolError::Input("PNG IDAT appears before IHDR".to_owned()));
                }
                saw_idat = true;
            }
            b"IEND" => {
                if length != 0 || !saw_ihdr || !saw_idat {
                    return Err(ToolError::Input(
                        "PNG IEND requires a preceding IHDR and IDAT and must be empty".to_owned(),
                    ));
                }
            }
            _ if chunk_index == 0 => {
                return Err(ToolError::Input(
                    "PNG IHDR must be the first chunk".to_owned(),
                ));
            }
            _ => {}
        }
        if chunk_type != b"caBX" {
            output.extend_from_slice(&bytes[cursor..end]);
        }
        cursor = end;
        if chunk_type == b"IEND" {
            saw_end = true;
            break;
        }
        chunk_index += 1;
    }
    if !saw_end || cursor != bytes.len() {
        return Err(ToolError::Input(
            "PNG must end exactly after its IEND chunk".to_owned(),
        ));
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::{MediaKind, preserved_non_c2pa};

    #[test]
    fn jpeg_preservation_includes_entropy_coded_scan_data() {
        let before = [0xff, 0xd8, 0xff, 0xda, 0x00, 0x02, 0x01, 0xff, 0xd9];
        let after = [0xff, 0xd8, 0xff, 0xda, 0x00, 0x02, 0x02, 0xff, 0xd9];
        assert!(!preserved_non_c2pa(&before, &after, MediaKind::Jpeg).unwrap());
    }
}
