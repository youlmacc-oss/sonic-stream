FROM python:3.11-slim
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

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
    && deno --version

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

ARG YTDLP_TRACK=stable
RUN if [ "$YTDLP_TRACK" = "nightly" ]; then pip install --no-cache-dir --upgrade --pre "yt-dlp[default]"; fi

EXPOSE 8000

# Single process: JobStore and limiter are in-memory and not shared.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
