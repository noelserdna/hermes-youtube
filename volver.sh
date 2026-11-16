#!/usr/bin/env bash
# Vuelve a una instalación anterior de hermes-youtube sin tocar datos: reapunta «actual», recopia el plugin al perfil
# principal y reinicia el gateway. Con --config <tar> restaura además cron/jobs.json y config.yaml de los perfiles
# desde una copia hecha antes de instalar.
#
#   bash volver.sh                    a la instalación anterior (instalacion.json → anterior)
#   bash volver.sh <carpeta>          a esa carpeta de ~/.hermes/hermes-youtube (p. ej. 0.1.0-ae0601e)
#   bash volver.sh … --config <tar>   y restaura cron/jobs.json y config.yaml de los perfiles desde el tar
#   bash volver.sh … --sin-reinicio   no reinicia el gateway (pruebas)
set -euo pipefail
HH="$HOME/.hermes"; HYT="${HERMES_YT_HOME:-$HH/hermes-youtube}"; HERMES="${HERMES_BIN:-hermes}"
DESTINO=""; TAR=""; REINICIO=true
while [ $# -gt 0 ]; do case $1 in
  --config) TAR=$2; shift 2 ;; --sin-reinicio) REINICIO=false; shift ;;
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;; *) DESTINO=$1; shift ;; esac; done
if [ -z "$DESTINO" ]; then DESTINO=$(jq -r '.anterior // ""' "$HYT/instalacion.json" 2>/dev/null); fi
[ -n "$DESTINO" ] || { echo "No sé a qué versión volver: pasa la carpeta (ls $HYT)" >&2; exit 2; }
case $DESTINO in /*) ;; *) DESTINO="$HYT/$DESTINO" ;; esac
[ -f "$DESTINO/plugin/hermes-youtube/plugin.yaml" ] || { echo "$DESTINO no es una instalación de hermes-youtube" >&2; exit 2; }
ACTUAL=$(readlink "$HYT/actual" 2>/dev/null || true)
ln -sfn "$DESTINO" "$HYT/actual"
mkdir -p "$HH/plugins"; rm -rf "$HH/plugins/hermes-youtube"; cp -R "$DESTINO/plugin/hermes-youtube" "$HH/plugins/hermes-youtube"
ln -sfn "$HYT/actual/hyt" "$HOME/.local/bin/hyt"
jq --arg c "$DESTINO" --arg a "$ACTUAL" '.carpeta = $c | .anterior = $a' "$HYT/instalacion.json" > "$HYT/instalacion.json.tmp" \
  && mv "$HYT/instalacion.json.tmp" "$HYT/instalacion.json"
if [ -n "$TAR" ]; then
  (cd "$HOME" && tar xzf "$TAR" --wildcards '.hermes/profiles/*/cron/jobs.json' '.hermes/profiles/*/config.yaml' \
     '.hermes/config.yaml' 2>/dev/null) || echo "AVISO: no pude restaurar todo desde $TAR"
  echo "Restaurados cron/jobs.json y config.yaml desde $TAR"
fi
echo "hermes-youtube vuelve a $DESTINO (antes: ${ACTUAL:-?})"
if $REINICIO; then
  setsid bash -c 'sleep 3; sudo -n systemctl restart hermes-gateway hermes-dashboard' >/dev/null 2>&1 < /dev/null &
  echo "Reiniciando el gateway en 3 s"
fi
