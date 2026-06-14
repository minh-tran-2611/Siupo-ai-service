# ---- builder: cài dependencies vào virtualenv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build-essential cho các package cần compile (grpcio, libsql-client...)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---- runtime: image gọn, chỉ copy venv ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# User không phải root
RUN useradd -m -u 1000 appuser

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Thư mục runtime (ephemeral trên Cloud Run — xem ghi chú DEPLOY-GCP.md)
RUN mkdir -p logs data/uploads && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Cloud Run cấp biến $PORT (mặc định 8080). KHÔNG dùng --reload trên production.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
