#!/usr/bin/env bash
# Lanza tests/plugin_telegram.py con un Python de Hermes que tenga python-telegram-bot.
PY=${HERMES_PY:-}
if [ -z "$PY" ]; then
  for p in "$HOME"/.hermes/installs/*/environments/*/venv/bin/python "$HOME"/.hermes/hermes-agent/venv/bin/python; do
    [ -x "$p" ] && "$p" -c "import telegram" 2>/dev/null && { PY=$p; break; }
  done
fi
[ -n "$PY" ] || { echo "ok   (se salta: no hay un Python de Hermes con python-telegram-bot)"; exit 0; }
exec "$PY" "$(dirname "$0")/plugin_telegram.py"
