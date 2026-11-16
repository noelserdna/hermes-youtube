#!/usr/bin/env bash
# Carga de fuentes sin modelo: de una carpeta o de un zip, por tramos, sin ruido, con el ritmo medido en las fuentes
# guionizadas, los compilados marcados y las citas literales comprobadas. Con transcripciones inventadas.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HERMES_YT_HOME="$T/home" HOME="$T/casa"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }
F="python3 $ROOT/plugin/hermes-youtube/hyt_fuentes.py"
C="$HERMES_YT_HOME/canales/cocina"; mkdir -p "$C"
echo '{"slug":"cocina","transcripcion":{"ruido":["(inaudible)"]}}' > "$C/canal.json"

O="$T/origen/Charlas"; mkdir -p "$O"
frase() { for i in $(seq 1 "$1"); do printf 'palabra%s ' "$i"; done; }
printf '# V01 - Arroz suelto\n\n[0:00:00]\nEl arroz no se pasa por el tiempo. [música] Se pasa por el agua (inaudible) y ya.\n\n[0:01:00]\n%s\n' "$(frase 290)" > "$O/V01 - Arroz suelto.txt"
printf 'WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nEl arroz\n\n00:01:58.000 --> 00:02:00.000\nfin\n' > "$O/V01 - Arroz suelto.es-orig.vtt"
printf '# V02 - Sofrito\n\n[0:00:00]\nEl sofrito es paciencia y fuego bajo, nada más, y quien te diga otra cosa no ha hecho uno bueno en su vida.\n\n[0:00:40]\n%s\n' "$(frase 140)" > "$O/V02 - Sofrito.txt"
printf '# V03 - Caldo\n\n[0:00:00]\nUn caldo se hace con huesos, verdura y tiempo, y no hay atajo que valga para sacarle el sabor de verdad.\n' > "$O/V03 - Caldo.txt"
cat "$O/V01 - Arroz suelto.txt" "$O/V02 - Sofrito.txt" "$O/V03 - Caldo.txt" > "$O/Todo junto.txt"
(cd "$T/origen" && zip -qr "$T/charlas.zip" Charlas)

si "carga desde una carpeta" "$F cargar cocina '$O' --coleccion charlas --tipo guionizado"
J="$C/fuentes/charlas"; I="$C/fuentes/indice.json"
si "una ficha por transcripción, con su identificador corto" "test -f $J/v01.json -a -f $J/v02.json -a -f $J/v01.txt"
si "parte por las marcas de tiempo" "jq -e '.tramos | length == 2 and .[1].t == 60 and .[1].marca == \"0:01:00\"' $J/v01.json"
si "quita el ruido automático y el del canal, y no toca las palabras" "jq -e '.tramos[0].texto == \"El arroz no se pasa por el tiempo. Se pasa por el agua y ya.\"' $J/v01.json"
si "mide el ritmo con los subtítulos: palabras por minuto" "jq -e '.ppm == 152' $J/v01.json"
si "sin subtítulos no hay ritmo" "jq -e '.ppm == 0' $J/v02.json"
si "el fichero que contiene a varios otros se marca como compilado" "jq -e '[.fuentes[] | select(.compilado)] | length == 1 and .[0].id == \"todo-junto\"' $I"
si "el índice guarda el ritmo medido del canal" "jq -e '.ppm_medido == 152 and (.fuentes | length == 4)' $I"
si "recargar una colección la sustituye, no la duplica" "$F cargar cocina '$O' --coleccion charlas --tipo guionizado && jq -e '.fuentes | length == 4' $I"
si "carga desde un zip, en otra colección" "$F cargar cocina '$T/charlas.zip' --coleccion directos --tipo directo && jq -e '.fuentes | length == 8' $I"
si "en un directo no se mide el ritmo aunque haya subtítulos" "jq -e '.ppm == 0' $C/fuentes/directos/v01.json"
si "la lista enseña las fuentes y el ritmo" "$F lista cocina | grep -q 'charlas/v01.*152 ppm' && $F lista cocina | grep -q 'compilado'"
no "un canal que no existe se rechaza" "$F cargar nadie '$O' --coleccion charlas"
no "un nombre de colección con espacios se rechaza" "$F cargar cocina '$O' --coleccion 'mis charlas'"
no "un origen sin transcripciones se rechaza" "mkdir -p $T/vacio && $F cargar cocina '$T/vacio' --coleccion nada"
python3 - "$ROOT/plugin/hermes-youtube" <<'PY' && ok "cita literal: se encuentra sin tildes ni mayúsculas, y una inventada no" || bad "citas"
import sys; sys.path.insert(0, sys.argv[1]); import hyt_fuentes as F
assert F.cita("cocina", "charlas", "v01", "EL ARROZ NO SE PASA POR EL TIEMPO") == {"t": 0, "marca": "0:00:00"}
assert F.cita("cocina", "charlas", "v01", "el arroz se pasa siempre por el fuego") is None
assert F.cita("cocina", "charlas", "v01", "el arroz") is None          # demasiado corta para probar nada
PY
exit $fail
