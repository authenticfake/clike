# INSTALL

How to install CLike on a developer machine: the services (orchestrator, gateway, eval sandbox,
vector store), the VS Code extension, the optional local agents, and the MCP connections that let
Claude Code and Codex use CLike.

## 1. Requirements

| What | Version | Needed for |
|---|---|---|
| VS Code | 1.85 or newer | the CLike chat and commands |
| Podman 5 + `podman-compose` (or Docker Compose v2) | — | the services |
| Container VM memory | **at least 4 GB, 6 GB recommended** | eval sandbox (tests, browser e2e) |
| Provider API keys | OpenAI and/or Anthropic | cloud execution |
| Claude Code CLI (`claude`) and/or Codex CLI (`codex`) | logged in | agent execution (optional) |
| Node.js 22+, Python 3.12 + [`uv`](https://docs.astral.sh/uv/) | — | only to build or develop CLike |

With Podman on macOS, check and raise the VM memory:

```bash
podman machine inspect | grep -i memory
podman machine stop && podman machine set --memory 6144 && podman machine start
```

## 2. Configuration

```bash
cp .env.example .env                 # provider keys + CLIKE_API_TOKEN
cp docker/.env.example docker/.env   # where your projects live, sandbox memory cap
```

| File | Variable | Value |
|---|---|---|
| `.env` | `CLIKE_API_TOKEN` | a secret shared by the services and the extension: `openssl rand -hex 32` |
| `.env` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | the providers you use in cloud execution |
| `docker/.env` | `CLIKE_PROJECTS_DIR` | the host folder that contains your projects (mounted read-only) |
| `docker/.env` | `CLIKE_EVAL_SANDBOX_MEM_LIMIT` | below the VM memory: `3g` with a 6 GB VM, `1g` with 2 GB |
| `docker/.env` | `CLIKE_EVAL_REGRESSION_WORKERS` | promoted REQs regressed at the same time: `2` (default), `1` with a small VM or sandbox |

Your projects live under `CLIKE_PROJECTS_DIR`: the eval sandbox reads them from there.
A project elsewhere (another client folder, a repository you cannot move) is mounted on its own,
read-only: when eval, gate or the `/adopt` baseline start on a project outside these folders, CLike
asks *Mount read-only*. On confirmation it runs `docker/mount-project.sh add <folder>`, which mounts
that folder only (never a parent; it must be a CLike project, with `.clike/project.json`) and recreates
the containers in about a minute. From a terminal: `./mount-project.sh add|remove <folder>`, `list`. The
list (`docker/projects.list`) and the compose override it generates (`docker/compose.projects.yml`) are
git-ignored, and `./rebuild.sh` keeps them.

Optional, for projects whose tests need a real database: `cp docker/eval.env.example docker/eval.env`
(git-ignored, read only by the eval sandbox) and set `CLIKE_EVAL_POSTGRES_URL` to a local PostgreSQL
admin URL as seen from the containers, e.g.
`postgresql://<user>@host.containers.internal:5432/postgres`. CLike then creates a disposable
database per project and REQ at every eval. Put there also the values only you have (a KIT marks
them `external`); everything else the tests need is created by CLike. Recreate the stack after
editing it (`docker/rebuild.sh`).

## 3. Services

```bash
cd docker
podman-compose up -d --build
podman ps --format "{{.Names}} {{.Status}}"     # wait until orchestrator, gateway, eval-sandbox, eval-tools are (healthy)
curl -s http://127.0.0.1:8080/health && curl -s http://127.0.0.1:8000/health
```

Services listen on `127.0.0.1` only. After an update: `cd docker && ./rebuild.sh` (cached build, recreated containers, health and image check; the eval tools are restored from their lock). `./rebuild.sh --update-tools` also updates the eval tools to their latest versions and prints what changed.
With projects mounted by `mount-project.sh`, restart the stack with `./rebuild.sh` (or `./rebuild.sh --no-build`): a plain `podman-compose up` does not read `compose.projects.yml` unless given `-f docker-compose.yml -f compose.projects.yml`.

## 4. VS Code extension

Install the packaged extension (or build it from source):

```bash
code --install-extension extensions/vscode/clike-1.6.9.vsix
# from source: cd extensions/vscode && npm ci && npm run check && npm run package
```

Then in VS Code:

1. **CLike: Set Service Token** → paste the `CLIKE_API_TOKEN` value.
2. Open a project folder located under `CLIKE_PROJECTS_DIR`.
3. **CLike: Chat (Q&A / Harper / Coding)**.

## 5. Local agents (optional)

CLike runs Claude Code or Codex with **their own login** (never with the cloud API keys):

```bash
claude            # log in once (subscription), then exit
codex login       # or an API key login
```

In the CLike chat: `/agent-default claude|codex|auto` picks the agent, `/agent-model list` shows the
models, `/agent-model claude opus` (or `sonnet`, an exact id) sets one, and the Execution selector
chooses cloud or agent. `/agent-model` without arguments shows the current setup.

## 6. Use CLike from Claude Code or Codex (MCP)

Two MCP servers, both local (loopback) and token-protected. Register them with `localhost` URLs:
organisation policies for Claude Code often allow only `http://localhost*` MCP servers.

| Server | URL | What it does |
|---|---|---|
| Orchestrator (read-only) | `http://localhost:8080/mcp/` | reads project docs, plan, REQs, runs, RAG (`project_root` selects the project) |
| VS Code extension (operational) | `http://localhost:55742/mcp` | **runs** Harper phases, eval and gate through CLike's governance; needs VS Code open |

Orchestrator MCP (token = `CLIKE_API_TOKEN`; export it in your shell profile, the same value as in
`.env`). Claude Code: a project `.mcp.json` that reads the token from the environment (no secret in
the file):

```json
{ "mcpServers": { "clike": { "type": "http", "url": "http://localhost:8080/mcp/",
  "headers": { "Authorization": "Bearer ${CLIKE_API_TOKEN}" } } } }
```

Codex:

```bash
codex mcp add clike --url http://localhost:8080/mcp/ --bearer-token-env-var CLIKE_API_TOKEN
```

`claude mcp add ... --header "Authorization: Bearer $CLIKE_API_TOKEN"` works too, but expands the
token when you run it (empty if the variable is not set). A "Dynamic Client Registration rejected
(HTTP 401)" error means the header is missing: CLike has no OAuth. A whole project driven from
Claude Code or Codex: [howto-mcp-project.md](howto-mcp-project.md).

Extension MCP: enable `clike.mcp.extensionServerEnabled`, run **CLike: Copy Extension MCP Token**,
then:

```bash
export CLIKE_EXT_MCP_TOKEN=<copied token>
claude mcp add --transport http clike-ext http://localhost:55742/mcp --header "Authorization: Bearer $CLIKE_EXT_MCP_TOKEN"
codex mcp add clike-ext --url http://localhost:55742/mcp --bearer-token-env-var CLIKE_EXT_MCP_TOKEN
```

Codex asks to approve every MCP tool call (and in `codex exec` it cannot ask). CLike's tools are
governed by CLike itself (locked tests, gate, write rules, no overrides from MCP), so approve them
once in `~/.codex/config.toml`:

```toml
[mcp_servers.clike]
default_tools_approval_mode = "approve"

[mcp_servers.clike-ext]
default_tools_approval_mode = "approve"
```

Or for one run only: `codex exec -c 'mcp_servers.clike.default_tools_approval_mode="approve"' ...`.
Claude Code asks once per tool in interactive sessions; to pre-approve, add `"mcp__clike"` and
`"mcp__clike-ext"` to `permissions.allow` in its settings.

## 7. Check

| Check | How |
|---|---|
| Services | `curl -s http://127.0.0.1:8080/health` |
| Chat | Harper mode, `/help` |
| Agent | `/agent-model` shows the default agent and models |
| Telemetry portal | `http://127.0.0.1:8000/v1/metrics/harper/ui` (log in with the service token) |

Next: [GET STARTED](GET_STARTED.md).
