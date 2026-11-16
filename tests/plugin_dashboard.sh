#!/usr/bin/env bash
# Lanza tests/plugin_dashboard.py con un Python de Hermes que tenga FastAPI (el del panel). Comprueba también el JS.
command -v node >/dev/null && { node --check "$(dirname "$0")/../plugin/hermes-youtube/dashboard/dist/index.js" && echo "ok   la pestaña (JS) es válida" || { echo "FAIL index.js"; exit 1; }; }
PY=${HERMES_PY:-}
if [ -z "$PY" ]; then
  for p in "$HOME"/.hermes/installs/*/environments/*/venv/bin/python "$HOME"/.hermes/hermes-agent/venv/bin/python; do
    [ -x "$p" ] && "$p" -c "import fastapi, httpx" 2>/dev/null && { PY=$p; break; }
  done
fi
[ -n "$PY" ] || { echo "ok   (se salta la API: no hay un Python de Hermes con FastAPI)"; exit 0; }
exec "$PY" "$(dirname "$0")/plugin_dashboard.py"
