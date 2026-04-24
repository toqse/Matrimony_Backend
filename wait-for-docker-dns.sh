#!/bin/bash
# Wait until Docker's embedded DNS resolves DB and Redis so clients don't fail with
# "could not translate host name" / "Name or service not known" (common race on WSL2).
set -e
DB_HOST="${DATABASE_HOST:-postgres}"
SECS="${WAIT_FOR_DOCKER_DNS:-90}"
echo "Waiting for Docker DNS: ${DB_HOST}, redis (max ${SECS}s)..."
for i in $(seq 1 "$SECS"); do
  if python -c "
import os, socket
for name in (os.environ.get('DATABASE_HOST') or 'postgres', 'redis'):
    socket.gethostbyname(name)
" 2>/dev/null; then
    echo "DNS ready for ${DB_HOST} and redis."
    exit 0
  fi
  if [ $((i % 5)) -eq 0 ] || [ "$i" -le 3 ]; then
    echo "  resolvers not ready yet (${i}/${SECS})..."
  fi
  sleep 1
done
echo "Timeout: could not resolve ${DB_HOST} or redis. Try: docker compose down && docker compose up --build" >&2
exit 1
