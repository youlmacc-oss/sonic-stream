FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        unzip \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && rm -rf /var/lib/apt/lists/*

ARG RENDER_GIT_COMMIT=unknown
ENV DENO_INSTALL=/usr/local \
    PATH="/usr/local/bin:${PATH}" \
    GIT_COMMIT=${RENDER_GIT_COMMIT}

COPY backend/requirements.txt .

# stable = requirements pin. nightly = verified local track 2026.08.30.232658
ARG YTDLP_TRACK=stable
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$YTDLP_TRACK" = "nightly" ]; then \
        pip install --no-cache-dir --upgrade --pre "yt-dlp[default]"; \
    fi

COPY backend/ .

EXPOSE 8000

# Single process: JobStore and limiter are in-memory and not shared.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
