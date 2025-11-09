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

if docker compose ps ollama >/dev/null 2>&1; then
  echo "[i] Using docker compose (service: ollama)"
  for m in "${MODELS[@]}"; do
    echo "-> pulling $m ..."
    docker compose exec ollama ollama pull "$m"
  done
  docker compose exec ollama ollama list
  exit 0
fi

# Fallback: ollama nativo sull’host
if command -v ollama >/dev/null 2>&1; then
  echo "[i] Using host ollama"
  for m in "${MODELS[@]}"; do
    echo "-> pulling $m ..."
    ollama pull "$m"
  done
  ollama list
  exit 0
fi

echo "[!] Nessuna istanza Ollama trovata (né docker compose né host)."
exit 1
