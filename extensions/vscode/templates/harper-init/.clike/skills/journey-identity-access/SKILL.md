---
name: journey-identity-access
description: Use when a product has accounts, sign-in, roles or sessions, to enumerate and prove the identity and access scenarios (failure, lockout, expiry, deny, recovery) and not only the successful login.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: IAM
scenarios:
  - IAM-01 | required | Registration and verification | When a visitor submits valid registration data, the system shall create the account pending verification and show how to complete the verification.
  - IAM-02 | required | Successful login | When a verified user submits correct credentials, the system shall start an authenticated session and land the user on the expected page or resource.
  - IAM-03 | required | Wrong credentials | If a user submits a wrong identifier or password, then the system shall reject the login with one generic message that does not reveal which field was wrong.
  - IAM-04 | required | Lockout and rate limit | If repeated failed logins exceed the configured threshold, then the system shall throttle or lock the account and tell the user when and how to retry.
  - IAM-05 | required | Password reset and recovery | When a user requests a password reset, the system shall send a single-use, time-limited link or code and reject it once used or expired.
  - IAM-06 | required | Session expiry and refresh | If a session or token has expired, then the system shall refresh it when allowed, otherwise require re-authentication and return the user to the page they were on.
  - IAM-07 | required | Logout | When a user logs out, the system shall invalidate the session server-side so that a replayed token or cookie is rejected.
  - IAM-08 | required | Permission deny | If an authenticated user requests an action outside their role, then the system shall deny it with 403 (or the lane equivalent) and the UI shall show a permission-denied state instead of the action.
  - IAM-09 | conditional | [MFA required] Second factor | When MFA is enabled for an account, the system shall require a valid second factor before granting the session and reject wrong or reused codes.
  - IAM-10 | conditional | [User administration exists] User and role administration | When an administrator creates, disables or changes the role of a user, the system shall apply the change on the user's next request and record who made it.
  - IAM-11 | conditional | [Personal data stored] Account deletion and data export | When a user requests deletion or export of their account data, the system shall confirm the request, complete it within the stated policy and prevent further login after deletion.
  - IAM-12 | conditional | [Multiple sessions allowed] Concurrent sessions and revocation | When a user or administrator revokes sessions (including logout everywhere), the system shall reject every revoked session on its next request.
  - IAM-13 | required | No account enumeration | If registration, login or password reset names an account that does or does not exist, then the system shall give the same response and message, so that the reply does not reveal whether the account exists.
  - IAM-14 | conditional | [Cookie-based sessions] Cross-site request forgery | If a state-changing request lacks a valid anti-forgery token or comes from a foreign origin, then the system shall reject it without side effects.
  - IAM-15 | conditional | [Server-side sessions or session cookies] New session at login | When a user authenticates, the system shall issue a new session identifier and invalidate the one used before login.
  - IAM-16 | conditional | [Refresh tokens issued] Refresh token rotation and reuse | If a refresh token that was already exchanged is presented again, then the system shall reject it and revoke every token issued from the same login (each exchange issues a new refresh token and retires the used one).
  - IAM-17 | conditional | [Local passwords] Password policy | If a new password is shorter than the policy or is a known breached or common password, then the system shall reject it with a message naming the rule.
  - IAM-18 | conditional | [Local passwords or editable email] Credential change | When a user changes the password, the system shall end the user's other sessions; when a user changes the email, the system shall verify the new address before using it.
  - IAM-19 | conditional | [Single sign-on] Federated sign-in checks | If the state, nonce or PKCE verifier of a federated sign-in is missing or does not match, then the system shall abort the sign-in without creating a session.
obligations:
  - Enumerate every IAM scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Assert the user-visible message text for every failure scenario, not only the status code
  - Never reveal account existence through login, reset or registration messages
eval_checks:
  - scenario-coverage
  - failure-message-asserted
  - server-side-session-invalidation-tested
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-permission-deny-untested
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Identity and Access

## Intent

Make identity and access complete by construction. A login form that works with the right password is not an identity feature: the wrong password, the locked account, the expired session, the reset link used twice and the user without permission are the journeys that decide whether the slice is promotable.

## Use when

- Use cases or REQs mention login, sign-in, sign-up, account, user, password, session, token, SSO, role, permission, admin, tenant, profile, MFA, OTP, logout, "only managers can ...".
- The product has more than one kind of user, or any action that must be restricted.
- An operator console or HMI requires an operator identity for commands.

## Do not use when

The product has no accounts, sessions or roles (a public read-only page, a batch job without users), or identity is fully outside the solution and no integration point is built.

## How the pipeline uses it

- **SPEC**: list every scenario in a `## Scenarios` section. Each `required` scenario is included, or excluded with a reason. Each `conditional` scenario is included when its bracketed condition holds, otherwise marked not applicable with one line.
- **PLAN**: assign each included scenario ID to exactly one owning REQ in plan.json `scenarios`, and add an acceptance item starting with the ID (for example `IAM-04: after 5 failed logins ...`).
- **KIT**: write one blocking check per included scenario and record it in docs/ACCEPTANCE.json with the scenario ID; UI-facing scenarios also get a journey test that reads the visible text.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion. A scenario silently missing from SPEC is a finding.

## Valid exclusions

- Authentication is delegated to an external identity provider: IAM-01, IAM-03, IAM-04, IAM-05, IAM-09 may be excluded, but the integration point still needs a test (token validation, expired or forged token rejected, role claims mapped).
- Single-user local tool with no remote access: IAM-08 may be excluded with that reason stated.
- Machine-to-machine API with no human users: registration and reset excluded; credential rotation and revocation remain in scope.
- Not a valid reason: "first release", "later", "framework handles it" without a test of the configuration.

## Proof per scenario

- Drive the real entry point (HTTP route, UI, CLI, HMI command), not the internal helper.
- Assert the outcome and the message: status or result code, the exact or pattern-matched message text, and the absence of sensitive detail (no stack trace, no "user not found").
- Time-dependent scenarios (expiry, reset link, lockout window) use a controlled clock, never real sleeps.
- Lockout: N-1 failures still allow login, the Nth locks, the unlock or retry-after path works.
- Logout and revocation: capture the token or cookie before, replay it after, expect rejection.
- Permission deny: assert both the server rejection and that the UI shows a deny state or hides the action; a hidden button alone is not proof.

## Forbidden

- Happy-path-only tests (successful login and nothing else).
- Asserting only status codes without the user-visible message.
- Mocking the authentication or authorization layer in the test that claims to prove it.
- Client-side-only permission checks.
- Distinct messages for "unknown user" and "wrong password".
- Real sleeps for expiry, or tests that depend on wall-clock time.

## References

- references/test-idioms.md
