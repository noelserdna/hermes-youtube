#!/usr/bin/env bash
# Ejecutor CLAUDE CODE con supervisor (copiado y adaptado de hermes-sdd). Lanza UNA etapa con `claude -p` y la vigila:
#   · candado por encargo: nunca dos etapas a la vez en el mismo encargo (otra viva → outcome "busy")
#   · Claude en su propio grupo de procesos; si este supervisor o su padre desaparecen, el grupo se mata
#   · entorno limpio: Claude no hereda los tokens del bot ni las claves de Hermes (solo su propia sesión, si se pasa
#     CLAUDE_CODE_OAUTH_TOKEN)
#   · cuota agotada o Claude sin sesión → outcome "scheduled" (no es un fallo de la etapa)
#   · el estado de hermes-youtube (puertas, decisiones, configuración, secretos) no se puede editar desde la etapa
#
#   executors/claude.sh <carpeta> <nombre> <prompt> [modelo] [perfil] [skill]
#
# Última línea de stdout: JSON {outcome: done|failed|scheduled|busy, reason, run, session_id, cost_usd, minutes, reset_at}
set -uo pipefail
DIR=$(cd "$1" && pwd); NOMBRE=$2; PROMPT=$3; MODELO=${4:-}
H="${HERMES_YT_HOME:-$HOME/.hermes/hermes-youtube}"
RUN="$(date +%Y%m%d-%H%M%S)-$NOMBRE"
EST="$DIR/.estado"; LOCK="$EST/lock"; mkdir -p "$EST/runs"
OUT="$EST/runs/$RUN.json"; ERR="$EST/runs/$RUN.err"

salir() {  # salir <outcome> <reason> [extra-json]
  local x=${3:-}; [ -n "$x" ] || x='{}'
  if [ "$1" = scheduled ]; then   # cuota agotada: todo espera hasta el reinicio (o 1 h si no se sabe)
    local r; r=$(echo "$x" | jq -r '.reset_at // empty'); [ -n "$r" ] || r=$(( $(date +%s) + 3600 ))
    mkdir -p "$H"
    jq -n --arg r "$r" --arg m "$(echo "$x" | jq -r '.motivo // "cuota"')" '{reset_at: ($r|tonumber), motivo: $m}' > "$H/cuota.json"
  fi
  jq -nc --arg o "$1" --arg r "$2" --arg run "$RUN" --argjson x "$x" '{outcome:$o, reason:$r, run:$run} + $x'
  exit 0
}

if ! mkdir "$LOCK" 2>/dev/null; then
  otro=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$otro" ] && kill -0 "$otro" 2>/dev/null; then salir busy "ya hay una etapa viva en este encargo (pid $otro)"; fi
  rm -rf "$LOCK"; mkdir "$LOCK"   # candado huérfano
fi
echo $$ > "$LOCK/pid"; echo "$RUN" > "$LOCK/run"
CPID=""
limpiar() { [ -n "$CPID" ] && kill -TERM -- "-$CPID" 2>/dev/null; [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCK"; }
trap limpiar EXIT
trap 'limpiar; exit 143' TERM INT HUP

BIN=$(command -v "${CLAUDE_BIN:-claude}" || true)
[ -n "$BIN" ] || for b in "$HOME/.npm-global/bin/claude" "$HOME/.local/bin/claude"; do [ -x "$b" ] && BIN=$b && break; done
[ -n "$BIN" ] || salir failed "no encuentro el ejecutable de Claude Code"
PATH_LIMPIO="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
for b in "$BIN" "$(command -v node || true)"; do
  [ -n "$b" ] || continue; d=$(dirname "$b")
  case ":$PATH_LIMPIO:" in *":$d:"*) ;; *) PATH_LIMPIO="$d:$PATH_LIMPIO";; esac
done
# La etapa escribe en su carpeta; lo que decide o configura el sistema, las fuentes y la memoria del canal no se tocan
# nunca desde aquí. Sin herramientas de red: una etapa trabaja solo con el material propio del canal.
AJUSTES=$(jq -nc --arg h "$H" '{permissions: {deny: [
  ("Edit(" + $h + "/puertas/**)"), ("Edit(" + $h + "/decisiones/**)"), ("Edit(" + $h + "/*.json)"),
  ("Edit(" + $h + "/secretos.env)"), ("Edit(" + $h + "/canales/*/canal.json)"), ("Edit(" + $h + "/canales/*/secretos.env)"),
  ("Edit(" + $h + "/canales/*/wiki/**)"), ("Edit(" + $h + "/canales/*/fuentes/**)"), ("Edit(" + $h + "/canales/*/inventario.json)"),
  ("Edit(" + $h + "/canales/*/*.jsonl)"), ("Edit(" + $h + "/actual/**)"), "Edit(~/.hermes/config.yaml)", "Edit(~/.hermes/.env)",
  "Read(~/.hermes/.env)", ("Read(" + $h + "/secretos.env)"), ("Read(" + $h + "/canales/*/secretos.env)")]}}')
