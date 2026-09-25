#!/usr/bin/env bash
# Сборка и перезапуск контейнера API на сервере. Запускать из папки backend.
set -euo pipefail
docker build -t kixbox-pulse-api .
docker rm -f kixbox-pulse-api 2>/dev/null || true
docker run -d --name kixbox-pulse-api --restart unless-stopped \
  --network host --env-file .env kixbox-pulse-api
sleep 3
curl -s http://127.0.0.1:8095/api/v1/health && echo
