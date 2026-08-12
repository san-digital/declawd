use std::collections::{BTreeMap, BTreeSet};
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Args, Parser, Subcommand};
use declawd::unicode::parse_code_point;
use declawd::{Report, TextSelectors, ToolError, clean_c2pa_file, clean_text_file, inspect_file};

#[derive(Debug, Parser)]
#[command(
    name = "declawd",
    version,
    about = "Inspect and selectively remove known carriers for education",
    long_about = "Inspect and selectively remove known Unicode and embedded C2PA carriers.\n\nThis tool does not detect or certify removal of Claude's watermark. A finding is not evidence that AI was involved."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Inspect UTF-8 text, PNG or JPEG without changing it.
    Inspect(InspectArgs),
    /// Create a new output after an explicit, verified transformation.
    Clean(CleanArgs),
}

#[derive(Debug, Args)]
struct InspectArgs {
    /// UTF-8 text, PNG or JPEG file to inspect.
    file: PathBuf,
    /// Emit the versioned JSON report rather than the human summary.
    #[arg(long)]
    json: bool,
    /// Include up to 32 Unicode scalars of source context on either side.
    #[arg(long)]
    include_context: bool,
    /// Return zero even when supported carriers are found.
    #[arg(long)]
    exit_zero: bool,
}

#[derive(Debug, Args)]
struct CleanArgs {
    #[command(subcommand)]
    command: CleanCommand,
}

#[derive(Debug, Subcommand)]
enum CleanCommand {
    /// Selectively remove or replace Unicode scalars in UTF-8 text.
    Text(CleanTextArgs),
    /// Remove only an embedded C2PA/JUMBF store from PNG or JPEG.
    C2pa(CleanC2paArgs),
}

#[derive(Debug, Args)]
struct CleanTextArgs {
    /// UTF-8 input file. UTF-16 with a BOM and invalid UTF-8 are refused.
    input: PathBuf,
    /// New output path. Existing files are never overwritten.
    #[arg(long, short)]
    output: PathBuf,
    /// Remove this exact scalar, for example U+200B. Repeatable.
    #[arg(long, value_name = "U+XXXX")]
    remove: Vec<String>,
    /// Remove a named registry class. Repeatable; `bom` is not selectable.
    #[arg(long, value_name = "CLASS")]
    remove_class: Vec<String>,
    /// Replace one scalar with another, for example U+202F=U+0020. Repeatable.
    #[arg(long, value_name = "U+XXXX=U+YYYY")]
    replace: Vec<String>,
    /// Write a byte-identical output when no requested target is found.
    #[arg(long)]
    allow_empty: bool,
    /// Emit the versioned JSON report rather than the human summary.
    #[arg(long)]
    json: bool,
}

#[derive(Debug, Args)]
struct CleanC2paArgs {
    /// PNG or JPEG input identified by file signature.
    input: PathBuf,
    /// New output path. Existing files are never overwritten.
    #[arg(long, short)]
    output: PathBuf,
    /// Write a byte-identical output when no embedded C2PA store is found.
    #[arg(long)]
    allow_empty: bool,
    /// Emit the versioned JSON report rather than the human summary.
    #[arg(long)]
    json: bool,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(cli) {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            let _ = writeln!(io::stderr(), "declawd: {error}");
            ExitCode::from(error.exit_code() as u8)
        }
    }
}

fn run(cli: Cli) -> Result<u8, ToolError> {
    match cli.command {
        Command::Inspect(args) => {
            let report = inspect_file(&args.file, args.include_context)?;
            let findings = report.findings.len();
            print_report(&report, args.json)?;
            Ok(if findings > 0 && !args.exit_zero {
                1
            } else {
                0
            })
        }
        Command::Clean(args) => match args.command {
            CleanCommand::Text(args) => {
                let selectors = parse_selectors(args.remove, args.remove_class, args.replace)?;
                let report =
                    clean_text_file(&args.input, &args.output, &selectors, args.allow_empty)?;
                print_report(&report, args.json)?;
                Ok(0)
            }
            CleanCommand::C2pa(args) => {
                let report = clean_c2pa_file(&args.input, &args.output, args.allow_empty)?;
                print_report(&report, args.json)?;
                Ok(0)
            }
        },
    }
}

