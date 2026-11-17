#!/usr/bin/env bash
# Instala (o actualiza) hermes-youtube en este Hermes. Idempotente: nunca borra perfiles, claves, canales ni datos.
#
#   bash instalar.sh [--coordinadora | --coordinadora-estricta] [--seco]
#
#   --coordinadora            el perfil principal (default) pasa a ser también la coordinadora: su carta en SOUL.md y
#                             prohibiciones duras (approvals.deny) solo para lo irreversible: decidir o firmar puertas,
#                             secretos y aprobadores. Conserva su terminal.
#   --coordinadora-estricta   además, el guardia (fail-closed) que la limita a la CLI hyt y a leer.
#
# Qué deja:
#   ~/.hermes/hermes-youtube/<versión> + enlace «actual», instalacion.json, aprobadores.json (si no existe)
#   el plugin hermes-youtube activado (Telegram, notario, sección de prompt) y la CLI hyt en ~/.local/bin
#   perfiles: yt-estacion (mueve tarjetas) y los de rol (yt-analista, yt-estratega, yt-espectador, yt-titulador,
#   yt-miniaturista, yt-investigador, yt-guionista, yt-verificador, yt-retencion, yt-doble, yt-editor-jefe), con sus
#   cartas y las skills del arnés
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
HH="$HOME/.hermes"; HYT="${HERMES_YT_HOME:-$HH/hermes-youtube}"
HERMES="${HERMES_BIN:-hermes}"
COORD=false; ESTRICTA=false; SECO=false
for a in "$@"; do case $a in --coordinadora) COORD=true ;; --coordinadora-estricta) COORD=true; ESTRICTA=true ;;
  --seco) SECO=true ;; *) sed -n '2,16p' "$0"; exit 2 ;; esac; done

