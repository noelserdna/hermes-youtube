#!/usr/bin/env bash
# Instalación en un HOME de pruebas, con Hermes falso: copia versionada, aprobadores, plugin, CLI, perfiles, la
# coordinadora (carta, prohibiciones y guardia) y volver a la instalación anterior. Nunca toca el Hermes de verdad.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/casa" HERMES_BIN="$ROOT/tests/dobles/hermes" FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros"
unset HERMES_YT_HOME
mkdir -p "$HOME/.hermes"
printf 'TELEGRAM_BOT_TOKEN=secreto\nTELEGRAM_ALLOWED_USERS=12345\nCLAUDE_CODE_OAUTH_TOKEN=tok\n' > "$HOME/.hermes/.env"
echo "Eres mi asistente." > "$HOME/.hermes/SOUL.md"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
H="$HOME/.hermes"; S="$H/hermes-youtube"
# una copia del repo con material privado al lado: lo que no es código no debe viajar a la instalación
R="$T/repo"; mkdir -p "$R"
rsync -a --exclude .git --exclude fuentes --exclude privado --exclude canales --exclude '__pycache__' "$ROOT/" "$R/"
mkdir -p "$R/fuentes/coleccion" "$R/privado" "$R/canales/uno"; echo "transcripción privada" > "$R/fuentes/coleccion/a.txt"
echo "nota privada" > "$R/privado/nota.md"; echo "{}" > "$R/canales/uno/canal.json"

si "en seco no cambia nada" "bash $R/instalar.sh --seco | grep -q 'en seco' && [ ! -d $S ]"
si "una opción desconocida enseña la ayuda y no instala" "! bash $R/instalar.sh --otra-cosa > $T/ayuda && grep -q 'bash instalar.sh' $T/ayuda && [ ! -d $S ]"
si "instalar sin la coordinadora" "bash $R/instalar.sh"
si "copia versionada y enlace actual" "[ -L $S/actual ] && [ -f $S/actual/pipelines/guion.json ] && [ -f $S/actual/skills/escribir-guion/SKILL.md ] && [ -f $S/actual/plantillas/canal.json ] && [ ! -d $S/actual/tests ]"
si "el material privado del repo no viaja con la instalación" "[ ! -e $S/actual/fuentes ] && [ ! -e $S/actual/privado ] && [ ! -e $S/actual/canales ] && ! grep -rq 'transcripción privada' $S/actual"
si "la carpeta lleva versión y commit, e instalacion.json la apunta" "jq -e '(.carpeta | test(\"/[0-9]+\\\\.[0-9]+\\\\.[0-9]+-\")) and .version == \"0.1.0\" and (.root | endswith(\"/hermes-youtube/actual\"))' $S/instalacion.json"
si "aprobadores: tú, por local, panel y Telegram, en todos los canales" "jq -e '.yo.medios.telegram == \"12345\" and .yo.medios.local == \"$(id -un)\" and .yo.medios.dashboard == \"$(id -un)\" and .yo.canales == [\"*\"]' $S/aprobadores.json && [ \$(python3 -c \"import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 0o777)[2:])\" $S/aprobadores.json) = 600 ]"
si "plugin copiado y activado" "[ -f $H/plugins/hermes-youtube/__init__.py ] && [ -f $H/plugins/hermes-youtube/dashboard/manifest.json ] && grep -q 'plugins enable hermes-youtube' $FALSO_LLAMADAS"
si "la CLI hyt en ~/.local/bin" "[ -L $HOME/.local/bin/hyt ] && $HOME/.local/bin/hyt canales | grep -q 'ningún canal'"
si "perfiles creados: estación y 12 de rol" "[ \$(grep -c '^profile create' $FALSO_LLAMADAS) = 13 ] && grep -q '^profile create yt-estacion ' $FALSO_LLAMADAS && grep -q '^profile create yt-editor-jefe ' $FALSO_LLAMADAS"
si "cada perfil de rol de las pipelines tiene su perfil de Hermes" "for p in \$(jq -r '.etapas[].perfil' $ROOT/pipelines/*.json | sort -u); do grep -q \"^profile create \$p \" $FALSO_LLAMADAS || exit 1; done"
si "carta de rol = rol + reglas comunes" "grep -q '^# Guionista' $H/profiles/yt-guionista/SOUL.md && grep -q 'Reglas comunes de hermes-youtube' $H/profiles/yt-guionista/SOUL.md"
si "la descripción del perfil sale de su carta" "grep -q 'profile create yt-doble .*--description Doble de voz de hermes-youtube' $FALSO_LLAMADAS"
si "los perfiles no reciben el token del bot" "! grep -q TELEGRAM $H/profiles/yt-analista/.env && grep -q CLAUDE_CODE_OAUTH_TOKEN $H/profiles/yt-analista/.env && grep -q 'HERMES_YT_HOME=$S' $H/profiles/yt-analista/.env"
si "skills del arnés en los perfiles de rol" "grep -q 'yt-guionista config set skills.external_dirs .*hermes-youtube/actual/skills' $FALSO_LLAMADAS"
si "los perfiles de rol trabajan sin web: solo material propio" "grep -q -- '-p yt-investigador tools disable web browser' $FALSO_LLAMADAS"
si "solo quien investiga la versión con fuentes externas tiene web (y sin navegador ni delegación)" "grep -q -- '-p yt-investigador-web tools enable web' $FALSO_LLAMADAS && grep -q -- '-p yt-investigador-web tools disable browser' $FALSO_LLAMADAS && ! grep -q -- '-p yt-investigador-web tools disable web' $FALSO_LLAMADAS && [ \$(grep -c -- 'tools enable web' $FALSO_LLAMADAS) = 1 ]"
si "la estación aguanta etapas largas" "grep -q 'TERMINAL_MAX_FOREGROUND_TIMEOUT=9600' $H/profiles/yt-estacion/.env && grep -q -- '-p yt-estacion config set terminal.timeout 9600' $FALSO_LLAMADAS"
si "sin --coordinadora no toca el SOUL principal ni pone el guardia" "[ \"\$(cat $H/SOUL.md)\" = 'Eres mi asistente.' ] && [ ! -f $H/shell-hooks-allowlist.json ] && ! grep -q 'hooks.pre_tool_call' $FALSO_LLAMADAS"
echo "secreto viejo" > "$H/profiles/yt-analista/.env"
jq '.yo.nombre = "Otra"' "$S/aprobadores.json" > "$T/ap" && cp "$T/ap" "$S/aprobadores.json"
si "reinstalar no recrea perfiles ni pisa sus claves ni los aprobadores" "bash $R/instalar.sh && [ \$(grep -c '^profile create' $FALSO_LLAMADAS) = 13 ] && grep -q 'secreto viejo' $H/profiles/yt-analista/.env && jq -e '.yo.nombre == \"Otra\"' $S/aprobadores.json"
si "con --coordinadora: carta y prohibiciones duras, sin guardia" "bash $R/instalar.sh --coordinadora && grep -q 'Eres mi asistente' $H/SOUL.md && grep -q 'hermes-youtube:inicio' $H/SOUL.md && grep -q 'Coordinadora de hermes-youtube' $H/SOUL.md && grep -q 'config set approvals.deny .*hyt_puertas.py' $FALSO_LLAMADAS && [ ! -f $H/shell-hooks-allowlist.json ]"
si "con --coordinadora-estricta: además el guardia, aprobado y fail-closed" "bash $R/instalar.sh --coordinadora-estricta && jq -e '.approvals | length == 1 and (.[0].command | test(\"guardia/guardia.py .*/hermes-youtube/actual\$\"))' $H/shell-hooks-allowlist.json && grep -q 'config set hooks.pre_tool_call .*fail_closed.*true' $FALSO_LLAMADAS"
si "el guardia instalado funciona: deja consultar y bloquea decidir" "printf '%s' '{\"tool_name\":\"terminal\",\"tool_input\":{\"command\":\"hyt estado\"}}' | python3 -I $S/actual/guardia/guardia.py $S/actual && ! printf '%s' '{\"tool_name\":\"terminal\",\"tool_input\":{\"command\":\"hyt decidir g1 acepto\"}}' | python3 -I $S/actual/guardia/guardia.py $S/actual"
si "la carta y el guardia no se duplican al reinstalar" "bash $R/instalar.sh --coordinadora-estricta && [ \$(grep -c 'hermes-youtube:inicio' $H/SOUL.md) = 1 ] && jq -e '.approvals | length == 1' $H/shell-hooks-allowlist.json"
si "no programa tareas ni toca el crontab" "! grep -q 'cron create\|cron edit' $FALSO_LLAMADAS"