fn parse_selectors(
    remove: Vec<String>,
    remove_class: Vec<String>,
    replace: Vec<String>,
) -> Result<TextSelectors, ToolError> {
    let remove = remove
        .iter()
        .map(|value| parse_code_point(value).map_err(ToolError::Usage))
        .collect::<Result<BTreeSet<_>, _>>()?;
    let remove_classes = remove_class.into_iter().collect::<BTreeSet<_>>();
    let mut replacements = BTreeMap::new();
    for value in replace {
        let Some((from, to)) = value.split_once('=') else {
            return Err(ToolError::Usage(format!(
                "expected U+XXXX=U+YYYY, got {value:?}"
            )));
        };
        if to.contains('=') {
            return Err(ToolError::Usage(format!(
                "expected U+XXXX=U+YYYY, got {value:?}"
            )));
        }
        let from = parse_code_point(from).map_err(ToolError::Usage)?;
        let to = parse_code_point(to).map_err(ToolError::Usage)?;
        if let Some(previous) = replacements.insert(from, to)
            && previous != to
        {
            return Err(ToolError::Usage(format!(
                "{} has conflicting replacement targets",
                declawd::unicode::format_code_point(from)
            )));
        }
    }
    let selectors = TextSelectors {
        remove,
        remove_classes,
        replacements,
    };
    selectors.validate().map_err(ToolError::Usage)?;
    Ok(selectors)
}

fn print_report(report: &Report, json: bool) -> Result<(), ToolError> {
    if json {
        let mut rendered = serde_json::to_string_pretty(report).map_err(|error| {
            ToolError::Verification(format!("cannot render JSON report: {error}"))
        })?;
        escape_registered_controls(&mut rendered);
        println!("{rendered}");
        return Ok(());
    }
    println!("Operation: {}", report.operation);
    println!(
        "Input: {} bytes, SHA-256 {}",
        report.input.byte_length, report.input.sha256
    );
    println!("Supported findings: {}", report.findings.len());
    if let Some(output) = &report.output {
        println!(
            "Output: {} bytes, SHA-256 {}",
            output.byte_length, output.sha256
        );
    } else if report.operation.starts_with("clean-") {
        println!("Output: none");
    }
    println!("Changed: {}", report.changed);
    for finding in &report.findings {
        match (&finding.code_point, finding.scalar_offset) {
            (Some(code_point), Some(offset)) => println!(
                "- {} {} at scalar {} (line {}, column {}): {}",
                finding.class,
                code_point,
                offset,
                finding.line.unwrap_or(0),
                finding.column.unwrap_or(0),
                finding.disposition
            ),
            _ => println!("- {}: {}", finding.class, finding.disposition),
        }
    }
    for channel in &report.untested_channels {
        println!("Not tested: {channel}");
    }
    for warning in &report.warnings {
        println!("Warning: {warning}");
    }
    Ok(())
}

fn escape_registered_controls(rendered: &mut String) {
    let mut escaped = String::with_capacity(rendered.len());
    for character in rendered.chars() {
        let scalar = character as u32;
        if declawd::unicode::is_registered_scalar(scalar) {
            if scalar <= 0xffff {
                escaped.push_str(&format!("\\u{scalar:04x}"));
            } else {
                let adjusted = scalar - 0x1_0000;
                let high = 0xd800 + (adjusted >> 10);
                let low = 0xdc00 + (adjusted & 0x3ff);
                escaped.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
            }
        } else {
            escaped.push(character);
        }
    }
    *rendered = escaped;
}
