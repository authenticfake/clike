# ===== Base image =====
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app


# Toggle facoltativi (puoi spegnere Java/Node al build)
ARG ENABLE_JAVA=true
ARG ENABLE_NODE=true

# # ===== System deps di base =====
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     curl ca-certificates git openssh-client \
#     bash coreutils findutils \
#     gcc g++ make \
#     # util per debug/health (opzionale)
#     procps \
#   && rm -rf /var/lib/apt/lists/*
# Harden APT against flaky mirrors/CDN
ENV DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    # Detect codename (e.g., trixie/bookworm)
    codename="$(. /etc/os-release && echo "${VERSION_CODENAME:-bookworm}")"; \
    # Ensure APT sources exist and use HTTPS (handles both classic and deb822 formats)
    if [ -f /etc/apt/sources.list ]; then \
        sed -i -E 's|http://([^ ]+)|https://\1|g' /etc/apt/sources.list; \
    elif ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; then \
        sed -i -E 's|^(URIs:\s*)http://|\1https://|g' /etc/apt/sources.list.d/*.sources; \
    else \
        printf "deb https://deb.debian.org/debian %s main\n" "$codename" > /etc/apt/sources.list; \
        printf "deb https://deb.debian.org/debian %s-updates main\n" "$codename" >> /etc/apt/sources.list; \
        printf "deb https://security.debian.org/debian-security %s-security main\n" "$codename" >> /etc/apt/sources.list; \
    fi; \
    # (opzionale) forzare mirror Cloudflare se i 500 persistono
    # if grep -q deb.debian.org /etc/apt/sources.list 2>/dev/null; then sed -i 's|deb.debian.org|cloudflare.debian.org|g' /etc/apt/sources.list; fi; \
    # if ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; then sed -i 's|deb.debian.org|cloudflare.debian.org|g' /etc/apt/sources.list.d/*.sources; fi; \
    # APT hardening: retry, timeouts, no-cache (abilita ForceIPv4 se la tua rete rompe IPv6)
    printf 'Acquire::Retries "5";\nAcquire::http::No-Cache "true";\nAcquire::https::No-Cache "true";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/99-retries; \
    # echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99-force-ipv4; \
    # Update + install with retries
    apt-get update; \
    for i in 1 2 3 4 5; do \
        apt-get install -y --no-install-recommends \
            curl ca-certificates git openssh-client \
            bash coreutils findutils \
            gcc g++ make procps \
        && break || (echo "apt install failed, retry $i/5"; sleep 5; apt-get update); \
    done; \
    rm -rf /var/lib/apt/lists/*


# ===== Java (facoltativo) =====
# openjdk-17-jre-headless non è più disponibile -> usa OpenJDK 21
RUN if [ "$ENABLE_JAVA" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
      rm -rf /var/lib/apt/lists/* ; \
    else echo "Skip Java"; fi

# ===== Node.js 20 (facoltativo, per prettier/eslint) =====
RUN if [ "$ENABLE_NODE" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends gnupg && \
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
      apt-get install -y --no-install-recommends nodejs && \
      rm -rf /var/lib/apt/lists/* ; \
    else echo "Skip Node"; fi

# Tool JS globali (solo se Node abilitato)
RUN if command -v npm >/dev/null 2>&1; then \
      npm i -g --silent prettier eslint; \
    else \
      echo "npm non presente, salto prettier/eslint"; \
    fi

# ===== Google Java Format (jar) =====
# Scaricalo solo se Java abilitato
RUN if [ "$ENABLE_JAVA" = "true" ]; then \
      curl -L -o /usr/local/bin/google-java-format.jar \
      https://github.com/google/google-java-format/releases/download/v1.22.0/google-java-format-1.22.0-all-deps.jar ; \
    else echo "Skip GJF jar"; fi

# ===== Python deps =====
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ===== App source =====
COPY . /app

# ===== Env toggle per tool esterni (di default ON, spegnili se non installi i binari) =====
ENV CLIKE_TOOLS_PY_BLACK=true \
    CLIKE_TOOLS_PY_ISORT=true \
    CLIKE_TOOLS_PY_RUFF=true \
    CLIKE_TOOLS_TS_PRETTIER=true \
    CLIKE_TOOLS_TS_ESLINT=false \
    CLIKE_TOOLS_JAVA_GJF=true \
    CLIKE_TOOLS_GO_FMT=true \
    CLIKE_TOOLS_GO_IMPORTS=true

# Se non hai installato Java/Node al build, spegni i flag relativi:
# (puoi anche farlo da docker-compose environment:)
# ENV CLIKE_TOOLS_JAVA_GJF=false
# ENV CLIKE_TOOLS_TS_PRETTIER=false
# ENV CLIKE_TOOLS_TS_ESLINT=false

EXPOSE 8080

# Avvio orchestrator (dev: reload)
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080","--reload"]
