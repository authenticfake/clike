#!/usr/bin/env bash
# set -euo pipefail
# echo 'pulling nomic-embed-text'
# docker compose exec ollama ollama pull nomic-embed-text
#!/usr/bin/env bash
set -euo pipefail

# Modelli da scaricare
MODELS=(
  "llama3"
  "nomic-embed-text"
#  "gpt-oss"
#  "codellama:34b"
#  "deepseek-coder:33b"
#da fabio fanta: starcoder, codegeex4, yi-coder -> *** to be read ***
)

run_compose_exec_pull() {
  local compose_cmd="$1"
  local service="$2"

  echo "[i] Using $compose_cmd (service: $service)"
  for m in "${MODELS[@]}"; do
    echo "-> pulling $m ..."
    eval "$compose_cmd exec $service ollama pull \"$m\""
  done
  eval "$compose_cmd exec $service ollama list"
}

# 1) docker compose
if docker compose ps ollama >/dev/null 2>&1; then
  run_compose_exec_pull "docker compose" "ollama"
  exit 0
fi

# 2) podman compose
if command -v podman >/dev/null 2>&1 && podman compose ps ollama >/dev/null 2>&1; then
  run_compose_exec_pull "podman-compose" "ollama"
  exit 0
fi

# 3) host ollama
if command -v ollama >/dev/null 2>&1; then
  echo "[i] Using host ollama"
  for m in "${MODELS[@]}"; do
    echo "-> pulling $m ..."
    ollama pull "$m"
  done
  ollama list
  exit 0
fi

echo "[!] No Ollama instance found (docker compose, podman compose, or host)."
# exit 1
# if docker compose ps ollama >/dev/null 2>&1; then
#   echo "[i] Using docker compose (service: ollama)"
#   for m in "${MODELS[@]}"; do
#     echo "-> pulling $m ..."
#     docker compose exec ollama ollama pull "$m"
#   done
#   docker compose exec ollama ollama list
#   exit 0
# fi

# # Fallback: ollama nativo sull’host
# if command -v ollama >/dev/null 2>&1; then
#   echo "[i] Using host ollama"
#   for m in "${MODELS[@]}"; do
#     echo "-> pulling $m ..."
#     ollama pull "$m"
#   done
#   ollama list
#   exit 0
# fi

# echo "[!] Nessuna istanza Ollama trovata (né docker compose né host)."
# exit 1

podman compose exec ollama ollama pull nomic-embed-text
#podman compose exec ollama ollama pull llama3
podman compose exec ollama ollama list