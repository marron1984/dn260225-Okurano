#!/bin/bash
# 大嵓埜 管理画面サーバー自動起動スクリプト
# SessionStartフックから呼ばれ、サーバーをバックグラウンドで起動する

PORT=8080
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$PROJECT_DIR/generator/.server.pid"
LOG_FILE="$PROJECT_DIR/generator/.server.log"

# 既に起動中なら何もしない
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[大嵓埜] 管理画面は既に起動中です (PID: $OLD_PID, http://localhost:$PORT/)"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

# ポートが使用中か確認
if command -v ss &>/dev/null && ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
  echo "[大嵓埜] ポート $PORT は既に使用中です"
  exit 0
fi

# サーバーをバックグラウンドで起動
cd "$PROJECT_DIR"
nohup python3 generator/server.py --port "$PORT" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

sleep 1

if kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "[大嵓埜] 管理画面を起動しました → http://localhost:$PORT/"
else
  echo "[大嵓埜] サーバー起動に失敗しました。ログ: $LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi
