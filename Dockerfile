# syntax=docker/dockerfile:1.7

# ---- web UI ------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- app ---------------------------------------------------------------------
FROM python:3.13-slim-trixie

LABEL org.opencontainers.image.title="Printmich" \
      org.opencontainers.image.description="Scheduled photo prints from Immich to a Canon imagePROGRAF PRO-310 (or any IPP Everywhere printer)." \
      org.opencontainers.image.source="https://github.com/au12/Printmich" \
      org.opencontainers.image.licenses="MIT" \
      net.unraid.docker.icon="https://raw.githubusercontent.com/au12/Printmich/main/icon.png" \
      net.unraid.docker.webui="http://[IP]:[PORT:8080]/"

# libvips does the imaging (with HEIC/AVIF decoders for phone photos);
# the fonts are the caption typefaces offered in presets.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libvips42t64 libheif-plugin-libde265 libheif-plugin-aomdec \
      fonts-ebgaramond fonts-inter fonts-dejavu-core fontconfig \
      tini tzdata ca-certificates \
 && fc-cache -f \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/tmp/.cache \
    PRINTMICH_DATA=/config \
    PRINTMICH_STATIC=/app/static \
    PRINTMICH_PORT=8080 \
    PUID=99 \
    PGID=100 \
    TZ=Etc/UTC

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/printmich ./printmich
COPY --from=web /web/dist ./static
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 8080
VOLUME /config
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PRINTMICH_PORT','8080'), timeout=4)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "printmich.main"]
