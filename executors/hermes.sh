#!/usr/bin/env bash
# Ejecutor HERMES: la etapa la hace un perfil de rol de Hermes (yt-investigador, yt-guionista…) con su skill y el
# modelo que le toca a esa etapa (hyt_modelos.py). Mismo contrato que claude.sh.
#
#   executors/hermes.sh <carpeta> <nombre> <prompt> <modelo|""> <perfil> <skill>
#
# Última línea de stdout: JSON {outcome: done|failed|busy, reason, run, session_id, cost_usd, minutes}
set -uo pipefail
DIR=$(cd "$1" && pwd); NOMBRE=$2; PROMPT=$3; MODELO=${4:-}; PERFIL=${5:?perfil}; SKILL=${6:-}
RUN="$(date +%Y%m%d-%H%M%S)-$NOMBRE"
EST="$DIR/.estado"; LOCK="$EST/lock"; mkdir -p "$EST/runs"
OUT="$EST/runs/$RUN.txt"; ERR="$EST/runs/$RUN.err"; USO="$EST/runs/$RUN.json"
salir() { local x=${3:-}; [ -n "$x" ] || x='{}'
  jq -nc --arg o "$1" --arg r "$2" --arg run "$RUN" --argjson x "$x" '{outcome:$o, reason:$r, run:$run} + $x'; exit 0; }

if ! mkdir "$LOCK" 2>/dev/null; then
  otro=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  [ -n "$otro" ] && kill -0 "$otro" 2>/dev/null && salir busy "ya hay una etapa viva en este encargo (pid $otro)"
  rm -rf "$LOCK"; mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"; trap 'rm -rf "$LOCK"' EXIT

ARGS=(-p "$PERFIL" --accept-hooks --usage-file "$USO" -z "$PROMPT")
[ -n "$SKILL" ] && ARGS+=(-s "$SKILL")
[ -n "$MODELO" ] && ARGS+=(-m "$MODELO")
INICIO=$(date +%s)
cd "$DIR"
"${HERMES_BIN:-hermes}" "${ARGS[@]}" > "$OUT" 2> "$ERR"; RC=$?
MIN=$(( ($(date +%s) - INICIO) / 60 ))
COSTE=$(jq -r '.estimated_cost_usd // .cost_usd // .total_cost_usd // 0' "$USO" 2>/dev/null || echo 0)
RES=$(tail -c 800 "$OUT" | tr '\n' ' ')
EXTRA=$(jq -nc --arg c "$COSTE" --argjson m "$MIN" --arg r "$RES" '{session_id:"hermes", cost_usd:($c|tonumber? // 0), minutes:$m, resumen:$r}')
if [ "$RC" != 0 ]; then
  if grep -qiE "usage limit|rate limit|quota" "$ERR" "$OUT" 2>/dev/null; then
    salir scheduled "cuota del proveedor agotada" "$(echo "$EXTRA" | jq -c --arg r "$(( $(date +%s) + 3600 ))" '. + {reset_at:($r|tonumber)}')"
  fi
  salir failed "hermes salió con $RC: $(tail -c 300 "$ERR" | tr '\n' ' ')" "$EXTRA"
fi
salir done "ok" "$EXTRA"
