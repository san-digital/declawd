# `declawd.report/v1`

Every JSON command result uses the schema identifier `declawd.report/v1`.
The machine-readable contract is [`report-v1.schema.json`](report-v1.schema.json),
and a normative instance is published in `vectors/report-v1.json`.
Core CLI operations are `inspect`, `clean-text` and `clean-c2pa`. Other
lower-case, hyphenated operation IDs are reserved for compatible producers;
their semantics must be documented by that producer.

- `tool_version`, `operation` and `changed` identify the invocation result.
- `input` and optional `output` contain media type, byte length and SHA-256.
- `findings` contain the carrier, normative class, position and disposition.
- `requested_actions` record every selector and match count.
- `completed_actions` contain only actions with at least one match.
- `verification` records supported-carrier and preservation checks.
- `untested_channels` and `warnings` prevent a narrow result being read as a
  general provenance conclusion.

Text positions are zero-based Unicode scalar offsets and one-based scalar line
and column numbers. CRLF is one line break; lone CR and lone LF each advance one
line. Context is excluded unless `--include-context` is explicitly requested.
`verification.supported_carriers_remaining` counts output scalars that still
match a selector requested for that cleaning operation. It is not a claim that
every character in the registry, or every possible watermark carrier, is absent.
