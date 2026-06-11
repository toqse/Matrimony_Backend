FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DJANGO_SETTINGS_MODULE=matrimony_backend.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev default-libmysqlclient-dev pkg-config \
    libraqm0 \
    libharfbuzz0b \
    libfribidi0 \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    fonts-smc fonts-noto-core \
    wget libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Swiss Ephemeris data files for pyswisseph (thalakkuri/jathakam astronomy).
# Resilient: if the download fails at build time, pyswisseph falls back to its
# built-in Moshier model, so the image still builds.
RUN mkdir -p /usr/share/ephe \
    && wget -q https://www.astro.com/ftp/swisseph/ephe/seas_18.se1 \
         -O /usr/share/ephe/seas_18.se1 \
    && wget -q https://www.astro.com/ftp/swisseph/ephe/semo_18.se1 \
         -O /usr/share/ephe/semo_18.se1 \
    && wget -q https://www.astro.com/ftp/swisseph/ephe/sepl_18.se1 \
         -O /usr/share/ephe/sepl_18.se1 \
    || echo "WARN: Swiss Ephemeris download failed; pyswisseph will use Moshier fallback."

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
