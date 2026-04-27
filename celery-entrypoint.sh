#!/bin/bash
set -e
/wait-for-redis.sh
exec celery "$@"
