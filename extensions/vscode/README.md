
# Clike VS Code Extension (v0.5.3)

**What’s included**

- Full command set (CLike: Open Chat (Q&A / Harper / Coding), Code Action+, Add Docstring, Refactor, Generate Tests, Fix Errors, RAG, List Models, Hardened Apply).

- Vibe Coding is the UX/frontier practice → developer stays in flow, but it needs AI-Native SWE to scale to enterprise.
- Harper-Style builds on this: IDEA → SPEC → PLAN → KIT with HITL validation.
-EDD ensures governance and code quality (eval gates at every step).
-MCP + Agent Frameworks provide the technical glue for orchestration and integration.
-GenAI Model Routers are required in Clike Gateway to support multi-model configuration (GPT, Claude, Ollama, etc.).
- Robust diff preview (fixed URIs).
- Defaults: `clike.git.openPR = false`.
- Multi Model and frontier routing policy.

**Configure**

- `clike.orchestratorUrl`: `http://localhost:8080`
- `clike.gatewayUrl`: `http://localhost:8000`

**How to run**

1. Extract the zip and open the folder in VS Code
2. `npm install`
3. Press **F5** to launch the Extension Development Host
4. In that window: `Cmd+Shift+P` → **Clike: Code Action…**

**Smoke test (no backend needed)**
Copy to clipboard:

````
```
new content demo
```
````

Then run **Clike: Apply New Content** to confirm edit flow and preview work.

**Backend calls**

- [CLike github url](https://github.com/authenticfake/clike)
- Orchestrator `/agent/code` with `op` = `add_docstring|refactor|generate_tests|fix_errors`
- Orchestrator RAG `/rag/search`, `/rag/reindex`
- Gateway models `/v1/models`
