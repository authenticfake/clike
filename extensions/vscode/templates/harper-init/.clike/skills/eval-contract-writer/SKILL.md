---
name: eval-contract-writer
description: Use for every KIT that ships code, tests or CI, to emit the proof contract CLike's eval runs — ci/LTC.json cases, docs/ACCEPTANCE.json and tests named after the scenario they prove — so that a failing check means a product defect, not a broken harness.
phases: ["kit", "eval"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "plc-scada", "ai-native", "sql", "data"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - Every acceptance criterion and every owned scenario is proved by a blocking case of ci/LTC.json
  - The test that proves a scenario carries the scenario id in its name or title
  - ci/LTC.json uses only the fields CLike's eval reads (cases[] with name, run, cwd, expect)
  - Never claim a check passed without having run it
eval_checks:
  - ltc-cases-runnable
  - acceptance-coverage
gate_implications:
  - block-if-a-criterion-or-scenario-has-no-blocking-proof
evidence_required:
  - runs/kit/<REQ-ID>/ci/LTC.json
  - runs/kit/<REQ-ID>/ci/HOWTO.md
  - runs/kit/<REQ-ID>/docs/ACCEPTANCE.json
---

# Eval Contract Writer — the proof contract

## Intent

The eval does not read prose. It runs `cases[]` of `ci/LTC.json` in a sandbox without credentials,
then blocks the REQ (`acceptance::coverage`) unless every acceptance criterion and every journey
scenario the plan gives the REQ is proved by a blocking case and by a test that names it. Write the
contract so it runs the first time.

## Use when

Every KIT that ships source, tests, CI, infrastructure code or scripts, and every eval repair.

## Do not use when

Documentation-only REQs with nothing to execute.

## The proof chain (one per criterion and per scenario)

criterion or scenario → test that asserts the visible outcome → blocking case of `ci/LTC.json` that
runs it → entry in `docs/ACCEPTANCE.json` naming that case.

- `docs/ACCEPTANCE.json`: `{"criteria": [{"id": "REQ-001-A01", "status": "done", "checks": ["unit-tests"], "scenarios": ["IAM-03"]}]}` —
  status `done | partial | missing | developer_evidence`; `done` only when the named blocking cases
  verify it. Be truthful: a partial criterion sends the REQ back, a false `done` fails at eval.
- Scenario id in the **test name or title**, one or two ids per test:
  pytest `def test_iam_03_wrong_password_shows_generic_message`, vitest/Playwright
  `it("IAM-03: wrong password shows a generic message", …)`, JUnit `@DisplayName("IAM-03 …")`,
  xUnit method `Iam03_WrongPassword…`, Go `t.Run("IAM_03_wrong_password", …)`, Rust
  `fn iam_03_wrong_password…`, Structured Text `METHOD IAM_03_WrongPassword`. A comment that lists
  many ids proves none.
- Where tests live: under the KIT's `test/` (or the area's tests root), or as the language puts them —
  Go `*_test.go` next to the code, Rust `#[test]` modules, `*.test.ts` / `*.spec.ts`; the eval finds
  them there and nowhere else (never in `docs/` or `ci/`).
- One test proves one behaviour; an error, empty, denied or limit case has its own test and asserts
  the message or state the user or caller sees, not only a status code.

## ci/LTC.json — the fields the eval reads

```json
{
  "version": "1.0",
  "req_id": "REQ-001",
  "lane": "python",
  "cases": [
    {"name": "unit-tests", "run": "pytest -q test", "cwd": "runs/kit/REQ-001", "expect": 0,
     "blocking": true, "env": {"PYTHONPATH": "src"}},
    {"name": "broker-integration", "run": "pytest -q -m integration test", "cwd": "runs/kit/REQ-001",
     "expect": 0, "blocking": false, "environment_requirements": ["kafka"]}
  ],
  "environment": {"required_variables": [
    {"name": "APP_DATABASE_URL", "purpose": "disposable test database", "provision": "postgres_database"}
  ]}
}
```

- `cases[]` is the only executable section; every case has `name`, `run`, `cwd` (relative to the
  project root), `expect`. Optional: `timeout`, `env`, `blocking`, `environment_requirements`.
- Blocking cases run in the sandbox as it is: no internet, no containers, no developer credentials.
  What needs real infrastructure is `blocking: false` with `environment_requirements`, or is
  provided by CLike through `environment.required_variables` (`token`, `uuid`, `timestamp`,
  `template`, `postgres_database`, `service`; `external` only for values only the developer has).
- Do not invent fields (`commands[].cmd`, `requires_external_infra`, `gate_policy`): the eval
  ignores them and the check you meant never runs.
- Declare the runtime versions the project requires in `environment` (`"python": "3.12"`,
  `"node": ">=22"`) and the dependency file the cases need (lockfile install for Node:
  `npm ci`; Python: `requirements_file` or the project manifest).
- Variable names never contain TOKEN, SECRET, PASSWORD, API_KEY or CREDENTIAL (the sandbox refuses
  them); tests never hardcode values.

## ci/HOWTO.md

Copy-paste runnable: prerequisites, the exact commands of the cases, expected results, and the
section `## Run with CLike /eval` (what CLike provisions, the `external` values and their
`docker/eval.env` lines, `/eval <REQ-ID>` and `/eval <REQ-ID> --fix`).

## Forbidden

- Copying tests or test helpers of other REQs into this KIT, or a case that re-runs them: CLike's
  regression already re-runs every promoted REQ's checks with this candidate overlaid.
- Placeholder tests (`assert True`), import-only tests where behaviour is required, skipped or
  `xfail` tests for an acceptance criterion.
- A blocking case that needs production infrastructure, the network or a server started by hand.
- Claiming results you did not run: in a single generation write "to be run by the eval".
- Disabling type checks, lint rules or coverage thresholds globally to get green.

## When the eval fails (repair)

The failing case is the specification. Read its output, fix the source; tests and `ci/` are locked
during `/eval` (only `ci/HOWTO.md` may be corrected). A test that is wrong is corrected without
weakening its assertions. Keep assertions on error classification, status, codes and messages;
narrow types instead of removing them.
