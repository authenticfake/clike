# Test idioms: files and export

Generate hostile and edge-case fixtures inside the test; assert messages and unchanged storage.

## Python

- pytest + `TestClient` / httpx multipart uploads (`files={"file": ("../../x.csv", b"", "text/csv")}`).
- Use `tmp_path` as the storage root; assert no file exists outside it and none was written on rejection.
- Oversized: generate bytes just over the limit in memory or a spooled temp file; assert early rejection message.
- Type sniffing: wrong magic bytes with a valid extension.
- Encoding: write UTF-8 with BOM and accented values via `csv` / `io`; round-trip and compare.
- Streaming exports: assert a `StreamingResponse` / chunked iteration and parse the result.

## TypeScript / web

- API: supertest `.attach("file", Buffer.from(""), "empty.csv")`; assert status and message body.
- UI: Testing Library `user.upload(input, file)` with empty, too-large and wrong-type `File` objects; assert the visible message and accepted formats.
- Journeys: Playwright `setInputFiles` with buffers; `page.waitForEvent("download")` and read the file to validate content; assert the in-progress and failed states.

## Java

- JUnit 5 + MockMvc `multipart()` with `MockMultipartFile`; `@TempDir` as the storage root.
- Assert `spring.servlet.multipart.max-file-size` maps to a readable message, not a raw exception.
- Streaming: `StreamingResponseBody` asserted with RestAssured.

## .NET

- xUnit + `WebApplicationFactory` with `MultipartFormDataContent`; temp directory as storage root.
- Assert request size limits map to ProblemDetails with the limit in the message.
- `Path.GetFileName` / server-generated names asserted against traversal inputs.

## Go

- `testing` + `httptest` with `mime/multipart` writer; `t.TempDir()` storage root.
- `http.MaxBytesReader` limit asserted; `filepath` containment checked for traversal names.

## Mobile

- Component tests for picker errors (too large, wrong type); emulator E2E for share/download flows and permission prompts.

## IaC

- Policy tests that buckets or shares are private by default, encrypted, with signed short-lived download links and size limits at the edge.

## PLC / SCADA / industrial

- Recipe or configuration file import to a controller tested against a simulator: malformed or out-of-range files rejected with an alarm text, active configuration unchanged.
