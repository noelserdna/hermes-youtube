#!/usr/bin/env bash
# Ejecuta una pipeline en esta máquina, etapa a etapa, con Claude Code y sin Hermes: para juzgar la calidad de lo que
# sale antes de instalar nada. El estado vive en privado/.hyt (fuera de git). No hay kanban ni puertas por correo:
# las etapas corren en fila y la decisión se toma con «decidir».
#
#   local.sh canal <slug> <carpeta-con-canal.json>     da de alta el canal y le pone su configuración y su voz
#   local.sh fuentes <slug> <zip|carpeta> <colección> <tipo>
#   local.sh correr <slug> <pipeline> [clave=valor …]  lanza y ejecuta todas las etapas hasta la puerta
#   local.sh seguir <slug> <encargo> [etapa]           continúa un encargo (desde esa etapa o desde la primera sin hacer)
#   local.sh decidir <puerta> <acepto|cambios|rechazo|algunas> [texto]
#   local.sh dato <puerta> <dato> <verificado|corregido|eliminado> [valor]
#   local.sh estado <slug>
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export HERMES_YT_HOME="${HERMES_YT_HOME:-$ROOT/privado/.hyt}"
export HERMES_BIN="$ROOT/tests/dobles/hermes" FALSO_LLAMADAS="$HERMES_YT_HOME/.local/llamadas" FALSO_TABLEROS="$HERMES_YT_HOME/.local/tableros"
export HERMES_YT_DESHACER_S=0 HYT_SIN_SCOPE=1 HYT_QUIEN="${USER:-local}"
mkdir -p "$HERMES_YT_HOME/.local"
P="$ROOT/plugin/hermes-youtube"; hyt() { python3 "$P/hyt_cli.py" "$@"; }
[ -f "$HERMES_YT_HOME/aprobadores.json" ] || printf '{"%s": {"nombre": "%s", "medios": {"local": "%s"}, "canales": ["*"]}}\n' "$(id -un)" "$(id -un)" "$(id -un)" > "$HERMES_YT_HOME/aprobadores.json"

etapas() {  # etapas <slug> <encargo> [desde]
  local slug=$1 eid=$2 desde=${3:-} d="$HERMES_YT_HOME/canales/$1/encargos/$2" ir=0
  [ -z "$desde" ] && ir=1
  for e in $(jq -r '.etapas[].id' "$d/encargo.json"); do
    [ "$e" = "$desde" ] && ir=1
    [ "$ir" = 1 ] || continue
    if [ -z "$desde" ] && jq -e --arg e "$e" 'select(.encargo == "'"$eid"'" and .etapa == $e and .resultado == "done")' "$HERMES_YT_HOME/canales/$slug/etapas.jsonl" >/dev/null 2>&1; then continue; fi
    printf '▶ %-12s ' "$e"; t0=$(date +%s)
    r=$(bash "$ROOT/etapa.sh" "$slug" "$eid" "$e" 2>&1 | tail -1)
    o=$(echo "$r" | jq -r '.outcome // "?"' 2>/dev/null || echo "?")
    printf '%s · %ss · %s $\n' "$o" "$(( $(date +%s) - t0 ))" "$(echo "$r" | jq -r '.cost_usd // 0' 2>/dev/null)"
    echo "$r" | jq -r '"   " + ((.resumen // .reason // "") | tostring | gsub("\n"; " ") | .[-300:])' 2>/dev/null
    if [ "$o" != done ]; then echo "✋ Parado en «$e». Para seguir: local.sh seguir $slug $eid $e"; return 1; fi
    g=$(echo "$r" | jq -r '.puerta // empty' 2>/dev/null); [ -n "$g" ] && echo "🚪 Puerta abierta: $g  (local.sh decidir $g acepto|cambios|rechazo [texto])"
  done
  echo "📁 $d"
}

case "${1:-}" in
  canal)
    slug=$2; src=$3
    [ -f "$HERMES_YT_HOME/canales/$slug/canal.json" ] || hyt alta "$slug" "$(jq -r .nombre "$src/canal.json")" "$(jq -r .presentador "$src/canal.json")"
    c="$HERMES_YT_HOME/canales/$slug"
    # en local todas las etapas van con Claude Code
    jq --slurpfile p <(cat "$ROOT"/pipelines/*.json | jq -s '[.[].etapas[].id] | unique | map({(.): "claude"}) | add') '. + {ejecutores: $p[0]}' "$src/canal.json" > "$c/canal.json.nuevo"
    python3 - "$P" "$c/canal.json.nuevo" <<'PY' || exit 1
import json, sys
sys.path.insert(0, sys.argv[1]); import hyt_canales as C
e = C.validar(json.load(open(sys.argv[2])))
if e: print("La configuración no es válida:\n- " + "\n- ".join(e)); sys.exit(1)
PY
    mv "$c/canal.json.nuevo" "$c/canal.json"
    [ -f "$src/voz.md" ] && mkdir -p "$c/wiki/concepts" && cp "$src/voz.md" "$c/wiki/concepts/voz.md"
    hyt estado "$slug" ;;
  fuentes) python3 "$P/hyt_fuentes.py" cargar "$2" "$3" --coleccion "$4" --tipo "$5" && python3 "$P/hyt_fuentes.py" lista "$2" ;;
  correr)
    slug=$2; pid=$3; shift 3; args=(); for kv in "$@"; do args+=(--param "$kv"); done
    out=$(hyt lanzar "$slug" "$pid" ${args[@]+"${args[@]}"}) || { echo "$out"; exit 1; }
    echo "$out"; eid=$(echo "$out" | grep -oE '\([a-z0-9-]+\)' | head -1 | tr -d '()')
    [ -n "$eid" ] && etapas "$slug" "$eid" ;;
  seguir) etapas "$2" "$3" "${4:-}" ;;
  decidir) python3 "$P/hyt_puertas.py" decidir-local "$2" "$3" "${4:-}" ;;
  dato) python3 "$P/hyt_puertas.py" dato-local "$2" "$3" "$4" "${5:-}" ;;
  estado) hyt estado "$2"; hyt puertas "$2" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
