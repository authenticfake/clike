# Test idioms: AI guardrails

A fake model adapter replays recorded responses; every check is deterministic and offline.

## Python

- Model port + fake: `FakeModel(responses=[...])` injected into the service; record real responses once into fixtures (JSON) and replay them.
- Schema: pydantic models for the output; AIR-01 feeds invalid payloads and asserts `ValidationError` handling and no repository write.
- Timeout: the fake raises `TimeoutError` (or never answers within an injected short timeout); assert the fallback message.
- Eval set: `@pytest.mark.parametrize` over `eval_cases.jsonl`, scored by code (exact label, field match, cited ids subset); a final test asserts the pass rate ≥ the threshold.
- Retrieval: an in-memory vector index over fixture documents with owners; assert scoped results and the abstain path.

## TypeScript / web

- Model client interface with a fake returning recorded responses; validate output with a schema (zod); vitest table tests for the eval set with a computed pass rate.
- Streaming UIs: feed the fake stream chunk by chunk and assert the partial and final visible text, and the error text when the stream breaks.

## Java

- Interface for the model client, fake in tests; Jackson + Bean Validation for the output; JUnit `@ParameterizedTest` with `@MethodSource` over the eval set.

## .NET

- `IChatClient`-style abstraction with a fake; `System.Text.Json` + validation; xUnit `[Theory]` over the eval set with a pass-rate assertion.

## Go

- Interface for the model client and a fake; `encoding/json` with strict decoding (`DisallowUnknownFields` where the schema is closed); table-driven eval cases with a pass-rate check.
