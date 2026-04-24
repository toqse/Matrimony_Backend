#!/bin/bash
set -e
/wait-for-docker-dns.sh
exec celery "$@"
