---
name: journey-files-export
description: Use when a capability uploads, imports, generates, exports or downloads files, to enumerate and prove the file scenarios (empty, oversized, wrong type, malicious names or content, encoding, denied download, generation failure) beyond a well-formed file.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: FIL
scenarios:
  - FIL-01 | required | Valid file processed | When a user uploads or requests a valid file, the system shall process or generate it and confirm the result with name, size or record count.
  - FIL-02 | required | Empty file | If an uploaded file is empty or has headers only, then the system shall reject it with a message that the file has no content and store nothing.
  - FIL-03 | required | Oversized file | If an uploaded file exceeds the configured size or row limit, then the system shall reject it early with a message that states the limit, without exhausting memory or disk.
  - FIL-04 | required | Wrong format or type | If an uploaded file has a disallowed type or content that does not match its declared format, then the system shall reject it with a message listing the accepted formats.
  - FIL-05 | required | Malicious content and unsafe names | If a file name contains path traversal or control characters, or the content is a known-dangerous payload (archive bomb, macro, script), then the system shall reject or neutralize it and never write outside the storage area.
  - FIL-06 | required | Special characters and encoding | When a file contains non-ASCII text, delimiters inside values or a byte-order mark, the system shall read and write it without corruption and with a declared encoding.
  - FIL-07 | required | Invalid rows reported | If some rows or records of an imported file are invalid, then the system shall report each invalid row with its line number and reason and apply the stated all-or-nothing or partial policy.
  - FIL-08 | required | Download permission deny | If a user requests a file they are not allowed to access, then the system shall deny it with 403 (or the lane equivalent) and not reveal whether the file exists, including via guessable links.
  - FIL-09 | required | Generation in progress or failed | When a file is being generated, the system shall show that it is in progress, and if generation fails, then it shall show a readable failure with a retry.
  - FIL-10 | conditional | [Large exports possible] Large export streaming | When an export exceeds the in-memory threshold, the system shall stream or chunk it with bounded memory and deliver a complete, valid file.
  - FIL-11 | conditional | [Archives are accepted] Archive extraction limits | If an archive contains entries that escape the target folder or expand beyond the size or ratio limit, then the system shall stop the extraction, write nothing outside the target and report the reason.
  - FIL-12 | conditional | [Uploaded files are shared with other users] Malware scan | When a user uploads a file that others can download, the system shall keep it in quarantine until a scan passes and never serve a file that failed the scan.
  - FIL-13 | conditional | [Spreadsheet export: CSV or XLSX] Formula injection | When an exported cell value starts with =, +, -, @, tab or carriage return, the system shall neutralize it so that a spreadsheet does not execute it.
  - FIL-14 | conditional | [Uploaded images are shown to others] Metadata stripped | When an uploaded image is stored for others to see, the system shall remove its location and device metadata.
  - FIL-15 | conditional | [Download links are shared] Expiring links | If a download link is used after its expiry or by a user it was not issued for, then the system shall refuse the download.
obligations:
  - Enumerate every FIL scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Validate size, type and name on the server before processing
  - Generate storage names server-side; never trust client file names for paths
eval_checks:
  - scenario-coverage
  - failure-message-asserted
  - path-traversal-tested
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-client-filename-used-as-path
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Files and Export

## Intent

Files arrive empty, huge, mislabelled, hostile or in an unexpected encoding, and generated files can fail or leak. This skill lists those journeys so that import, upload and export features are safe and honest, not only correct for a tidy sample file.

## Use when

- Use cases or REQs mention upload, import, attachment, document, CSV, Excel, PDF, image, export, download, report file, backup, archive, template, bulk load.
- Recipe, log or configuration files are transferred to or from a controller or edge device.

## Do not use when

The REQ neither accepts uploads nor produces files or exports.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason; state limits (size, rows, types) as numbers.
- **PLAN**: assign each included scenario ID to one owning REQ in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `FIL-03: a 30 MB upload is rejected with "Files must be 10 MB or smaller"`).
- **KIT**: one blocking check per included scenario recorded in docs/ACCEPTANCE.json with the scenario ID; small generated fixtures in the test root (no large binaries committed).
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- Export only, no upload: FIL-02 to FIL-05 and FIL-07 excluded; FIL-06, FIL-08, FIL-09 remain.
- Files never leave the server and are generated from trusted templates only: FIL-05 reduced to the naming rule.
- Exports always small by contract (bounded record count stated): FIL-10 excluded.
- Not a valid reason: "the web server limits size" without a test of the configured limit and message.

## Proof per scenario

- Build fixtures in the test: empty, header-only, just-over-limit, wrong magic bytes with a valid extension, names like `../../etc/passwd` and `con.txt`, UTF-8 with accents and a BOM, quoted delimiters.
- Assert the rejection message text and that storage is unchanged (no file written, no partial rows).
- Path safety: assert the stored path stays inside the storage root.
- Round-trip: export then re-import, or parse the generated file, and compare content.
- Download deny: request another user's file ID and a guessed link; assert denial without existence hints.
- Large exports: assert streaming (chunked response or bounded memory) and file validity.

## Forbidden

- Tests with one well-formed sample file only.
- Trusting extension or client MIME type alone.
- Using client file names as storage paths.
- Loading whole large files into memory when streaming is in scope.
- Silently skipping invalid rows.
- Public or guessable download links for private files.

## References

- references/test-idioms.md
