#!/usr/bin/env bash
# Canales: alta desde la plantilla, validación de tipos y rangos, capacidades y cambios de configuración con historial.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
C="python3 $ROOT/plugin/hermes-youtube/hyt_canales.py"
K="$HERMES_YT_HOME/canales"
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }

si "la plantilla es un JSON con la forma de partida" "jq -e '.version == 1 and .idioma == \"es-ES\" and .reglas.titulo_max == 55 and .reglas.minutos == [13, 15] and (.permite | all(. == false)) and .politicas.tope_semanal == 0' $ROOT/plantillas/canal.json"
si "alta de un canal nuevo" "$C alta canal-uno 'Canal Uno' 'Persona Ejemplo'"
si "canal.json sale de la plantilla con su nombre y quien presenta" "jq -e '.slug == \"canal-uno\" and .nombre == \"Canal Uno\" and .presentador == \"Persona Ejemplo\" and .reglas.ppm == 150 and .pilares == []' $K/canal-uno/canal.json"
si "crea su carpeta con wiki, fuentes y secretos 600" \
   "[ -d $K/canal-uno/wiki ] && [ -d $K/canal-uno/fuentes ] && [ \$(python3 -c \"import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 0o777)[2:])\" $K/canal-uno/secretos.env) = 600 ]"
si "el alta queda en el historial" "jq -e '.accion == \"alta\" and .presentador == \"Persona Ejemplo\"' $K/canal-uno/config.jsonl"
no "no repite un alta" "$C alta canal-uno 'Otro' 'Otra Persona'"
no "rechaza un slug con mayúsculas" "$C alta Malo 'Malo' 'Persona'"
no "rechaza un nombre reservado" "$C alta cartera 'Cartera' 'Persona'"
no "rechaza un alta sin presentador" "$C alta sin-nadie 'Sin nadie' ''"
si "un alta rechazada no deja canal.json" "[ ! -f $K/sin-nadie/canal.json ]"
si "el resumen dice canal, quién presenta y sus capacidades" "$C listar | grep -q 'Canal Uno (canal-uno) · presenta: Persona Ejemplo' && $C listar | grep -q 'capacidades: ninguna'"

# ── validación ──
no "rechaza una zona horaria inventada" "$C config canal-uno zona_horaria Marte/Olimpo"
no "rechaza un idioma mal escrito" "$C config canal-uno idioma español"
si "acepta un idioma con país y sin él" "$C config canal-uno idioma en-US && $C config canal-uno idioma es && $C config canal-uno idioma es-ES"
no "pilares: tipo desconocido" "$C config canal-uno pilares '[{\"id\":\"a\",\"nombre\":\"A\",\"tipo\":\"otro\"}]'"
no "pilares: id repetido" "$C config canal-uno pilares '[{\"id\":\"a\",\"nombre\":\"A\",\"tipo\":\"pilar\"},{\"id\":\"a\",\"nombre\":\"B\",\"tipo\":\"prueba\"}]'"
no "pilares: sin nombre" "$C config canal-uno pilares '[{\"id\":\"a\",\"tipo\":\"pilar\"}]'"
si "pilares: pilar y prueba" "$C config canal-uno pilares '[{\"id\":\"oficio\",\"nombre\":\"El oficio\",\"tipo\":\"pilar\"},{\"id\":\"ensayo\",\"nombre\":\"Ensayos\",\"tipo\":\"prueba\"}]'"
si "con pilares, la capacidad «pilares»" "$C capacidades canal-uno | grep -qw pilares"
no "reglas: título fuera de rango" "$C config canal-uno reglas.titulo_max 500"
no "reglas: un texto donde va un número" "$C config canal-uno reglas.ppm rapido"
no "reglas: un booleano no es un número" "$C config canal-uno reglas.miniaturas true"
no "reglas: minutos al revés" "$C config canal-uno reglas.minutos '[15, 13]'"
no "reglas: más títulos presentados que internos" "$C config canal-uno reglas.titulos_internos 3"
si "reglas: valores válidos" "$C config canal-uno reglas.minutos '[8, 10]' && $C config canal-uno reglas.titulo_max 60 && jq -e '.reglas.minutos == [8, 10] and .reglas.titulo_max == 60' $K/canal-uno/canal.json"
no "listas: un elemento vacío" "$C config canal-uno prohibidas '[\"vale\", \"\"]'"
no "listas: un texto suelto no es una lista" "$C config canal-uno excluido precios"
si "listas: textos" "$C config canal-uno prohibidas '[\"sin duda\", \"en el mundo actual\"]' && $C config canal-uno excluido '[\"precios\"]'"
si "patrones: con nombre, expresión regular y gravedad" "$C config canal-uno excluido '[{\"nombre\":\"precio\",\"patron\":\"[0-9]+ ?(€|euros)\",\"grave\":true},\"ofertas\"]' && $C config canal-uno sin_promesas '[{\"patron\":\"gana(r)? dinero\"}]'"
no "patrones: una expresión regular que no compila" "$C config canal-uno excluido '[{\"nombre\":\"mal\",\"patron\":\"(sin cerrar\"}]'"
no "patrones: sin patrón" "$C config canal-uno sin_promesas '[{\"nombre\":\"dinero\"}]'"
no "patrones: gravedad que no es true o false" "$C config canal-uno excluido '[{\"patron\":\"x\",\"grave\":\"mucho\"}]'"
no "transcripción: correcciones que no son textos" "$C config canal-uno transcripcion.correcciones '{\"jason\": 3}'"
si "transcripción: correcciones y ruido" "$C config canal-uno transcripcion '{\"correcciones\":{\"jason\":\"JSON\"},\"ruido\":[\"[Música]\"]}'"
no "personas: papel desconocido" "$C config canal-uno personas '{\"ana\":{\"nombre\":\"Ana\",\"correo\":\"ana@ejemplo.com\",\"roles\":[\"jefa\"]}}'"
no "personas: correo mal escrito" "$C config canal-uno personas '{\"ana\":{\"nombre\":\"Ana\",\"correo\":\"ana-arroba\",\"roles\":[\"datos\"]}}'"
no "personas: sin nombre" "$C config canal-uno personas '{\"ana\":{\"correo\":\"ana@ejemplo.com\",\"roles\":[\"datos\"]}}'"
si "personas: con sus papeles" "$C config canal-uno personas '{\"ana\":{\"nombre\":\"Ana\",\"correo\":\"ana@ejemplo.com\",\"roles\":[\"marketing\",\"datos\"]},\"leo\":{\"nombre\":\"Leo\",\"correo\":\"\",\"roles\":[\"presentador\"]}}'"
no "permite: solo interruptores" "$C config canal-uno permite.cifras_propias quiza"
si "permite: encender uno" "$C config canal-uno permite.cifras_propias true && jq -e '.permite.cifras_propias == true and .permite.promesas_empleo == false' $K/canal-uno/canal.json"
no "políticas: tope negativo" "$C config canal-uno politicas.tope_semanal -1"
no "políticas: pausado que no es true o false" "$C config canal-uno politicas.pausado quiza"
no "no deja cambiar el slug" "$C config canal-uno slug otro"
no "una clave con caracteres raros" "$C config canal-uno 'reglas..x' 1"
si "un cambio de config queda en el historial (antes y después)" "grep '\"clave\": \"reglas.titulo_max\"' $K/canal-uno/config.jsonl | jq -e '.antes == 55 and .despues == 60'"
si "un cambio rechazado no se escribe" "jq -e '.zona_horaria == \"Europe/Madrid\" and .reglas.ppm == 150 and .reglas.titulos_presentados == 5' $K/canal-uno/canal.json"
si "validar un canal sano" "$C validar canal-uno"
si "validar dice qué falla en un canal.json tocado a mano" "jq '.reglas.rondas_max = 0 | .presentador = \"\"' $K/canal-uno/canal.json > $T/roto && cp $K/canal-uno/canal.json $T/sano && cp $T/roto $K/canal-uno/canal.json && ! $C validar canal-uno > $T/errores; cp $T/sano $K/canal-uno/canal.json; grep -q 'reglas.rondas_max' $T/errores && grep -q 'presentador' $T/errores"

