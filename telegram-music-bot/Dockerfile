# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="your-name"
LABEL description="Telegram Music Bot with Spotify + YouTube streaming"

# FFmpeg is required for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create directories that the bot writes to at runtime
RUN mkdir -p logs /tmp/musicbot

# Non-root user for security
RUN useradd --create-home --shell /bin/bash botuser \
    && chown -R botuser:botuser /app /tmp/musicbot
USER botuser

# Health check — just verifies Python can import the config
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "from config.settings import Settings; Settings()" || exit 1

CMD ["python", "main.py"]
