# Clike MVP Stage1 — Full Package

## What’s inside
- **configs/models.yaml**: routing policies (capability, latency, cost, privacy, frontier) + providers
- **gateway/**: OpenAI-compatible endpoints `/v1/chat/completions`, `/v1/models` + privacy guard
- **orchestrator/**: `/agent/code` returns **diff + new_content + rationale**
- **extensions/vscode/**: commands
  - `Clike: Refactor (Diff-First)`
  - `Clike: Apply Last Patch`
- **docker/docker-compose.yml**: gateway, orchestrator, vLLM, Ollama

## Run all
```bash
cd docker
docker compose up -d --build
```

## Quick test
```bash
# models
curl -s http://localhost:8000/v1/models | jq

# gateway chat (no code)
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "messages":[{"role":"user","content":"Say hi"}],
  "intent":"spec"
}' | jq

# orchestrator diff
curl -s http://localhost:8080/agent/code -H "Content-Type: application/json" -d '{
  "intent":"new_file",
  "path":"apps/fe/src/lib/hello.ts",
  "prompt":"Create a hello() function and a comment",
  "language":"typescript"
}' | jq
```

## VS Code extension (dev install)
Open **extensions/vscode** in VS Code → press **F5** (Extension Development Host).  
Commands:
- `Clike: Refactor (Diff-First)` → generates diff + stores `new_content`
- `Clike: Apply Last Patch` → writes `new_content` to the file

## Notes
- Enable cloud providers in `configs/models.yaml` only if needed; set env keys before running.
- Privacy guard: with `never_send_source_to_cloud=true`, requests that include source code to cloud LLMs will be blocked.
