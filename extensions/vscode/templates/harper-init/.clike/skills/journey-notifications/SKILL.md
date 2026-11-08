---
name: journey-notifications
description: Use when the system sends e-mail, SMS, push or in-app notifications, to prove each event is notified once, in the user's language, with safe content, honouring preferences and unsubscribe, with failures retried and visible, and links that expire.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "backend"]
domains: ["enterprise", "startup", "consumer", "industrial"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid"]
gate_required: true
scenario_prefix: NTF
scenarios:
  - NTF-01 | required | Notified once per event | When an event that triggers a notification is processed, possibly more than once, the system shall send one notification per recipient.
  - NTF-02 | required | Rendered in the recipient's language with safe content | When a notification is rendered, the system shall use the recipient's language and escape user-provided values, and include no secrets or more personal data than the purpose needs.
  - NTF-03 | required | Delivery failure retried and visible | If sending fails, then the system shall retry with backoff and, after the retry limit, mark the notification failed with the reason, visible to an operator.
  - NTF-04 | conditional | [Users can choose what they receive] Preferences and unsubscribe honoured | If a recipient has opted out of a notification type or unsubscribed, then the system shall not send it, while still sending mandatory service messages.
  - NTF-05 | conditional | [Notifications carry action links] Links expire and are single use | If a link in a notification is used after its expiry or a second time where it is single use, then the system shall refuse it with a readable message and a way to request a new one.
  - NTF-06 | conditional | [Bursts of events possible] Rate limited per recipient | When many events for one recipient occur in a short time, the system shall group or throttle them according to the stated policy.
obligations:
  - Send through a notification adapter with a fake outbox in tests; blocking checks never send real messages
  - Templates live in files with one version per language
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
---

# Journey: Notifications

## Intent

Users judge a product by its messages: a duplicate e-mail, a reset link in the wrong language, an
unsubscribe that does not work, a failed message nobody sees. This journey proves each of them with a
fake outbox, so the content and the delivery policy are tested, not hoped for.

## Use when

E-mail, SMS, push, chat or in-app notifications, digests, reminders, verification and reset messages.

## Do not use when

The product sends no messages to people (machine-to-machine events belong to journey-integration).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; list the notification types, which are mandatory,
  the languages and the retry policy.
- **PLAN**: the REQ that introduces the notification adapter owns NTF-01/03; each REQ that adds a
  notification type owns NTF-02 (and NTF-04/05) for it.
- **KIT**: tests assert on the fake outbox: recipients, count, subject and body text, links.

## Valid exclusions

- No user preferences (only mandatory service messages): NTF-04, with that reason.
- Not valid: "the e-mail provider deduplicates".

## Proof per scenario

- NTF-01: process the same event twice; assert one message in the outbox.
- NTF-02: recipient with another language and a name containing markup; assert the translated
  subject and the escaped value.
- NTF-03: the fake sender fails N times; assert the attempts and the failed state with its reason.
- NTF-05: use a link twice and after expiry (controlled clock); assert the refusal text.

## Forbidden

- Real e-mail or SMS from tests; templates built by string concatenation of user input.
- Tokens, passwords or full documents in message bodies or logs.

## References

- references/test-idioms.md
