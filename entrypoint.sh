#!/bin/bash
set -e

/wait-for-redis.sh

echo "Waiting for database (retrying migrate until ready)..."
until python manage.py migrate --noinput; do
  echo "Database not ready, retrying in 2s..."
  sleep 2
done
echo "Migrations done."

# Optional: create or reset Django /admin/ superuser (accounts.User).
# Set in .env — only for local/dev; remove or leave unset in production.
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "Ensuring Django admin superuser for ${DJANGO_SUPERUSER_EMAIL}..."
  python manage.py set_admin_password "$DJANGO_SUPERUSER_EMAIL" "$DJANGO_SUPERUSER_PASSWORD"
fi

echo "Starting: $*"
exec "$@"
