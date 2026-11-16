#!/usr/bin/env bash
# Ejecutor falso: escribe la salida que le pide el prompt («Write your result to: X») y responde según FALSO_MODO.
DIR=$1; NOMBRE=$2; PROMPT=$3; MODELO=${4:-}; PERFIL=${5:-}; SKILL=${6:-}
echo "$NOMBRE|$MODELO|$PERFIL|$SKILL" >> "${FALSO_EJECUCIONES:-/dev/null}"
mkdir -p "$DIR/.estado"; printf "%s" "$PROMPT" > "$DIR/.estado/ultimo-prompt.txt"
SALIDA=$(printf '%s' "$PROMPT" | sed -nE 's/^Write your result to: (.*)$/\1/p')
# la salida pedida: texto con su línea VEREDICTO, o JSON válido con el campo «veredicto» si acaba en .json
escribir() {  # escribir <APROBADO|CAMBIOS> [cambio]
  case "$SALIDA" in
    *.json) jq -n --arg n "$NOMBRE" --arg v "$1" --arg c "${2:-}" '{veredicto: $v, resultado: ("Resultado de " + $n)} + (if $c == "" then {} else {cambios: [$c]} end)' > "$DIR/$SALIDA" ;;
    *) { printf 'Resultado de %s\n' "$NOMBRE"; [ -z "${2:-}" ] || printf '1. Cambio obligatorio: %s\n' "$2"; printf 'VEREDICTO: %s\n' "$1"; } > "$DIR/$SALIDA" ;;
  esac
}
case "${FALSO_MODO:-ok}" in
  ok) escribir APROBADO
      jq -nc --arg r "hecho $NOMBRE" '{outcome:"done", reason:"ok", resumen:$r, cost_usd:0.01, minutes:0}' ;;
  cambios) escribir CAMBIOS "corregir la cifra"
      jq -nc --arg r "hecho $NOMBRE" '{outcome:"done", reason:"ok", resumen:$r, cost_usd:0.01, minutes:0}' ;;
  sinsalida) jq -nc '{outcome:"done", reason:"ok"}' ;;
  falla) jq -nc '{outcome:"failed", reason:"algo falló"}' ;;
esac