# ── la instalación funciona: alta de un canal y su primer encargo ──
si "desde la instalación: alta de un canal con su memoria" "$HOME/.local/bin/hyt alta demo 'Canal Demo' 'Persona Ejemplo' | grep -q 'Memoria sembrada' && [ -f $S/canales/demo/canal.json ] && [ -f $S/canales/demo/wiki/SCHEMA.md ]"
si "y lanzar: las tarjetas llaman al etapa.sh de la instalación (no al del repo)" "$HOME/.local/bin/hyt lanzar demo propuesta | grep -q 'en marcha' && grep -q 'Ejecuta: bash .*/\.hermes/hermes-youtube/0\.1\.0-[^/ ]*/etapa.sh demo propuesta-' $FALSO_LLAMADAS"

# ── volver a la instalación anterior sin tocar datos ──
ANT=$(readlink $S/actual); cp -a "$ANT" "$S/0.0.9-viejo"; echo "# viejo" >> "$S/0.0.9-viejo/plugin/hermes-youtube/plugin.yaml"
si "volver.sh reapunta actual y recopia el plugin" "bash $R/volver.sh 0.0.9-viejo --sin-reinicio && [ \"\$(readlink $S/actual)\" = $S/0.0.9-viejo ] && grep -q '# viejo' $H/plugins/hermes-youtube/plugin.yaml && jq -e '.carpeta == \"$S/0.0.9-viejo\" and .anterior == \"$ANT\"' $S/instalacion.json"
si "y sin argumento vuelve a la de antes" "bash $R/volver.sh --sin-reinicio && [ \"\$(readlink $S/actual)\" = $ANT ] && ! grep -q '# viejo' $H/plugins/hermes-youtube/plugin.yaml"
si "rechaza una carpeta que no es una instalación" "! bash $R/volver.sh /tmp --sin-reinicio"
si "volver no toca los datos del canal" "[ -f $S/canales/demo/canal.json ] && [ -f $S/aprobadores.json ]"
exit $fail
