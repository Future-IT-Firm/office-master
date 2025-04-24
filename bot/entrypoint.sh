#!/bin/sh
set -e
mkdir -p /data /shared

if [ "${WAIT_FOR_MASTER:-}" = "1" ]; then
  echo "⏳ waiting for /shared/all_data.txt …"
  while [ ! -f /shared/all_data.txt ]; do
    sleep 1
  done
  echo "found master list"
fi

exec python main.py
