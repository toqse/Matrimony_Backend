FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DJANGO_SETTINGS_MODULE=matrimony_backend.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    libraqm0 \
    libharfbuzz0b \
    libfribidi0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN python manage.py collectstatic --noinput 2>/dev/null || true

COPY entrypoint.sh /entrypoint.sh
COPY wait-for-redis.sh /wait-for-redis.sh
COPY celery-entrypoint.sh /celery-entrypoint.sh
# Strip CRLF (Windows) so script runs in Linux
RUN for f in /entrypoint.sh /wait-for-redis.sh /celery-entrypoint.sh; do \
  sed -i 's/\r$//' "$f" && chmod +x "$f"; \
done

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "matrimony_backend.asgi:application"]
