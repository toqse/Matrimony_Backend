#!/bin/bash
# Wait until Redis answers PING (REDIS_URL). An open TCP port does not mean
# Redis is usable — use the Redis protocol with bounded socket timeouts.
set -e
SECS="${WAIT_FOR_REDIS:-90}"
RURL="${REDIS_URL:-redis://localhost:6379/0}"
CONNECT_TIMEOUT="${REDIS_SOCKET_CONNECT_TIMEOUT:-2}"
SOCKET_TIMEOUT="${REDIS_SOCKET_TIMEOUT:-2}"
echo "Waiting for Redis (PING) — ${RURL} (max ${SECS}s)..."
export _RURL="$RURL"
export _REDIS_SOCKET_CONNECT_TIMEOUT="$CONNECT_TIMEOUT"
export _REDIS_SOCKET_TIMEOUT="$SOCKET_TIMEOUT"
for i in $(seq 1 "$SECS"); do
  if python -c "
import os, urllib.parse
import redis
u = urllib.parse.urlparse(os.environ.get('_RURL') or 'redis://localhost:6379/0')
h = u.hostname or 'localhost'
p = int(u.port or 6379)
password = u.password
db = 0
if u.path and u.path.strip('/'):
    try:
        db = int(u.path.strip('/').split('/')[0])
    except ValueError:
        db = 0
connect_timeout = float(os.environ.get('_REDIS_SOCKET_CONNECT_TIMEOUT') or 2)
socket_timeout = float(os.environ.get('_REDIS_SOCKET_TIMEOUT') or 2)
r = redis.Redis(
    host=h,
    port=p,
    password=password,
    db=db,
    socket_connect_timeout=connect_timeout,
    socket_timeout=socket_timeout,
)
r.ping()
" 2>/dev/null; then
    echo "Redis is up."
    exit 0
  fi
  if [ $((i % 5)) -eq 0 ] || [ "$i" -le 3 ]; then
    echo "  not ready yet (${i}/${SECS})..."
  fi
  sleep 1
done
echo "Timeout waiting for Redis (check REDIS_URL and that Redis answers PING)." >&2
exit 1
