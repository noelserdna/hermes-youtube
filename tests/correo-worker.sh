#!/usr/bin/env bash
# Worker del correo (con KV y envío falsos)
command -v node >/dev/null || { echo "ok   (sin node: se salta)"; exit 0; }
D="$(dirname "$0")/../correo"
[ -d "$D/node_modules/postal-mime" ] || (cd "$D" && npm install --silent --no-audit --no-fund >/dev/null 2>&1)
[ -d "$D/node_modules/postal-mime" ] || { echo "ok   (sin postal-mime ni red: se salta)"; exit 0; }
exec node "$(dirname "$0")/correo.mjs"
