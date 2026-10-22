FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed by psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project source
COPY . .

# Collect static files (harmless to do at build time; override for dev)
# RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Default command — docker-compose overrides this per service
CMD ["gunicorn", "payledger.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2"]
