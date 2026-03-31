# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /app/.local
ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app/.local/lib/python3.11/site-packages:$PYTHONPATH

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.sh

# Non-root user: data dirs and full /app tree (including /app/.local) owned by appuser
RUN useradd -r -s /bin/false appuser && \
    mkdir -p /app/uploads /app/processed && \
    chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Default command
CMD ["bash", "scripts/start.sh"]
