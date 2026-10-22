#!/usr/bin/env bash
# /autopilot of CLike from a terminal, Claude Code or Codex, through the extension MCP server
# (VS Code open on the project, clike.mcp.extensionServerEnabled = true).
#
#   scripts/clike-autopilot.sh [--via direct|claude|codex] start [N] [--executor cloud|codex|claude] [--methodology bmad]
#   scripts/clike-autopilot.sh status | stop | wait     # read, stop after the step, wait for the end
#
# N = stop after N promoted REQs. --executor: who writes KITs and repairs in this run (default: as
# configured in VS Code, restored at the end); --methodology bmad: BMAD developer / QA advisory.
# --via direct (default) calls the MCP server with curl; claude / codex make that agent call the
# harper_autopilot tool (its clike-ext MCP server configured as in docs/howto-mcp-project.md).
# Waiting never uses an agent: `wait` polls the server with curl (no tokens) and prints the final
# status; the full report is runs/autopilot/report.md in the project.
#
# Env: CLIKE_EXT_MCP_TOKEN (CLike: Copy Extension MCP Token), CLIKE_EXT_MCP_URL
# (default http://localhost:55742/mcp), CLIKE_AUTOPILOT_POLL_SECONDS (default 300).
set -euo pipefail

URL="${CLIKE_EXT_MCP_URL:-http://localhost:55742/mcp}"
POLL="${CLIKE_AUTOPILOT_POLL_SECONDS:-300}"
VIA="direct"
if [ "${1:-}" = "--via" ]; then VIA="${2:-}"; shift 2; fi
ACTION="${1:-status}"
[ $# -gt 0 ] && shift
MAX=0
EXECUTOR=""
METHODOLOGY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --executor) EXECUTOR="${2:-}"; shift 2 ;;
    --methodology) METHODOLOGY="${2:-}"; shift 2 ;;
    *) MAX="$1"; shift ;;
  esac
done

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
case "$ACTION" in start|status|stop|wait) ;; *) usage ;; esac
case "$VIA" in direct|claude|codex) ;; *) usage ;; esac
case "$MAX" in ''|*[!0-9]*) echo "N must be a number" >&2; exit 2 ;; esac
case "$EXECUTOR" in ''|cloud|codex|claude) ;; *) echo "--executor must be cloud, codex or claude" >&2; exit 2 ;; esac
case "$METHODOLOGY" in ''|bmad) ;; *) echo "--methodology must be bmad" >&2; exit 2 ;; esac

# One tools/call of harper_autopilot; prints the tool's JSON result.
call() {
  local action="$1"
  if [ -z "${CLIKE_EXT_MCP_TOKEN:-}" ]; then
    echo "CLIKE_EXT_MCP_TOKEN is not set (VS Code: CLike: Copy Extension MCP Token)." >&2; exit 1
  fi
  local body
  body=$(printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"harper_autopilot","arguments":{"action":"%s","max_reqs":%s,"executor":"%s","methodology":"%s"}}}' \
    "$action" "$MAX" "$EXECUTOR" "$METHODOLOGY")
  curl -sS --max-time 60 -X POST "$URL" \
    -H "Authorization: Bearer ${CLIKE_EXT_MCP_TOKEN}" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' -d "$body" |
    python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["result"]["content"][0]["text"] if "result" in r else json.dumps(r.get("error", r)))'
}

field() { python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('$1') if d.get('$1') is not None else '')"; }

agent_prompt() {
  local extra=""
  [ "$MAX" != "0" ] && extra=", max_reqs: $MAX"
  [ -n "$EXECUTOR" ] && extra="$extra, executor: \"$EXECUTOR\""
  [ -n "$METHODOLOGY" ] && extra="$extra, methodology: \"$METHODOLOGY\""
  printf 'Call the clike-ext MCP tool harper_autopilot with {action: "%s"%s}. Do nothing else: no other tool, no file change. Reply only with the JSON it returns.' "$1" "$extra"
}

if [ "$ACTION" = "wait" ]; then
  last=""
  while true; do
    snap=$(call status)
    running=$(printf '%s' "$snap" | field running)
    line=$(printf '%s' "$snap" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("current=%s promoted=%s parked=%s outcome=%s" % (d.get("current"), d.get("promoted"), [p["req_id"] for p in d.get("parked") or []], d.get("outcome")))')
    [ "$line" != "$last" ] && echo "$(date '+%H:%M') $line" && last="$line"
    [ "$running" = "True" ] || break
    sleep "$POLL"
  done
  printf '%s\n' "$snap"
  exit 0
fi

case "$VIA" in
  direct) call "$ACTION" ;;
  claude) claude -p "$(agent_prompt "$ACTION")" --allowedTools "mcp__clike-ext__harper_autopilot" ;;
  codex)  codex exec "$(agent_prompt "$ACTION")" ;;
esac
