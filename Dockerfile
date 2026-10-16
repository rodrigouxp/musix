# syntax=docker/dockerfile:1.6
#
# Imagem do player (fork do Swing Music) para o homelab.
# Contexto de build: raiz deste repo + o repo do cliente clonado em ./client-src
#   git clone https://github.com/rodrigouxp/swingmusic-webclient client-src
#   docker build -t swingmusic-dev .
#
# A versao vem de version.txt (fonte unica): serve de metadado do pacote e
# tambem vai para <cliente>/version.txt. Isso e OBRIGATORIO: a cada boot o
# servidor compara as duas versoes e, se divergirem, APAGA a pasta do cliente
# e baixa o cliente do upstream (settings.py: ensure_client_matches_app_version).

ARG PYTHON_VERSION=3.11

# ---------- 1. cliente web (fork) ----------
FROM node:22-slim AS client
WORKDIR /client
COPY client-src/package.json client-src/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY client-src/ ./
RUN yarn build --outDir /client-dist

# ---------- 2. servidor: gera o wheel ----------
FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /src
RUN pip install --no-cache-dir setuptools setuptools-scm
COPY pyproject.toml requirements.txt version.txt README.md ./
COPY src/ ./src/
RUN SETUPTOOLS_SCM_PRETEND_VERSION="$(cat version.txt)" \
    pip wheel . --no-deps --no-build-isolation -w /wheels

# ---------- 3. imagem final ----------
FROM python:${PYTHON_VERSION}-slim
WORKDIR /app
LABEL org.opencontainers.image.title="swingmusic-dev" \
      org.opencontainers.image.source="https://github.com/rodrigouxp/swingmusic"
EXPOSE 1970/tcp
VOLUME /music
VOLUME /config

# Logs no `docker logs` e comportamento de container (mesmo do upstream).
ENV PYTHONUNBUFFERED=1 \
    SWINGMUSIC_IN_DOCKER=1 \
    HOME=/music

RUN apt-get update && apt-get install -y --no-install-recommends \
        libev-dev ffmpeg libavcodec-extra \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Dependencias fixadas primeiro (camada cacheada), depois so o wheel do app.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=builder /wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Cliente FORA de /config (o ZimaOS monta uma pasta ali e esconderia a imagem)
# e com o version.txt igual ao do servidor.
COPY version.txt /app/version.txt
COPY --from=client /client-dist /app/client
RUN cp /app/version.txt /app/client/version.txt

HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:1970/')" || exit 1

ENTRYPOINT ["python", "-m", "swingmusic", "--host", "0.0.0.0", "--port", "1970", "--config", "/config", "--client", "/app/client"]
