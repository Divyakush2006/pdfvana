# syntax=docker/dockerfile:1.7
# ---------- 1. Processing engine + API ----------
FROM python:3.12-slim-bookworm AS engine
ARG TARGETARCH=amd64
ARG PANDOC_VERSION=3.6.4
# SHA-256 of the official release archives — the build fails if a download was tampered with.
ARG PANDOC_SHA256_amd64=5def6e1ff535e397becce292ee97767a947306150b9fb1488003b67ac3417c5e
ARG PANDOC_SHA256_arm64=ad5cf63fe0420388d9ec513f02d03e061477b786d11a328164dce8ad7387b8bd
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data/jobs STATIC_DIR=/app/static OMP_THREAD_LIMIT=1 \
    TMPDIR=/data/tmp XDG_CACHE_HOME=/tmp/.cache HOME=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends \
      ghostscript qpdf poppler-utils unpaper pngquant ffmpeg libcairo2 fonts-dejavu-core fonts-liberation \
      curl ca-certificates \
      tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-ben tesseract-ocr-tam \
      tesseract-ocr-tel tesseract-ocr-mar tesseract-ocr-guj tesseract-ocr-kan tesseract-ocr-mal tesseract-ocr-pan \
      tesseract-ocr-urd tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-spa tesseract-ocr-por tesseract-ocr-ita \
      tesseract-ocr-nld tesseract-ocr-rus tesseract-ocr-ara tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-kor \
      tesseract-ocr-tur tesseract-ocr-pol tesseract-ocr-ind tesseract-ocr-vie \
 && curl -fsSL -o /tmp/pandoc.tgz "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-linux-${TARGETARCH}.tar.gz" \
 && if [ "$TARGETARCH" = "arm64" ]; then SUM="$PANDOC_SHA256_arm64"; else SUM="$PANDOC_SHA256_amd64"; fi \
 && echo "$SUM  /tmp/pandoc.tgz" | sha256sum -c - \
 && tar -xzf /tmp/pandoc.tgz -C /usr/local --strip-components=1 && rm /tmp/pandoc.tgz \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
# No package manager or build tools at runtime: smaller image, smaller attack surface.
RUN pip install --upgrade pip && pip install -r requirements.txt \
 && pip uninstall -y setuptools wheel && python -m pip uninstall -y pip
COPY backend/app ./app
RUN useradd --no-create-home --shell /usr/sbin/nologin --uid 10001 appuser \
 && mkdir -p /data/jobs /data/tmp && chown -R appuser /data && chmod -R go-w /app
USER appuser
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["sh", "-c", "mkdir -p /data/jobs /data/tmp && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --timeout-keep-alive 15 --limit-concurrency 1000 --backlog 2048 --no-server-header --h11-max-incomplete-event-size 65536"]

# ---------- 2. Web app build ----------
FROM node:26-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 3. Test runner (CI) ----------
FROM engine AS test
USER root
RUN python -m ensurepip && python -m pip install --no-cache-dir "pytest>=8"
COPY tests /tests
USER appuser
ENTRYPOINT ["python", "-m", "pytest", "-q", "/tests"]

# ---------- 4. Production image ----------
FROM engine AS app
LABEL org.opencontainers.image.title="PDFVana" \
      org.opencontainers.image.description="Free, open-source PDF tools and universal file converter" \
      org.opencontainers.image.source="https://github.com/divyakush2006/pdfvana" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=web --chown=appuser /web/dist /app/static
