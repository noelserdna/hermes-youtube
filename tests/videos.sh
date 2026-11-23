#!/usr/bin/env bash
# Los vídeos de un canal, sin IA: el estado visible de cada uno a lo largo de su vida, las marcas de grabado y
# publicado, la lista de publicados, la entrega del paquete por partes y lo que el canal aprende al aprobar un guion.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }
P="$ROOT/plugin/hermes-youtube"; K="$HERMES_YT_HOME/canales/cocina"; V="python3 $P/hyt_videos.py"; PU="python3 $P/hyt_puertas.py"
python3 "$P/hyt_canales.py" alta cocina "Cocina clara" Marta >/dev/null
echo '{"max_decisiones": 0}' > "$HERMES_YT_HOME/yt.json"
jq -n --arg u "$(id -un)" '{admin: {nombre: "Admin", medios: {local: $u}, canales: ["*"]}}' > "$HERMES_YT_HOME/aprobadores.json"
estado() { $V lista cocina | grep -c "^$1 "; }
etapas() { for e in $(jq -r '.etapas[].id' "$K/encargos/$1/encargo.json"); do bash "$ROOT/etapa.sh" cocina "$1" "$e" >/dev/null 2>&1; done; }
puerta() { jq -r '.puerta_id // ""' "$K/encargos/$1/encargo.json"; }

