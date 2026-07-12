# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    PORT=5000

WORKDIR $APP_HOME

# Install system dependencies required for psycopg2-binary and cryptography.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies.
COPY requirements.txt pyproject.toml .flake8 ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Run migrations and start the production server.
# For a more robust deployment, run migrations as an init container/job before
# starting the web containers.
EXPOSE $PORT
CMD ["sh", "-c", "alembic upgrade head && gunicorn -w 2 -k sync -b 0.0.0.0:$PORT --access-logfile - --error-logfile - app:app"]
