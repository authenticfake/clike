---
name: secure-config-secrets
description: Enforce safe configuration, secret handling, auth boundaries, restricted egress, and security evidence for promotable software.
phases: ["spec", "plan", "kit", "eval", "gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "iac", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
obligations:
  - Keep secrets in environment/config providers; never hardcode credentials, tokens, API keys, or private URLs
  - Provide .env.example (or equivalent) when environment variables are introduced
  - Fail fast on missing production-critical configuration
  - Redact sensitive payloads, raw prompts, and document content from logs and audit
eval_checks:
  - no-hardcoded-secrets
  - env-example-present
  - missing-config-deny-path-tested
  - sensitive-log-redaction-tested
gate_implications:
  - block-if-hardcoded-secrets-or-credentials
  - block-if-production-endpoint-hardcoded-without-approval
  - block-if-missing-config-falls-back-to-unsafe-behavior
  - block-if-frontend-contradicts-backend-authorization
evidence_required:
  - Tests for deny paths or missing config where relevant
  - .env.example or configuration docs
  - Fake-client tests for external providers
  - HOWTO configuration section
---

# Secure Config Secrets Skill

## Intent

Generated software must be safe by default.

This skill prevents hardcoded secrets, unsafe defaults, leaked prompts or document content, hidden production endpoints, unrestricted egress, insecure local shortcuts promoted as production behavior, and auth/security claims without evidence.

## Use when

Use this skill when a REQ touches:

- authentication;
- authorization;
- RBAC;
- OIDC/SAML;
- API keys;
- secrets;
- environment variables;
- cloud/on-prem runtime;
- external providers;
- database connections;
- queues;
- object storage;
- AI providers;
- document content;
- logs;
- audit;
- deployment;
- network egress.

## Do not use when

Do not use this skill for pure algorithmic code with no configuration, no I/O, no external calls, no secrets, and no security-sensitive data.

## Required behavior

Generated code must:

- keep secrets in environment/config providers;
- never hardcode credentials, tokens, API keys, private URLs, or passwords;
- provide `.env.example` or equivalent when environment variables are introduced;
- distinguish local-dev defaults from production requirements;
- fail fast on missing production-critical configuration;
- redact sensitive payloads from logs and audit;
- avoid raw prompt logging for AI features unless explicitly allowed;
- keep provider SDKs behind approved boundaries when the plan requires adapters;
- document required configuration and safe defaults.

## Authentication and authorization

When auth/RBAC is touched:

- backend remains source of truth for authorization;
- frontend may hide/disable actions but must handle backend denials;
- user identity and roles must be explicit in contracts;
- local-dev auth must be clearly marked and not presented as production auth;
- OIDC/SAML or IdP integration must be configurable, not hardcoded.

## Network and provider security

When external calls are touched:

- keep endpoints configurable;
- prefer allowlists or restricted egress policy when enterprise/on-prem profiles apply;
- do not perform live provider calls in blocking unit tests;
- fake clients are acceptable for deterministic local tests;
- document live-provider checks as opt-in unless required and configured.

## AI/security-specific behavior

For AI/RAG/tooling:

- raw prompts and confidential content must not be logged by default;
- prompt injection must not override system policy;
- model output must be validated before business action;
- AI must not mutate business state unless explicit user action and policy allow it;
- provider metadata must be redacted;
- citations and retrieval scope must not leak unauthorized content.

## Required evidence

When this skill applies, KIT should include:

- tests for deny paths or missing config where relevant;
- no-secret scan or static check where tooling exists;
- `.env.example` or config docs;
- redaction tests for sensitive logs/payloads where relevant;
- fake-client tests for external providers;
- HOWTO configuration section.

## Forbidden behavior

- Do not commit secrets or realistic credentials.
- Do not hardcode production URLs.
- Do not use local-dev auth as production auth.
- Do not log full documents, raw prompts, tokens, API keys, or passwords.
- Do not ignore backend deny responses in frontend.
- Do not use unrestricted provider calls from business logic.
- Do not make tests depend on real credentials.
- Do not claim GDPR/security compliance without evidence and scope.

## Gate implications

Gate must BLOCK promotion when:

- secrets or credentials are hardcoded;
- production endpoints are hardcoded without explicit approval;
- missing config silently falls back to unsafe behavior;
- auth/RBAC is bypassed;
- frontend contradicts backend authorization;
- AI/provider calls leak raw sensitive content;
- selected runtime profile requires restricted egress and the code ignores it;
- generated docs omit required security configuration.

Gate may WARN when:

- advanced security scanning is unavailable locally but deterministic checks pass;
- production IdP integration is deferred and local-dev auth is clearly marked;
- optional live provider security checks are documented but not run locally.

## Success definition

The skill is satisfied when local execution is convenient, production configuration is explicit, secrets are externalized, sensitive data is redacted, and promotion does not depend on trusting hidden security assumptions.