python3 "$P/hyt_encargos.py" lanzar cocina titulo-miniatura --param "tema=Arroz suelto en casa" --param pilar=arroces >/dev/null
TM=$(ls "$K/encargos" | grep '^titulo-miniatura' | head -1)
si "un tema elegido es un vídeo en «Elegido», con su tema como título" "$V lista cocina | grep -q '^Elegido .*arroces .*Arroz suelto en casa'"
etapas "$TM"; $PU decidir-local "$(puerta $TM)" algunas "titulo: 1" >/dev/null
G=$(ls "$K/encargos" | grep '^guion-' | grep -v '^guion-investigado' | head -1); D="$K/encargos/$G"
GI=$(ls "$K/encargos" | grep '^guion-investigado' | head -1)
si "elegir título y miniatura lanza las dos versiones del guion, gemelas" "[ -n \"$GI\" ] && jq -e '.gemelos | length == 2' $K/encargos/$G/encargo.json && jq -e '.version == \"investigada\"' $K/encargos/$GI/encargo.json"
# aquí se prueba el camino de una sola versión: la investigada se para y la propia sigue sola
jq '.estado = "parado"' "$K/encargos/$GI/encargo.json" > "$T/e" && cp "$T/e" "$K/encargos/$GI/encargo.json"
si "al elegir título y miniatura pasa a «Título y miniatura elegidos», y sigue siendo un solo vídeo" "[ \$(estado 'Título y miniatura elegidos') = 1 ] && [ \$($V lista cocina | wc -l) = 1 ]"
deja() {  # lo que habrían dejado las etapas de verdad (el ejecutor de prueba escribe relleno)
  echo '{"titulo": "Arroz suelto: la regla del agua", "promesa": "Sabrás medir el agua", "miniatura": {"que_se_ve": "Una cazuela", "texto": "100 ML", "presentador": {"expresion": "duda", "foto_a_pedir": "De perfil, mirando la cazuela"}, "composicion": {"tipo": "plano-cenital"}}}' > "$D/eleccion.json"
  printf '## intro\nEl arroz no se pasa por el tiempo.[1] Se pasa por el agua.\n## cierre\nLa otra mitad es el fuego.\n' > "$D/guion.md"
  printf 'El arroz y su agua.\n\n00:00 La regla\n00:20 El fallo\n00:40 El reposo\n' > "$D/descripcion.md"
  echo '{"intro": {"ganchos": ["contra", "cifra"]}}' > "$D/escaleta.json"
  echo '{"material": [{"n": 1, "cita": "el arroz no se pasa por el tiempo, se pasa por el agua que le pones"}]}' > "$D/material.json"
  echo '{"piezas": [{"id": "p0001", "cita": "El arroz no se pasa por el tiempo, se pasa por el agua que le pones", "usado_en": []}, {"id": "p0002", "cita": "otra cosa distinta de la que no se habla en este guion", "usado_en": []}]}' > "$K/inventario.json"
}
etapas "$G"; deja
si "con el guion hecho está «En revisión de marketing», con su puerta y a quién espera" "$V lista cocina | grep -q '^En revisión de marketing' && python3 -c \"import sys; sys.path.insert(0,'$P'); import hyt_videos as V; v=V.lista('cocina')[0]; assert v['puerta']['tipo']=='revision' and v['puerta']['papel']=='marketing' and v['titulo']=='Arroz suelto: la regla del agua', v\""
no "un vídeo sin aprobar no se exporta" "$V exportar cocina $G guion"
no "ni se marca como grabado" "$V grabado cocina $G"
$PU decidir-local "$(puerta $G)" cambios "frase 2: yo diría otra cosa" >/dev/null
si "pedir rehacer lo deja en «Rehaciendo», en la ronda 1" "[ \$(estado Rehaciendo) = 1 ] && $V lista cocina | grep -q 'ronda 1/3'"
etapas "$G"; $PU decidir-local "$(puerta $G)" acepto >/dev/null
si "aprobada la primera revisión, y sin datos pendientes, pasa a «En revisión de quien presenta»" "[ \$(estado 'En revisión de quien presenta') = 1 ]"
$PU decidir-local "$(puerta $G)" acepto >/dev/null; deja
si "aprobado por quien presenta: «Aprobado»" "[ \$(estado Aprobado) = 1 ]"
si "el guion se exporta limpio: sin cabeceras ni marcas, una frase por línea" "[ \"\$($V exportar cocina $G guion | head -2 | tr '\n' '|')\" = 'El arroz no se pasa por el tiempo.|Se pasa por el agua.|' ] && ! $V exportar cocina $G guion | grep -q '\\[1\\]\\|##'"
si "se exportan el título, la descripción y la idea de miniatura con la foto que hay que hacer" "[ \"\$($V exportar cocina $G titulo)\" = 'Arroz suelto: la regla del agua' ] && $V exportar cocina $G descripcion | grep -q '00:20 El fallo' && $V exportar cocina $G miniatura | grep -q 'Foto que hay que hacer: De perfil'"
no "una parte que no existe se rechaza" "$V exportar cocina $G musica"
si "aprobar la última puerta ya dejó el guion como ejemplo de voz del canal" "test -s $K/guiones/$G.txt && grep -q '\"estado\": \"aprobado\"' $K/temas.jsonl"
python3 - "$P" "$G" <<'PY' && ok "al aprobarse, el canal aprende: guion como ejemplo, apertura apuntada y piezas marcadas como usadas" || bad "aprender del guion aprobado"
import json, sys
sys.path.insert(0, sys.argv[1]); import hyt_videos as V, hyt_canales as C
V.al_aprobar("cocina", sys.argv[2]); k = C.carpeta("cocina")
assert (k / "guiones" / f"{sys.argv[2]}.txt").read_text().startswith("El arroz no se pasa por el tiempo.")
a = [json.loads(x) for x in (k / "aperturas.jsonl").read_text().splitlines()]
assert a[-1]["frase"] == "El arroz no se pasa por el tiempo." and a[-1]["formulas"] == ["contra", "cifra"], a
inv = json.loads((k / "inventario.json").read_text())["piezas"]
assert inv[0]["usado_en"] == [sys.argv[2]] and inv[1]["usado_en"] == [], inv
V.al_aprobar("cocina", sys.argv[2]); assert json.loads((k / "inventario.json").read_text())["piezas"][0]["usado_en"] == [sys.argv[2]]   # no se repite
PY
si "se marca como grabado" "$V grabado cocina $G && [ \$(estado Grabado) = 1 ]"
si "y como publicado, con su enlace" "$V publicado cocina $G https://ejemplo.com/v1 && [ \$(estado Publicado) = 1 ]"
si "al publicarlo entra solo en la lista de publicados" "$V publicados cocina | grep -q 'Arroz suelto: la regla del agua  https://ejemplo.com/v1'"
python3 - "$P" <<'PY' && ok "la lista de publicados se mantiene a mano: alta, edición por id y baja" || bad "publicados a mano"
import sys
sys.path.insert(0, sys.argv[1]); import hyt_videos as V, hyt_pasos as S, hyt_base as B
n = V.publicado_poner("cocina", {"titulo": "El sofrito sin prisa", "pilar": "guisos"}, "marta"); assert n["id"] == "v-el-sofrito-sin-prisa", n
V.publicado_poner("cocina", {"id": n["id"], "titulo": "El sofrito, sin prisa", "url": "https://ejemplo.com/v2"})
p = {x["id"]: x for x in V.publicados("cocina")}; assert len(p) == 2 and p[n["id"]]["titulo"] == "El sofrito, sin prisa"
assert {x["titulo"] for x in S.banco("cocina") if x["estado"] == "publicado"} >= {"El sofrito, sin prisa", "Arroz suelto: la regla del agua"}   # avisan de parecidos
V.publicado_quitar("cocina", n["id"]); assert len(V.publicados("cocina")) == 1
for malo in (lambda: V.publicado_quitar("cocina", "no-existe"), lambda: V.publicado_poner("cocina", {"titulo": " "}), lambda: V.marcar("cocina", "nada", "grabado")):
    try: malo(); raise SystemExit(1)
    except B.Rechazo: pass
PY
python3 "$P/hyt_encargos.py" lanzar cocina titulo-miniatura --param "tema=Caldo de verdad" --param pilar=guisos >/dev/null
python3 "$P/hyt_encargos.py" lanzar cocina titulo-miniatura --param "tema=Tortilla jugosa" --param pilar=huevos >/dev/null
TM2=$(ls "$K/encargos" | grep '^titulo-miniatura-tortilla' | head -1); etapas "$TM2"; $PU decidir-local "$(puerta $TM2)" rechazo "no encaja" >/dev/null
si "un tema rechazado queda «Descartado», con su motivo" "$V lista cocina | grep -q '^Descartado .*Tortilla jugosa' && python3 -c \"import sys; sys.path.insert(0,'$P'); import hyt_videos as V; assert [v for v in V.lista('cocina') if v['estado_id']=='descartado'][0]['incidencia']=='no encaja'\""
si "el cierre de un guion puede llevar a otro vídeo elegido y sin publicar; nunca a sí mismo ni a uno descartado" "python3 -c \"import sys; sys.path.insert(0,'$P'); import hyt_videos as V; assert V.siguiente('cocina', excepto='$G') == 'Caldo de verdad', V.siguiente('cocina', excepto='$G')\""
exit $fail
