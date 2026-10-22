# /autopilot of CLike from PowerShell, Claude Code or Codex, through the extension MCP server
# (VS Code open on the project, clike.mcp.extensionServerEnabled = true). Same as clike-autopilot.sh:
#
#   scripts/clike-autopilot.ps1 [-Via direct|claude|codex] start [N] [-Executor cloud|codex|claude] [-Methodology bmad]
#   scripts/clike-autopilot.ps1 status | stop | wait
#
# Env: CLIKE_EXT_MCP_TOKEN, CLIKE_EXT_MCP_URL (default http://localhost:55742/mcp),
# CLIKE_AUTOPILOT_POLL_SECONDS (default 300). `wait` polls the server (no agent, no tokens) and prints
# the final status; the full report is runs/autopilot/report.md in the project.
param(
  [ValidateSet('direct', 'claude', 'codex')][string]$Via = 'direct',
  [Parameter(Position = 0)][ValidateSet('start', 'status', 'stop', 'wait')][string]$Action = 'status',
  [Parameter(Position = 1)][int]$Max = 0,
  [ValidateSet('', 'cloud', 'codex', 'claude')][string]$Executor = '',
  [ValidateSet('', 'bmad')][string]$Methodology = ''
)
$ErrorActionPreference = 'Stop'
$Url = if ($env:CLIKE_EXT_MCP_URL) { $env:CLIKE_EXT_MCP_URL } else { 'http://localhost:55742/mcp' }
$Poll = if ($env:CLIKE_AUTOPILOT_POLL_SECONDS) { [int]$env:CLIKE_AUTOPILOT_POLL_SECONDS } else { 300 }

function Invoke-Autopilot([string]$Act) {
  if (-not $env:CLIKE_EXT_MCP_TOKEN) { throw 'CLIKE_EXT_MCP_TOKEN is not set (VS Code: CLike: Copy Extension MCP Token).' }
  $body = @{ jsonrpc = '2.0'; id = 1; method = 'tools/call'
    params = @{ name = 'harper_autopilot'; arguments = @{ action = $Act; max_reqs = $Max; executor = $Executor; methodology = $Methodology } } } | ConvertTo-Json -Depth 5
  $r = Invoke-RestMethod -Method Post -Uri $Url -Body $body -ContentType 'application/json' -TimeoutSec 60 `
    -Headers @{ Authorization = "Bearer $($env:CLIKE_EXT_MCP_TOKEN)"; Accept = 'application/json, text/event-stream' }
  if ($r.error) { throw ($r.error | ConvertTo-Json) }
  return $r.result.content[0].text
}

function Get-AgentPrompt([string]$Act) {
  $extra = if ($Max -gt 0) { ", max_reqs: $Max" } else { '' }
  if ($Executor) { $extra += ", executor: `"$Executor`"" }
  if ($Methodology) { $extra += ", methodology: `"$Methodology`"" }
  return "Call the clike-ext MCP tool harper_autopilot with {action: `"$Act`"$extra}. Do nothing else: no other tool, no file change. Reply only with the JSON it returns."
}

if ($Action -eq 'wait') {
  $last = ''
  while ($true) {
    $text = Invoke-Autopilot 'status'
    $snap = $text | ConvertFrom-Json
    $line = "current=$($snap.current) promoted=$($snap.promoted -join ',') parked=$(($snap.parked | ForEach-Object { $_.req_id }) -join ',') outcome=$($snap.outcome)"
    if ($line -ne $last) { Write-Output "$(Get-Date -Format HH:mm) $line"; $last = $line }
    if (-not $snap.running) { break }
    Start-Sleep -Seconds $Poll
  }
  Write-Output $text
  exit 0
}

switch ($Via) {
  'direct' { Invoke-Autopilot $Action }
  'claude' { claude -p (Get-AgentPrompt $Action) --allowedTools 'mcp__clike-ext__harper_autopilot' }
  'codex' { codex exec (Get-AgentPrompt $Action) }
}
