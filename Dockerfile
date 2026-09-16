FROM python:3.11-slim
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DENO_INSTALL=/usr/local \
    PATH="/usr/local/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && deno --version \
    && node --version

ARG RENDER_GIT_COMMIT=unknown
ENV GIT_COMMIT=${RENDER_GIT_COMMIT}

# Context may be repo root or backend/.
COPY . /tmp/src
RUN set -eu; \
    if [ -f /tmp/src/backend/requirements.txt ]; then SRC=/tmp/src/backend; \
    elif [ -f /tmp/src/requirements.txt ]; then SRC=/tmp/src; \
    else echo "requirements.txt not found in build context" >&2; ls -la /tmp/src >&2; exit 1; \
    fi; \
    cp -a "$SRC"/. /app/; \
    pip install --no-cache-dir -r /app/requirements.txt

# Pin the verified cookie-free combination. Do not float to latest nightly.
ARG YTDLP_PIN=2026.8.30.232658
RUN pip install --no-cache-dir --pre "yt-dlp[default]==${YTDLP_PIN}" \
    || pip install --no-cache-dir --upgrade "yt-dlp[default]"

EXPOSE 8000

# Single process: JobStore and limiter are in-memory and not shared.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
