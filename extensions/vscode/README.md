
# Clike VS Code Extension (v0.5.3)

**What’s included**
- Full command set (Code Action, Add Docstring, Refactor, Generate Tests, Fix Errors, RAG, List Models, Hardened Apply).
- Robust diff preview (fixed URIs).
- Defaults: `clike.git.openPR = false`.

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
- Orchestrator `/agent/code` with `op` = `add_docstring|refactor|generate_tests|fix_errors`
- Orchestrator RAG `/rag/search`, `/rag/reindex`
- Gateway models `/v1/models`
