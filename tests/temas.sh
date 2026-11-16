#!/usr/bin/env bash
# Elegir temas de una propuesta, sin IA: cada tema elegido por su número arranca su propio encargo de título y
# miniatura, con su resumen y sus piezas en el brief, y queda anotado como elegido en el banco de ideas.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }
P="$ROOT/plugin/hermes-youtube"; K="$HERMES_YT_HOME/canales/cocina"
python3 "$P/hyt_canales.py" alta cocina "Cocina clara" Marta >/dev/null
echo '{"max_decisiones": 0}' > "$HERMES_YT_HOME/yt.json"
jq -n --arg u "$(id -un)" '{admin: {nombre: "Admin", medios: {local: $u}, canales: ["*"]}}' > "$HERMES_YT_HOME/aprobadores.json"
python3 "$P/hyt_encargos.py" lanzar cocina propuesta >/dev/null
EID=$(ls "$K/encargos" | head -1); D="$K/encargos/$EID"
tema() { jq -n --argjson n "$1" --arg t "$2" --arg p "$3" '{n: $n, id: ("c" + ($n|tostring)), pilar: $p, titulo: $t, resumen: ("Resumen de " + $t), piezas: ["p0001", "p0002"], origen: ["charlas/v01"], formato: "No es X, es Y", serie: ""}'; }
jq -n --argjson a "$(tema 1 'Arroz suelto: la regla del agua' arroces)" --argjson b "$(tema 2 'El sofrito sin prisa' guisos)" --argjson c "$(tema 3 'Caldo de verdad' guisos)" --argjson s "$(tema 9 'Arroz al horno' arroces)" \
  '{temas: [$a, $b, $c], suplentes: [$s], avisos: []}' > "$D/temas.json"
for e in generar puntuar; do bash "$ROOT/etapa.sh" cocina "$EID" "$e" >/dev/null 2>&1; done
G=$(jq -r .puerta_id "$D/encargo.json")
si "la propuesta acaba en una puerta para elegir temas" "jq -e '.tipo == \"elegir-temas\" and .al_aprobar == \"temas:titulo-miniatura\"' $HERMES_YT_HOME/puertas/$G.json"
no "elegir sin decir cuáles no vale" "python3 $P/hyt_puertas.py decidir-local $G algunas 'los que tú veas'"
si "y la puerta sigue abierta para decidir bien" "jq -e '.estado == \"abierta\"' $HERMES_YT_HOME/puertas/$G.json"
no "un número que no existe se rechaza al decidir" "python3 $P/hyt_puertas.py decidir-local $G algunas '1, 7'"
si "elegir «1, 3» y el suplente «4» lanza tres encargos de título y miniatura" "python3 $P/hyt_puertas.py decidir-local $G algunas '1, 3 y el 4' && [ \$(ls $K/encargos | grep -c '^titulo-miniatura') = 3 ]"
N=$(ls "$K/encargos" | grep '^titulo-miniatura-arroz-suelto' | head -1)
si "cada uno lleva su tema y su pilar como parámetros" "jq -e '.params.tema == \"Arroz suelto: la regla del agua\" and .params.pilar == \"arroces\"' $K/encargos/$N/encargo.json"
si "y su resumen, sus piezas y su formato en el brief" "grep -q 'Resumen de Arroz suelto' $K/encargos/$N/brief.md && grep -q 'p0001, p0002' $K/encargos/$N/brief.md && grep -q 'Formato: No es X, es Y' $K/encargos/$N/brief.md"
si "el suplente elegido también arranca" "ls $K/encargos | grep -q '^titulo-miniatura-arroz-al-horno'"
si "el tema no elegido no arranca" "! ls $K/encargos | grep -q 'sofrito'"
si "los elegidos quedan anotados en el banco de ideas con su encargo" "[ \$(jq -s '[.[] | select(.estado == \"elegida\" and (.sigue_en | startswith(\"titulo-miniatura\")))] | length' $K/temas.jsonl) = 3 ]"
si "la propuesta queda cerrada" "jq -e '.estado == \"cerrado\"' $D/encargo.json"
exit $fail