TOOLS="Read,Edit,Write,Glob,Grep,Bash(ls:*),Bash(cat:*),Bash(grep:*),Bash(wc:*),Bash(head:*),Bash(tail:*),Bash(jq:*)"
[ -n "${HYT_CLAUDE_TOOLS_EXTRA:-}" ] && TOOLS="$TOOLS,$HYT_CLAUDE_TOOLS_EXTRA"
PASAR=(); for v in $(compgen -e | grep '^HYT_PASAR_' || true); do PASAR+=("${v#HYT_PASAR_}=${!v}"); done
ARGS=(-p "$PROMPT" --output-format json --settings "$AJUSTES" --permission-mode acceptEdits --allowedTools "$TOOLS"
      --max-turns "${MAX_TURNS:-80}")
[ -n "$MODELO" ] && ARGS+=(--model "$MODELO")
IFS=: read -r -a DIRS <<< "${HYT_CLAUDE_DIRS:-}"; for d in ${DIRS[@]+"${DIRS[@]}"}; do [ -n "$d" ] && ARGS+=(--add-dir "$d"); done
cd "$DIR"
env -i HOME="$HOME" USER="${USER:-$(id -un)}" LOGNAME="${LOGNAME:-${USER:-}}" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-es_ES.UTF-8}" \
  PATH="$PATH_LIMPIO" TERM=dumb DISABLE_AUTOUPDATER=1 HYT_RUN="$RUN" ${PASAR[@]+"${PASAR[@]}"} \
  ${CLAUDE_CODE_OAUTH_TOKEN:+CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN"} \
  perl -e 'setpgrp(0,0); exec @ARGV' "$BIN" "${ARGS[@]}" > "$OUT" 2> "$ERR" &
CPID=$!
echo "$CPID" > "$LOCK/claude"
command -v caffeinate >/dev/null && caffeinate -i -s -w "$CPID" &

INICIO=$(date +%s)
while kill -0 "$CPID" 2>/dev/null; do
  if [ "$(ps -o ppid= -p $$ | tr -d ' ')" = 1 ]; then echo "padre desaparecido: se detiene la etapa" >> "$ERR"; limpiar; exit 1; fi
  sleep 5 & wait $!
done
wait "$CPID"; RC=$?; CPID=""
MIN=$(( ($(date +%s) - INICIO) / 60 ))

SESION='failed to authenticate|authentication_error|invalid api key|please run /login|oauth token (has )?expired|not logged in'
sin_sesion() { salir scheduled "Claude sin sesión: hay que volver a entrar" "$(echo "$1" | jq -c --arg r "$(( $(date +%s) + 900 ))" '. + {reset_at:($r|tonumber), motivo:"sesion"}')"; }
if ! jq -e . "$OUT" >/dev/null 2>&1; then
  if grep -qiE "usage limit|rate limit|limit reached|resets? at" "$ERR" "$OUT" 2>/dev/null; then
    RESET=$(grep -oE '\|[0-9]{10}' "$OUT" "$ERR" 2>/dev/null | head -1 | tr -d '|' || true)
    salir scheduled "cuota de Claude agotada" "$(jq -nc --arg r "${RESET:-}" 'if $r == "" then {} else {reset_at:($r|tonumber)} end')"
  fi
  grep -qiE "$SESION" "$ERR" "$OUT" 2>/dev/null && sin_sesion '{}'
  salir failed "Claude Code no devolvió JSON (rc=$RC): $(tail -c 300 "$ERR" | tr '\n' ' ')"
fi
TEXTO=$(jq -r '.result // ""' "$OUT")
EXTRA=$(jq -c --argjson m "$MIN" '{session_id, cost_usd: .total_cost_usd, turns: .num_turns, minutes: $m,
  resumen: ((.result // "") | .[-800:])}' "$OUT")
if [ "$(jq -r .is_error "$OUT")" = true ] || [ "$RC" -ne 0 ]; then
  if echo "$TEXTO" | grep -qiE "usage limit|rate limit|limit reached"; then
    RESET=$(echo "$TEXTO" | grep -oE '\|[0-9]{10}' | head -1 | tr -d '|' || true)
    salir scheduled "cuota de Claude agotada" "$(echo "$EXTRA" | jq -c --arg r "${RESET:-}" 'if $r == "" then . else . + {reset_at:($r|tonumber)} end')"
  fi
  echo "$TEXTO" | grep -qiE "$SESION" && sin_sesion "$EXTRA"
  salir failed "la etapa terminó con error: $(echo "$TEXTO" | tail -c 300 | tr '\n' ' ')" "$EXTRA"
fi
salir done "ok" "$EXTRA"