falta=()
for c in jq rsync git python3; do command -v "$c" >/dev/null || falta+=("$c"); done
command -v "$HERMES" >/dev/null || [ -x "$HERMES" ] || falta+=(hermes)
[ ${#falta[@]} -eq 0 ] || { echo "Faltan: ${falta[*]}" >&2; exit 1; }
command -v claude >/dev/null || [ -x "$HOME/.npm-global/bin/claude" ] || echo "Nota: no hay Claude Code en esta máquina; solo hace falta si un canal pone el ejecutor «claude» en alguna etapa"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Hace falta python3 >= 3.9" >&2; exit 1; }

VERSION=$(sed -nE 's/^version: *//p' "$ROOT/plugin/hermes-youtube/plugin.yaml")
# una carpeta por versión Y commit: la instalación anterior queda intacta para volver (volver.sh)
REV=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)
[ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ] || REV="$REV-local"
DEST="$HYT/$VERSION-$REV"
ANTERIOR=$(readlink "$HYT/actual" 2>/dev/null || true)
echo "hermes-youtube $VERSION → $DEST"
$SECO && { echo "(en seco: no se cambia nada)"; exit 0; }

# ── 1. el arnés, versionado ─────────────────────────────────────────────────────────────────────────────────────────
mkdir -p "$DEST" "$HYT/canales" "$HYT/puertas"
# el material de un canal (fuentes/, privado/, canales/) nunca viaja con el código, ni aunque esté en la carpeta del repo
rsync -a --delete --exclude .git --exclude tests --exclude evals --exclude '__pycache__' --exclude .DS_Store --exclude node_modules \
  --exclude /fuentes --exclude /privado --exclude /canales "$ROOT/" "$DEST/"
ln -sfn "$DEST" "$HYT/actual"
ARNES="$HYT/actual"
jq -n --arg r "$ARNES" --arg v "$VERSION" --arg c "$DEST" --arg a "$ANTERIOR" \
  '{root: $r, version: $v, carpeta: $c, anterior: $a}' > "$HYT/instalacion.json"

# ── 2. quién decide ─────────────────────────────────────────────────────────────────────────────────────────────────
if [ ! -f "$HYT/aprobadores.json" ]; then
  TG=$(grep -h '^TELEGRAM_ALLOWED_USERS=' "$HH/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" | cut -d, -f1 || true)
  jq -n --arg u "$(id -un)" --arg t "$TG" '{yo: {nombre: $u, medios: ({local: $u, dashboard: $u} + (if $t != "" then {telegram: $t} else {} end)), canales: ["*"]}}' \
    > "$HYT/aprobadores.json"
  chmod 600 "$HYT/aprobadores.json"
  echo "Creado aprobadores.json (tú decides en todos los canales${TG:+; Telegram $TG})"
fi

# ── 3. el plugin y la CLI ───────────────────────────────────────────────────────────────────────────────────────────
mkdir -p "$HH/plugins" "$HOME/.local/bin"
rm -rf "$HH/plugins/hermes-youtube"
cp -R "$DEST/plugin/hermes-youtube" "$HH/plugins/hermes-youtube"
"$HERMES" plugins enable hermes-youtube >/dev/null 2>&1 || echo "AVISO: no pude activar el plugin (hermes plugins enable hermes-youtube)"
ln -sfn "$ARNES/hyt" "$HOME/.local/bin/hyt"
# ── 4. perfiles ─────────────────────────────────────────────────────────────────────────────────────────────────────
# la carpeta del perfil, no «hermes profile list | grep -q»: con pipefail, grep -q cierra la tubería, la lista muere
# por SIGPIPE y la segunda instalación creía que no había perfiles (y fallaba al crearlos)
existe() { [ -d "$HH/profiles/$1" ] || "$HERMES" profile list 2>/dev/null | grep -w "$1" >/dev/null; }
copiar_modelo() {  # mismo proveedor y modelo que el perfil principal; solo las claves del proveedor (nunca las del bot)
  local P=$1 PD="$HH/profiles/$1" k v
  for k in provider base_url api_mode default; do
    v=$("$HERMES" config get "model.$k" 2>/dev/null | tail -1 || true)
    [ -n "$v" ] && [ "$v" != None ] && "$HERMES" -p "$P" config set "model.$k" "$v" >/dev/null || true
  done
  mkdir -p "$PD"
  { grep -hE '^(OPENROUTER_API_KEY|ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|OPENAI_API_KEY)=' "$HH/.env" 2>/dev/null || true
    echo "HERMES_YT_HOME=$HYT"; } > "$PD/.env"
  chmod 600 "$PD/.env"
}
carta() {  # SOUL.md = carta del perfil + reglas comunes (con copia de la anterior)
  local PD="$HH/profiles/$1"
  mkdir -p "$PD"
  [ -f "$PD/SOUL.md" ] && ! cmp -s "$PD/SOUL.md" <(cat "$ROOT/perfiles/$1.md" "$ROOT/perfiles/comun.md") && cp "$PD/SOUL.md" "$PD/SOUL.md.bak-$(date +%Y%m%d%H%M%S)"
  cat "$ROOT/perfiles/$1.md" "$ROOT/perfiles/comun.md" > "$PD/SOUL.md"
}
skills_dirs() {  # las skills del arnés y las propias de cada canal (canales/<canal>/extensiones/skills)
  { echo "$ARNES/skills"; for d in "$HYT"/canales/*/extensiones/skills; do [ -d "$d" ] && echo "$d"; done; } | jq -Rnc '[inputs]'
}
DENY='["*hyt_puertas.py*","*hyt_encargos.py*","*hyt_canales.py*","*decidir-local*","*dato-local*","*aprobadores.json*","*secretos.env*","*hermes config*","*hermes cron*","*hermes kanban*","*sqlite3*","*git push*"]'

if ! existe yt-estacion; then
  "$HERMES" profile create yt-estacion --no-alias --no-skills \
    --description "Estación de hermes-youtube: ejecuta etapa.sh de cada tarjeta y mueve la tarjeta según el resultado. No decide nada." >/dev/null
  copiar_modelo yt-estacion
fi
carta yt-estacion
"$HERMES" -p yt-estacion tools disable web browser image_gen tts computer_use cronjob delegation code_execution connections memory >/dev/null 2>&1 || true
# Hermes corta los comandos en primer plano a los 420 s salvo que el perfil suba TERMINAL_MAX_FOREGROUND_TIMEOUT
# (en .env) y timeouts.tools.*: sin esto, una etapa de Claude de más de 7 min se pierde.
env_linea() {   # env_linea <perfil> <CLAVE> <valor>: pone o cambia la línea sin tocar el resto del .env
  local f="$HH/profiles/$1/.env"; touch "$f"; chmod 600 "$f"
  grep -v "^$2=" "$f" > "$f.tmp" || true; echo "$2=$3" >> "$f.tmp"; mv "$f.tmp" "$f"; chmod 600 "$f"
}
env_linea yt-estacion TERMINAL_MAX_FOREGROUND_TIMEOUT 9600
for kv in "terminal.timeout 9600" "terminal.lifetime_seconds 9600" "timeouts.tools.sequential_call 9600" \
          "timeouts.tools.concurrent_batch 9600" "curator.enabled false" "display.language es"; do
  "$HERMES" -p yt-estacion config set $kv >/dev/null 2>&1 || true
done
"$HERMES" -p yt-estacion config set approvals.deny "$DENY" >/dev/null 2>&1 || true

ROLES="yt-analista yt-estratega yt-espectador yt-titulador yt-miniaturista yt-investigador yt-guionista yt-verificador yt-retencion yt-doble yt-editor-jefe"
for P in $ROLES; do
  if ! existe "$P"; then
    "$HERMES" profile create "$P" --no-alias --no-skills \
      --description "$(sed -n '1s/^# //p' "$ROOT/perfiles/$P.md") de hermes-youtube: hace etapas de pipelines (no decide ni publica nada)." >/dev/null
    copiar_modelo "$P"
  fi
  carta "$P"
  "$HERMES" -p "$P" config set skills.external_dirs "$(skills_dirs)" >/dev/null 2>&1 || true
  "$HERMES" -p "$P" config set approvals.deny "$DENY" >/dev/null 2>&1 || true
  "$HERMES" -p "$P" tools disable web browser image_gen tts computer_use cronjob delegation >/dev/null 2>&1 || true
  env_linea "$P" TERMINAL_MAX_FOREGROUND_TIMEOUT 2400
  for kv in "terminal.timeout 2400" "terminal.lifetime_seconds 2400" "timeouts.tools.sequential_call 2400" \
            "timeouts.tools.concurrent_batch 2400" "display.language es"; do
    "$HERMES" -p "$P" config set $kv >/dev/null 2>&1 || true
  done
done

# ── 5. la coordinadora (opcional) ───────────────────────────────────────────────────────────────────────────────────
if $COORD; then
  S="$HH/SOUL.md"; touch "$S"; cp "$S" "$S.bak-$(date +%Y%m%d%H%M%S)"
  python3 - "$S" "$ROOT/perfiles/coordinadora.md" <<'PY'
import re, sys
s, nueva = open(sys.argv[1]).read(), open(sys.argv[2]).read().strip()
bloque = f"<!-- hermes-youtube:inicio -->\n{nueva}\n<!-- hermes-youtube:fin -->"
if "<!-- hermes-youtube:inicio -->" in s:
    s = re.sub(r"<!-- hermes-youtube:inicio -->.*?<!-- hermes-youtube:fin -->", lambda m: bloque, s, flags=re.S)
else:
    s = s.rstrip() + "\n\n" + bloque + "\n"
open(sys.argv[1], "w").write(s)
PY
  # lo irreversible nunca, ni siquiera con la terminal libre (se suma a lo que ya hubiera en approvals.deny)
  ACTUAL=$("$HERMES" config get approvals.deny --json 2>/dev/null || echo '[]'); jq -e 'type == "array"' <<< "$ACTUAL" >/dev/null 2>&1 || ACTUAL='[]'
  "$HERMES" config set approvals.deny "$(jq -c '. + ["*hyt_puertas.py*","*decidir-local*","*dato-local*","*/puertas/g*","*aprobadores.json*","*hermes-youtube/secretos.env*"] | unique' <<< "$ACTUAL")" >/dev/null
  echo "Coordinadora: carta añadida a $S; lo irreversible (decidir puertas, aprobadores, secretos) prohibido"
  # su manera de trabajar no cambia sola: Hermes puede proponer skills nuevas, pero escribirlas pide aprobación
  "$HERMES" config set skills.write_approval true >/dev/null 2>&1 || true
  # en Telegram solo la respuesta final (sin los comentarios intermedios del modelo mientras usa herramientas)
  "$HERMES" config set display.interim_assistant_messages false >/dev/null 2>&1 || true
fi
if $ESTRICTA; then
  GUARDIA="python3 -I $ARNES/guardia/guardia.py $ARNES"
  "$HERMES" config set hooks.pre_tool_call \
    "[{\"matcher\":\"terminal|write_file|patch|read_file|search_files|execute_code|delegate_task|cronjob\",\"command\":\"$GUARDIA\",\"timeout\":10,\"fail_closed\":true}]" >/dev/null
  python3 - "$HH/shell-hooks-allowlist.json" "$GUARDIA" <<'PY'
import json, sys, datetime
f, c = sys.argv[1:]
try:
    d = json.load(open(f))
except (OSError, ValueError):
    d = {"approvals": []}
d["approvals"] = [a for a in d.get("approvals", []) if "guardia/guardia.py" not in a.get("command", "")]
d["approvals"].append({"event": "pre_tool_call", "command": c,
                       "approved_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
json.dump(d, open(f, "w"), indent=2)
PY
  echo "Coordinadora estricta: guardia activo (solo hyt y lectura)"
fi

# ── 6. avisos de configuración ──────────────────────────────────────────────────────────────────────────────────────
v=$("$HERMES" config get kanban.dispatch_interval_seconds 2>/dev/null | tail -1 || true)
[ -n "$v" ] && [ "$v" -gt 15 ] 2>/dev/null && echo "AVISO: las etapas tardan hasta ${v}s en arrancar: hermes config set kanban.dispatch_interval_seconds 10"
v=$("$HERMES" config get kanban.auto_decompose 2>/dev/null | tail -1 || true)
[ "$v" = true ] && echo "AVISO: kanban.auto_decompose está activo: hermes config set kanban.auto_decompose false"
echo "Listo. Reinicia el gateway (hermes gateway restart o el servicio) para cargar el plugin."
