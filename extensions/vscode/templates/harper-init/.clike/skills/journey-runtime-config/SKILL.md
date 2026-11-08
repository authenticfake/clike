---
name: journey-runtime-config
description: Use when a REQ adds a runnable service, configuration, secrets, external providers or a runtime profile (local, cloud, on-prem, edge), to prove the app starts on local defaults, fails fast on missing production config, keeps secrets out of code and logs, and runs the same in the eval sandbox as in production.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "backend", "frontend", "iac", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: CFG
scenarios:
  - CFG-01 | required | Starts on local defaults | When the application starts with only the documented local configuration (.env.example) and no external infrastructure, the system shall select its local adapters, start and answer its smoke check.
  - CFG-02 | required | Missing production configuration fails fast | If a value required by the selected runtime profile is missing or invalid, then the system shall refuse to start and name the variable, never falling back to an unsafe default.
  - CFG-03 | required | No secrets in delivered files | The system shall read every secret, credential and environment-specific endpoint from configuration, and the delivered files shall contain none.
  - CFG-04 | required | Sensitive data redacted in logs | When the system logs requests, errors or provider calls, it shall redact passwords, tokens, keys, personal data and confidential content.
  - CFG-05 | required | Configuration documented completely | The system shall list every configuration variable it reads in .env.example (or the lane's equivalent) with its purpose, and no listed variable shall be unused.
  - CFG-06 | required | Production adapters only on explicit selection | When no runtime profile is selected, the system shall use local or fake adapters; it shall call real cloud, SaaS or plant systems only when the configuration selects them.
  - CFG-07 | conditional | [A frontend calls a backend] Frontend and backend routes match | When the frontend calls the backend, every route it calls shall exist on the backend with the method and payload the frontend uses.
  - CFG-08 | conditional | [The service is deployed and monitored] Health and readiness | When a required dependency is unreachable, the system shall report not ready on its readiness endpoint while its liveness endpoint stays healthy.
  - CFG-09 | conditional | [Restricted egress: enterprise, on-prem, air-gapped] Outbound allowlist | If code tries to call a host that is not in the configured allowlist, then the system shall refuse the call and log the refused host.
obligations:
  - Keep domain logic behind ports; real providers are adapters selected by configuration
  - Provide a local or fake adapter for every external system the blocking checks touch
  - Ship .env.example with every variable and its purpose; never a real value
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-secret-in-delivered-files
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - .env.example and the HOWTO configuration section
---

# Journey: Runtime and Configuration

## Intent

Most "works on my machine" failures and most leaks come from configuration: a service that needs
a cloud account to start, a default that silently points at production, a key in the code, a token
in the logs, a frontend calling a route the backend never had. This journey makes each of them a
tested scenario, so the slice runs in the eval sandbox, on a laptop and in production the same way.

## Use when

- The REQ adds or changes a service entrypoint, configuration, environment variables, secrets,
  provider clients (database, queue, storage, identity, AI, SaaS, plant systems) or runtime profiles.
- A frontend and a backend are delivered or wired together.

## Do not use when

Pure library or algorithmic code with no configuration, no I/O and no entrypoint.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; name the runtime profiles and, per external
  system, its local stand-in (fake, in-memory, simulator, disposable database).
- **PLAN**: the REQ that creates the application owns CFG-01/02/05/06 (and CFG-08); later REQs own
  CFG-03/04 for what they add, and CFG-07 for the routes they wire.
- **KIT**: one blocking check per included scenario; real-provider checks are `blocking: false`
  with `environment_requirements`, or get their values from CLike (`environment.required_variables`).

## Valid exclusions

- No frontend: CFG-07. Not deployed as a service (CLI, batch, library): CFG-08.
- Open egress by policy: CFG-09.
- Not valid: "secrets are handled by the platform" without a scan proving the files hold none.

## Proof per scenario

- CFG-01: start the app in the test with only `.env.example` values (subprocess or app factory),
  call the smoke route, assert the local adapter is in use.
- CFG-02: start with the production profile and one required value removed; assert the startup error
  names it.
- CFG-03: a blocking check scans the delivered files for secret patterns (keys, tokens, private keys,
  connection strings with passwords) and fails on a hit; test fixtures use obvious fakes.
- CFG-04: log a request carrying a password, a token and an e-mail; capture the log and assert they
  are masked.
- CFG-05: a test parses `.env.example` and the settings model (or greps the reads) and compares the sets.
- CFG-07: a test lists the frontend API client's calls and the backend's routes (router table or
  OpenAPI) and asserts every call has its route.

## Forbidden

- Blocking checks that need internet, real credentials, containers or a server started by hand.
- Defaults that point at production, or a fake adapter selected silently in production.
- Provider SDKs called from domain logic; endpoints, tenants, regions, buckets, queue names or device
  ids hardcoded.
- Logging full documents, prompts, tokens, keys or passwords.
- Treating a fake adapter as proof of production readiness: say what was validated where in HOWTO.

## References

- references/test-idioms.md
