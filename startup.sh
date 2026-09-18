#!/bin/bash
# Azure App Service の「スタートアップ コマンド」に  bash startup.sh  と設定する。
# 1) 保存先フォルダを作る  2) DB を最新にする  3) Web サーバーを起動する
set -e
export DATA_DIR="${DATA_DIR:-/home/data}"
mkdir -p "$DATA_DIR"
python -m alembic upgrade head
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WEB_CONCURRENCY:-2}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --access-logfile - --error-logfile -
