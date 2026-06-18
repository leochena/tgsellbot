#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${MODEL_LAB_APP_DIR:-/opt/tgsellbot}"
WORKER_USER="${MODEL_LAB_WORKER_USER:-tgsellbot-worker}"
PYTHON_BIN="${MODEL_LAB_WORKER_PYTHON:-$APP_DIR/.venv/bin/python}"
WORKER_SCRIPT="${MODEL_LAB_WORKER_SCRIPT:-$APP_DIR/scripts/platform_worker.py}"
WORKER_HOME="${MODEL_LAB_WORKER_HOME:-/nonexistent}"
SAFE_PATH="${MODEL_LAB_WORKER_PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
SUDO_BIN="${MODEL_LAB_SUDO:-/usr/bin/sudo}"

if [ "$(id -un)" != "$WORKER_USER" ]; then
  exec "$SUDO_BIN" -n -u "$WORKER_USER" -- "$0" "$@"
fi

cd "$APP_DIR"
exec /usr/bin/env -i \
  PATH="$SAFE_PATH" \
  HOME="$WORKER_HOME" \
  PYTHONPATH="$APP_DIR" \
  "$PYTHON_BIN" "$WORKER_SCRIPT" "$@"
