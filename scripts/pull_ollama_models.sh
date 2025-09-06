#!/usr/bin/env bash
set -euo pipefail
echo 'pulling nomic-embed-text'
docker compose exec ollama ollama pull nomic-embed-text
