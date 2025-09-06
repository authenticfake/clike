# CLike Orchestrator API (v1) — Summary

This document summarizes the **stable contracts** used by the VS Code client against the Orchestrator.
All requests are JSON (`application/json; charset=utf-8`). Authentication via `Authorization: Bearer <token>`.
Idempotent writes may include `Idempotency-Key: <uuid>`.

> Full machine-readable schema: see [`openapi.yaml`](./openapi.yaml).

## Endpoints
- `GET /v1/models` — list configured models (proxy of the Gateway)
- `POST /v1/chat` — free Q&A, no FS changes
- `POST /v1/generate` — structured generation (**harper|coding**)
- `POST /v1/apply` — HITL apply to FS + optional Git/PR
- `GET /v1/harper/status` — panel states + policy
- `POST /v1/harper/approve` — approve/reject stage
- `POST /v1/rag/index` — (re)index repo/docs
- `POST /v1/rag/search` — search with citations
- `GET /v1/audit/{audit_id}` — full run details

## Enums
- `PromptMode`: `free` | `harper` | `coding`
- `HarperStage`: `idea` | `spec` | `plan` | `kit`
- `ArtifactType`: `file` | `patch` | `spec` | `plan` | `kit`
- `EvalKind`: `lint` | `unit` | `sast` | `dast` | `uat`
- `ApprovalState`: `pending` | `approved` | `rejected`
- `ModelProfile`: `fast` | `strict` | `cost`
