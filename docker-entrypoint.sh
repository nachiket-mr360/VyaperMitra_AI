#!/bin/sh
set -e
mkdir -p /var/data
if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser /var/data
  exec gosu appuser "$0" "$@"
fi
cd /app/backend
# One worker: SQLite is not safe with multiple Gunicorn processes.
exec gunicorn \
  --bind "${HOST:-0.0.0.0}:${PORT:-5000}" \
  --workers 1 \
  --threads 8 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  app:app
