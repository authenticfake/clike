# Test idioms: notifications

A fake outbox records every message; assert recipients, counts and visible text.

## Python

- Sender port with `FakeOutbox` (list of messages); Django's `mail.outbox` or the framework equivalent; render templates with the real engine and assert the translated text and escaping.
- Idempotency: process the same event id twice; `assert len(outbox) == 1`.
- Clock: `freezegun` for link expiry.

## TypeScript / web

- Sender interface with an in-memory fake; render templates (MJML, React Email or the engine in use) to HTML and assert text with a DOM parser.

## Java

- Spring: `JavaMailSender` replaced by a fake, or GreenMail as an in-process SMTP server; assert subject, recipient and body.

## .NET

- `ISender` abstraction with a fake; or an in-process SMTP test server; assert rendered Razor templates.

## Go

- Sender interface with a recording fake; `html/template` for escaping, asserted on the rendered body.

## Rust

- Sender trait with a recording fake; templates with an engine that escapes HTML by default (askama, tera); assert the rendered text.
