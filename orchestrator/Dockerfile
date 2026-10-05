# ===== Base image =====
FROM python:3.12-slim AS base

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

# ===== Browser runtime libraries (optional, for Playwright/Puppeteer e2e checks in the eval sandbox) =====
# Only the system libraries: the browser itself is downloaded at eval time in the version the
# project's Playwright expects (EvalRunner runs `npx playwright install chromium` on demand).
ARG ENABLE_BROWSER=true
RUN if [ "$ENABLE_BROWSER" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libdbus-1-3 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64 \
        libpango-1.0-0 libcairo2 libx11-6 libxcb1 libxext6 fonts-liberation && \
      rm -rf /var/lib/apt/lists/* ; \
    else echo "Skip browser libraries"; fi

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

# ===== Python deps (locked, uv) =====
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml uv.lock /app/
# Runtime deps + the tools KIT LTC commands may call while eval still runs here (WP6 moves eval to sandboxes)
RUN uv sync --frozen --no-dev --group eval-toolchain


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

# ===== Non-root runtime user (WP4) =====
# uid 1000; on Podman for macOS files written to bind mounts show up as the host user.
RUN useradd --create-home --uid 1000 --shell /bin/bash clike \
 && mkdir -p /runs /app/runs \
 && chown -R clike:clike /runs /app/runs
USER clike
ENV HOME=/home/clike

EXPOSE 8080

CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080"]
