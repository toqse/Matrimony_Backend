#!/bin/bash
set -e

echo "Waiting for database (retrying migrate until ready)..."
until python manage.py migrate --noinput; do
  echo "Database not ready, retrying in 2s..."
  sleep 2
done
echo "Migrations done."

echo "Starting: $*"
exec "$@"
