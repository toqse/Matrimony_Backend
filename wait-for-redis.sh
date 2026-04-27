#!/bin/bash
# Wait until Redis accepts TCP (REDIS_URL). Uses connection check instead of
# service-name DNS, which is unreliable on some Docker Desktop + WSL2 setups.
set -e
SECS="${WAIT_FOR_REDIS:-90}"
RURL="${REDIS_URL:-redis://localhost:6379/0}"
echo "Waiting for Redis (TCP) — ${RURL} (max ${SECS}s)..."
export _RURL="$RURL"
for i in $(seq 1 "$SECS"); do
  if python -c "
import os, socket, urllib.parse
u = urllib.parse.urlparse(os.environ.get('_RURL') or 'redis://localhost:6379/0')
h, p = u.hostname, u.port
h = h or 'localhost'
p = int(p or 6379)
s = socket.create_connection((h, p), timeout=2)
s.close()
" 2>/dev/null; then
    echo "Redis is up."
    exit 0
  fi
  if [ $((i % 5)) -eq 0 ] || [ "$i" -le 3 ]; then
    echo "  not ready yet (${i}/${SECS})..."
  fi
  sleep 1
done
echo "Timeout waiting for Redis (check port mapping and REDIS_URL)." >&2
exit 1
