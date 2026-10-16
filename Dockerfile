# Imagem do player (fork do Swing Music) para o homelab.
# Contexto de build: raiz deste repo + o repo do cliente clonado em ./client-src
#   git clone https://github.com/rodrigouxp/swingmusic-webclient client-src
#   docker build -t swingmusic-dev .

# ---------- 1. cliente web (fork) ----------
FROM node:22-slim AS client
WORKDIR /client
COPY client-src/package.json client-src/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY client-src/ ./
RUN yarn build --outDir /client-dist

# ---------- 2. servidor: compila as dependencias ----------
FROM python:3.11-slim AS server-build
ARG VERSION=2.0.9
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libev-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

# ---------- 3. imagem final ----------
FROM python:3.11-slim
LABEL org.opencontainers.image.title="swingmusic-dev" \
      org.opencontainers.image.source="https://github.com/rodrigouxp/swingmusic"
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libev4 libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*
COPY --from=server-build /install /usr/local
# O cliente fica FORA de /config: o ZimaOS monta uma pasta no /config e
# esconderia qualquer coisa que a imagem deixasse la.
COPY --from=client /client-dist /app/client

EXPOSE 1970/tcp
VOLUME /music
VOLUME /config
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:1970/')" || exit 1

ENTRYPOINT ["python", "-m", "swingmusic", "--host", "0.0.0.0", "--port", "1970", "--config", "/config", "--client", "/app/client"]
