FROM python:3.11-slim

# Security: run as non-root user
RUN groupadd -r dwrs && useradd -r -g dwrs dwrs

WORKDIR /app

# Install system dependencies for face recognition, geo libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libgdal-dev \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Remove dev/test files from production image
RUN rm -rf tests/ .env.example

RUN chown -R dwrs:dwrs /app
USER dwrs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "services.registration.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