# ── capacidades ──
no "sin voz.md no hay capacidad «voz»" "$C capacidades canal-uno | grep -qw voz"
si "con wiki/concepts/voz.md, «voz»" "mkdir -p $K/canal-uno/wiki/concepts && echo '# Voz' > $K/canal-uno/wiki/concepts/voz.md && $C capacidades canal-uno | grep -qw voz"
no "un índice de fuentes vacío no cuenta" "echo '[]' > $K/canal-uno/fuentes/indice.json && $C capacidades canal-uno | grep -qw fuentes"
no "ni un índice con sus colecciones vacías" "echo '{\"fuentes\": []}' > $K/canal-uno/fuentes/indice.json && $C capacidades canal-uno | grep -qw fuentes"
si "con alguna entrada en fuentes/indice.json, «fuentes»" "echo '[{\"id\":\"f1\"}]' > $K/canal-uno/fuentes/indice.json && $C capacidades canal-uno | grep -qw fuentes"
no "sin inventario.json no hay «inventario»" "$C capacidades canal-uno | grep -qw inventario"
si "con inventario.json, «inventario»" "echo '{}' > $K/canal-uno/inventario.json && [ \"\$($C capacidades canal-uno)\" = 'fuentes inventario pilares voz' ]"
si "listar enseña todos" "$C alta canal-dos 'Canal Dos' 'Otra Persona' && [ \$($C listar --json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))') = 2 ]"
no "un canal que no existe" "$C ver no-existe"

python3 - "$ROOT" <<'PY' && ok "secretos: los del canal mandan sobre los globales y no hay comentarios" || bad "secretos"
import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_canales", Path(sys.argv[1]) / "plugin/hermes-youtube/hyt_canales.py")
C = importlib.util.module_from_spec(spec); sys.modules["hyt_canales"] = C; spec.loader.exec_module(C)
h = Path(os.environ["HERMES_YT_HOME"])
(h / "secretos.env").write_text("UNA=global\nOTRA='abc'\n")
(h / "canales/canal-uno/secretos.env").write_text("# nota\nUNA=propia\n")
s = C.secretos("canal-uno")
assert s == {"UNA": "propia", "OTRA": "abc"}, s
PY
exit $fail
