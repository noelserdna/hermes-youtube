#!/usr/bin/env bash
# De punta a punta sin IA: lanzar un encargo (tarjetas encadenadas en el tablero del canal), ejecutar sus etapas con
# un ejecutor falso, abrir la puerta al acabar, decidir, deshacer, firmar y lo que hace el notario
# (aprobar, elegir, rehacer con lo pedido, lanzar la pipeline siguiente o un script del canal, descartar).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" FALSO_EJECUCIONES="$T/ejecuciones" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
C="python3 $P/hyt_canales.py"; EN="python3 $P/hyt_encargos.py"; PU="python3 $P/hyt_puertas.py"
K="$HERMES_YT_HOME/canales/demo"
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }
ultima() { tail -1; }
etapas() { local e; for e in "${@:2}"; do bash "$ROOT/etapa.sh" demo "$1" "$e" | tail -1; done; }   # etapas <encargo> <etapa>…

$C alta demo "Canal Demo" "Persona Ejemplo" >/dev/null
$C config demo pilares '[{"id":"oficio","nombre":"El oficio","tipo":"pilar"}]' >/dev/null
$C config demo prohibidas '["sin duda","en el mundo actual"]' >/dev/null
$C config demo excluido '[{"nombre":"precio","patron":"[0-9]+ ?euros","grave":true},"ofertas"]' >/dev/null
$C config demo nombres_vetados '["Nombre Reservado Uno","Nombre Reservado Dos"]' >/dev/null
echo '{"max_decisiones": 0}' > "$HERMES_YT_HOME/yt.json"   # el tope de decisiones pendientes se prueba aparte, abajo
echo "{\"ana\":{\"nombre\":\"Ana\",\"medios\":{\"telegram\":\"111\",\"local\":\"$(id -un)\"},\"canales\":[\"*\"]},\"luis\":{\"nombre\":\"Luis\",\"medios\":{\"telegram\":\"222\"},\"canales\":[\"otro\"]}}" > "$HERMES_YT_HOME/aprobadores.json"

# Pipelines de prueba, del propio canal: aquí se prueba el mecanismo (tarjetas, etapas, puertas, rehacer, vueltas,
# continuación), no el detalle de las pipelines de producción.
mkdir -p "$K/extensiones/pipelines" "$K/extensiones/skills/nota-propia"; echo "# propia" > "$K/extensiones/skills/nota-propia/SKILL.md"
cat > "$K/extensiones/pipelines/pieza.json" <<'J'
{"id":"pieza","nombre":"Pieza","nueva_pieza":true,"parametros":{"tema":"De qué va","pilar":"Su pilar"},"etapas":[
  {"id":"documentar","titulo":"Documentar: {tema}","perfil":"yt-investigador","skill":"documentar","ejecutor":"hermes","salida":"material.md"},
  {"id":"escribir","titulo":"Escribir: {tema}","perfil":"yt-guionista","skill":"escribir-guion","ejecutor":"claude","salida":"guion.md"},
  {"id":"verificar","titulo":"Verificar: {tema}","perfil":"yt-verificador","skill":"verificar","ejecutor":"hermes","salida":"verificacion.json","si_cambios":"escribir"},
  {"id":"cierre","titulo":"Cierre: {tema}","perfil":"yt-editor-jefe","skill":"cierre","ejecutor":"hermes","salida":"cierre.json"}],
 "puerta":{"tipo":"revision","al_aprobar":"nada","rehacer":"escribir"}}
J
cat > "$K/extensiones/pipelines/con-puerta.json" <<'J'
{"id":"con-puerta","nombre":"Nota con puerta","etapas":[{"id":"nota","titulo":"Nota","perfil":"yt-guionista","skill":"nota-propia","salida":"nota.md"}],
 "puerta":{"tipo":"revision","al_aprobar":"nada"}}
J
cat > "$K/extensiones/pipelines/elegir.json" <<'J'
{"id":"elegir","nombre":"Elegir entre candidatos","etapas":[
  {"id":"generar","titulo":"Generar","perfil":"yt-estratega","skill":"generar-temas","salida":"candidatos.json"},
  {"id":"puntuar","titulo":"Puntuar","perfil":"yt-espectador","skill":"puntuar-temas","salida":"puntuacion.json"}],
 "puerta":{"tipo":"elegir-temas","al_aprobar":"nada","rehacer":"generar"}}
J
cat > "$K/extensiones/pipelines/primera.json" <<'J'
{"id":"primera","nombre":"Primera","parametros":{"tema":"De qué va","pilar":"Su pilar"},"etapas":[
  {"id":"angulo","titulo":"Ángulo: {tema}","perfil":"yt-estratega","skill":"angulo","salida":"brief.json"},
  {"id":"titular","titulo":"Títulos: {tema}","perfil":"yt-titulador","skill":"titular","salida":"titulos.json"}],
 "puerta":{"tipo":"elegir-titulo","al_aprobar":"pipeline:pieza","rehacer":"titular"}}
J

# ── lanzar ──
no "una pieza sin tema no se lanza" "$EN lanzar demo pieza --param pilar=oficio"
no "un parámetro que no existe no se lanza" "$EN lanzar demo pieza --param tema=x --param pilar=oficio --param color=rojo"
si "en seco no crea nada" "$EN lanzar demo pieza --param tema='Qué es X' --param pilar=oficio --seco && [ ! -d $K/encargos ]"
R=$($EN lanzar demo pieza --param tema='Qué es X' --param pilar=oficio --quien ana)
EID=$(echo "$R" | jq -r .encargo)
D="$K/encargos/$EID"
si "lanzar crea el encargo, con su canal" "jq -e '.canal == \"demo\" and .pipeline == \"pieza\" and .estado == \"en-curso\"' $D/encargo.json"
si "crea el tablero del canal" "grep -q 'kanban boards create demo' $FALSO_LLAMADAS"
si "4 tarjetas encadenadas para la estación" "[ \$(grep -c 'kanban --board demo create' $FALSO_LLAMADAS) = 4 ] && [ \$(grep -c -- '--parent' $FALSO_LLAMADAS) = 3 ] && grep -q 'assignee yt-estacion' $FALSO_LLAMADAS"
si "el cuerpo de la tarjeta es «Ejecuta: etapa.sh»" "grep -q 'Ejecuta: bash .*etapa.sh demo $EID documentar' $FALSO_LLAMADAS"
si "idempotente por etapa" "grep -q -- '--idempotency-key $EID-escribir' $FALSO_LLAMADAS"
si "el brief lleva lo pedido" "grep -q 'Qué es X' $D/brief.md && grep -q 'Canal: demo' $D/brief.md"
si "queda en encargos.jsonl como vídeo nuevo" "grep -q '\"nueva_pieza\": true' $K/encargos.jsonl"
si "el mismo trabajo en marcha no se lanza dos veces" "$EN lanzar demo pieza --param tema='Qué es X' --param pilar=oficio | jq -e '.duplicado and .encargo == \"$EID\"'"

# ── etapas ──
r=$(etapas "$EID" documentar)
si "una etapa sale done" "echo '$r' | jq -e '.outcome == \"done\"'"
si "deja su salida y el contexto del canal" "[ -f $D/material.md ] && grep -q '^# Canal: Canal Demo' $D/contexto-canal.md"
python3 - "$D/contexto-canal.md" "$D/.estado/ultimo-prompt.txt" "$HERMES_YT_HOME" "$ROOT" <<'PY' && ok "contexto-canal.md: identidad, pilares, reglas una por línea, listas, permite y rutas; los nombres vetados no se enumeran" || bad "contexto del canal"
import sys
c, prompt, home, root = open(sys.argv[1]).read(), open(sys.argv[2]).read(), sys.argv[3], sys.argv[4]
for trozo in ("- Nombre corto (para las herramientas: --canal): demo", "- Nombre: Canal Demo", "- Presenta: Persona Ejemplo",
              "- Idioma: es-ES", "- Pilares: El oficio (oficio, pilar)", "- Formatos: sin definir",
              "- titulo_max: 55", "- minutos: [13, 15]", "- reenganches: 2",
              "## Expresiones prohibidas\n- sin duda\n- en el mundo actual",
              "## Contenido excluido (no entra en ningún resultado)\n- precio (patrón: [0-9]+ ?euros)\n- ofertas",
              "Nombres vetados: 2", "- promesas_empleo: no",
              f"{home}/canales/demo/wiki", f"{home}/canales/demo/fuentes", f"{home}/canales/demo/inventario.json",
              f"{root}/referencias"):
    assert trozo in c, trozo
assert "Nombre Reservado" not in c and "Cierres prohibidos" not in c     # las listas vacías no ocupan
assert sum(1 for l in c.splitlines() if l.startswith("- ") and l[2:].split(":")[0] in
           ("titulo_max", "titulos_internos", "titulos_presentados", "miniaturas", "ppm", "ppm_medido", "minutos",
            "intro_max_palabras", "promesa_extra_palabras", "rondas_max", "temas_por_pilar", "reenganches")) == 12
for trozo in ("for a YouTube channel", "Stage: documentar — Documentar: Qué es X", "Skill to follow: documentar",
              "read brief.md and contexto-canal.md first", "Write your result to: material.md", "(es-ES)",
              "Do NOT publish or upload anything", "do NOT contact anyone", "do NOT change the channel's\nconfiguration",
              "do not invent"):
    assert trozo in prompt, trozo
assert "website" not in prompt
PY
si "el modelo de la etapa llega al ejecutor (documentar: en hermes sin proveedor, vacío)" "grep -q '^documentar||yt-investigador|documentar' $FALSO_EJECUCIONES"
r=$(etapas "$EID" escribir)
si "escribir va a Claude con Opus y con la ruta de su skill" "grep -q '^escribir|opus|yt-guionista|escribir-guion' $FALSO_EJECUCIONES && grep -q 'read $ROOT/skills/escribir-guion/SKILL.md' $D/.estado/ultimo-prompt.txt"
si "la etapa ve lo que dejaron las anteriores" "grep -q 'Earlier stages left: material.md (documentar)\$' $D/.estado/ultimo-prompt.txt"
r=$(FALSO_MODO=sinsalida etapas "$EID" verificar)
si "done sin su salida es un fallo" "echo '$r' | jq -e '.outcome == \"failed\" and (.reason | test(\"verificacion.json\"))'"
si "el encargo queda parado" "jq -e '.estado == \"parado\"' $D/encargo.json"
si "etapas.jsonl lo apunta" "[ \$(wc -l < $K/etapas.jsonl) = 3 ] && tail -1 $K/etapas.jsonl | jq -e '.etapa == \"verificar\" and .resultado == \"failed\"'"
no "una etapa que no es del encargo" "bash $ROOT/etapa.sh demo $EID inventada | tail -1 | jq -e '.outcome == \"done\"'"
si "un ejecutor que falla deja la etapa fallida con su motivo" "FALSO_MODO=falla bash $ROOT/etapa.sh demo $EID verificar | tail -1 | jq -e '.outcome == \"failed\" and .reason == \"algo falló\"'"
etapas "$EID" verificar >/dev/null
si "una salida .json del ejecutor es JSON válido con su veredicto" "jq -e '.veredicto == \"APROBADO\"' $D/verificacion.json"
r=$(etapas "$EID" cierre)
GID=$(echo "$r" | jq -r '.puerta // empty')
si "la última etapa abre la puerta de revisión" "[ -n '$GID' ] && $PU ver $GID | jq -e '.tipo == \"revision\" and .estado == \"abierta\" and .canal == \"demo\" and .rehacer == \"escribir\" and .papel == \"\"'"
si "con sus tres opciones: aprobar, rehacer y rechazar" "$PU ver $GID | jq -e '[.opciones[] | .verbo + \":\" + .etiqueta + \":\" + ((.texto // false) | tostring)] == [\"acepto:✅ Aprobar:false\", \"cambios:✏️ Rehacer:true\", \"rechazo:🗑 Rechazar:true\"]'"
si "el texto de la puerta lleva los parámetros y la salida final" "$PU ver $GID | jq -e '(.texto | test(\"tema: Qué es X\")) and (.texto | test(\"cierre.json\")) and (.titulo | test(\"📝 Pieza · Canal Demo\"))'"
si "el encargo pasa a «en puerta»" "jq -e '.estado == \"en-puerta\" and .puerta_id == \"$GID\"' $D/encargo.json"
no "no abre dos puertas para el mismo encargo" "$PU abrir demo $EID"
$C config demo politicas.pausado true >/dev/null
si "en pausa, una etapa espera (scheduled)" "bash $ROOT/etapa.sh demo $EID documentar | tail -1 | jq -e '.outcome == \"scheduled\"'"
no "y no se lanza nada nuevo" "$EN lanzar demo con-puerta"
$C config demo politicas.pausado false >/dev/null
touch "$HERMES_YT_HOME/pausa"
si "con la pausa global, también espera" "bash $ROOT/etapa.sh demo $EID documentar | tail -1 | jq -e '.outcome == \"scheduled\" and .reason == \"en pausa\"'"
rm "$HERMES_YT_HOME/pausa"

# ── decidir, deshacer, firmar ──
cat > "$T/py" <<'PY'
import importlib.util, json, sys, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_puertas", Path(os.environ["P"]) / "hyt_puertas.py")
PU = importlib.util.module_from_spec(spec); sys.modules["hyt_puertas"] = PU; spec.loader.exec_module(PU)
def rechaza(f):
    try: f(); return False
    except PU.Rechazo: return True
PY
export P
python3 - "$GID" <<PY && ok "decidir: autorización por medio y por canal, texto obligatorio, deshacer" || bad "decidir"
exec(open("$T/py").read())
g = sys.argv[1]
assert rechaza(lambda: PU.decidir(g, "acepto", "", "ana", "telegram", "999"))       # otra identidad
assert rechaza(lambda: PU.decidir(g, "acepto", "", "ana", "dashboard", "111"))      # su identidad es de otro medio
assert rechaza(lambda: PU.decidir(g, "acepto", "", "luis", "telegram", "222"))      # no decide en este canal
assert rechaza(lambda: PU.decidir(g, "cambios", "", "ana", "telegram", "111"))      # rehacer sin decir qué
assert rechaza(lambda: PU.decidir(g, "rechazo", "  ", "ana", "telegram", "111"))    # rechazar sin motivo
assert rechaza(lambda: PU.decidir(g, "algunas", "1", "ana", "telegram", "111"))     # opción que no es de este tipo
assert rechaza(lambda: PU.decidir(g, "borrar", "", "ana", "telegram", "111"))       # opción que no existe
p = PU.decidir(g, "cambios", "Más ejemplos", "ana", "telegram", "111")
assert p["decision"]["actor"] == {"persona": "ana", "medio": "telegram", "id": "111"}, p["decision"]
assert rechaza(lambda: PU.decidir(g, "acepto", "", "ana", "telegram", "111"))       # ya decidida
assert rechaza(lambda: PU.deshacer(g, "luis"))                                      # solo quien decidió
PU.deshacer(g, "ana")
assert PU.leer(g)["estado"] == "abierta"
assert rechaza(lambda: PU.marcar(g, estado="firmada")) and rechaza(lambda: PU.marcar(g, papel="x"))   # un medio no decide
assert PU.marcar(g, telegram=[{"chat": 1, "msg": 2}])["telegram"] == [{"chat": 1, "msg": 2}]
PY
python3 - "$GID" <<PY && ok "rehacer: el notario rehace desde escribir con lo pedido y lo firma con el medio" || bad "rehacer"
exec(open("$T/py").read())
g = sys.argv[1]
PU.decidir(g, "cambios", "Más ejemplos, menos jerga", "ana", "telegram", "111")
p = PU.firmar(g)
assert p["estado"] == "firmada" and p["resultado"] == "se rehace desde escribir", p
assert "Ana (telegram)" == p["firma"], p["firma"]
assert PU.firmar(g)["firmada"] == p["firmada"]                                      # idempotente
d = Path(os.environ["HERMES_YT_HOME"]) / "canales/demo/encargos"
enc = json.load(open(next(d.glob("pieza-*/encargo.json"))))
assert enc["estado"] == "en-curso" and enc["rondas"] == 1 and "puerta_id" not in enc
assert "Más ejemplos" in (next(d.glob("pieza-*")) / ".estado/feedback-escribir.txt").read_text()
PY
si "rehacer archiva las 3 tarjetas viejas" "[ \$(grep -c 'kanban --board demo archive' $FALSO_LLAMADAS) = 3 ]"
si "rehacer crea 3 tarjetas nuevas (escribir → cierre)" "[ \$(grep -c -- '--idempotency-key $EID-.*-r1' $FALSO_LLAMADAS) = 3 ]"
si "lo que pidió la persona llega al prompt de escribir" "bash $ROOT/etapa.sh demo $EID escribir >/dev/null && grep -q 'What the person asked to change' $D/.estado/ultimo-prompt.txt && grep -q 'Más ejemplos, menos jerga' $D/.estado/ultimo-prompt.txt"
etapas "$EID" verificar >/dev/null
GID2=$(etapas "$EID" cierre | jq -r '.puerta // empty')
si "segunda ronda: nueva puerta" "[ -n '$GID2' ] && [ '$GID2' != '$GID' ]"
si "aprobar cierra el encargo; el notario lo firma y lo registra" "$PU decidir-local $GID2 acepto | grep -q 'Firmada por Ana (local): aprobado' && jq -e '.estado == \"cerrado\"' $D/encargo.json"
si "puertas.jsonl registra las dos firmas, con su medio" "[ \$(wc -l < $K/puertas.jsonl) = 2 ] && head -1 $K/puertas.jsonl | jq -e '.verbo == \"cambios\" and .medio == \"telegram\" and .tipo == \"revision\" and .texto == \"Más ejemplos, menos jerga\"' && tail -1 $K/puertas.jsonl | jq -e '.verbo == \"acepto\" and .medio == \"local\" and .resultado == \"aprobado\"'"
no "una puerta firmada ya no se decide" "$PU decidir-local $GID2 rechazo 'tarde'"
si "listar: sin pendientes; con --todas, las firmadas" "[ -z \"\$($PU listar)\" ] && [ \$($PU listar --todas | wc -l) = 2 ]"

# ── una puerta se abre aunque aprobar no lance nada; sin puerta, el encargo queda hecho ──
R=$($EN lanzar demo con-puerta --quien ana); A=$(echo "$R" | jq -r .encargo)
GA=$(etapas "$A" nota | jq -r '.puerta // empty')
si "una pipeline con puerta se para en ella aunque aprobar no lance nada (al_aprobar: nada)" "[ -n '$GA' ] && jq -e '.estado == \"en-puerta\"' $K/encargos/$A/encargo.json && $PU ver $GA | jq -e '.tipo == \"revision\" and .al_aprobar == \"nada\"'"
si "mientras espera en su puerta, no se lanza otro igual" "$EN lanzar demo con-puerta | jq -e '.duplicado'"
si "rechazar deja el encargo descartado" "$PU decidir-local $GA rechazo 'Faltan fuentes' | grep -q 'descartado' && jq -e '.estado == \"descartado\"' $K/encargos/$A/encargo.json"
si "y ya se puede volver a lanzar" "$EN lanzar demo con-puerta | jq -e '.duplicado | not'"
cat > "$K/extensiones/pipelines/suelta.json" <<'J'
{"id":"suelta","nombre":"Nota suelta","etapas":[{"id":"nota","titulo":"Nota","perfil":"yt-guionista","skill":"nota-propia","ejecutor":"claude","salida":"nota.md"}]}
J
S=$($EN lanzar demo suelta | jq -r .encargo)
GS=$(etapas "$S" nota | jq -r '.puerta // empty')
si "una pipeline sin puerta no abre ninguna y queda hecha" "[ -z '$GS' ] && jq -e '.estado == \"hecho\" and .informe' $K/encargos/$S/encargo.json"
si "Claude recibe la ruta de la skill propia del canal" "grep -q 'extensiones/skills/nota-propia/SKILL.md' $K/encargos/$S/.estado/ultimo-prompt.txt"
cat > "$K/extensiones/pipelines/sin-skill.json" <<'J'
{"id":"sin-skill","nombre":"Sin skill","etapas":[{"id":"nota","titulo":"Nota","perfil":"yt-guionista","skill":"no-existe","ejecutor":"claude","salida":"nota.md"}]}
J
S2=$($EN lanzar demo sin-skill | jq -r .encargo)
si "con Claude, una skill que no existe es un fallo claro" "etapas $S2 nota | jq -e '.outcome == \"failed\" and (.reason | test(\"no-existe\"))'"

# ── elegir: temas y título; la elección viaja a la pipeline siguiente ──
PR=$($EN lanzar demo elegir | jq -r .encargo)
etapas "$PR" generar >/dev/null; GP=$(etapas "$PR" puntuar | jq -r '.puerta // empty')
si "la puerta de elegir temas, con sus opciones" "$PU ver $GP | jq -e '.tipo == \"elegir-temas\" and ([.opciones[] | .verbo + \":\" + .etiqueta + \":\" + ((.texto // false) | tostring)] == [\"algunas:✅ Elegir:true\", \"cambios:🔁 Otra propuesta:false\", \"rechazo:🗑 Ninguno:true\"])'"
no "elegir sin decir qué se elige, no" "$PU decidir-local $GP algunas"
no "en una puerta de elegir no hay «aprobar» a secas" "$PU decidir-local $GP acepto"
si "«otra propuesta» no necesita texto y vuelve a generar" "$PU decidir-local $GP cambios | grep -q 'se rehace desde generar' && jq -e '.estado == \"en-curso\" and .rondas == 1' $K/encargos/$PR/encargo.json && [ ! -f $K/encargos/$PR/.estado/feedback-generar.txt ]"
etapas "$PR" generar >/dev/null; GP2=$(etapas "$PR" puntuar | jq -r '.puerta // empty')
si "elegir guarda la elección en el encargo y lo cierra" "$PU decidir-local $GP2 algunas 'Los temas 1 y 3' | grep -q aprobado && grep -q 'Los temas 1 y 3' $K/encargos/$PR/eleccion.md && jq -e '.estado == \"cerrado\" and .eleccion == \"Los temas 1 y 3\"' $K/encargos/$PR/encargo.json"
TM=$($EN lanzar demo primera --param tema='Qué es X' --param pilar=oficio | jq -r .encargo)
etapas "$TM" angulo >/dev/null; GT=$(etapas "$TM" titular | jq -r '.puerta // empty')
si "la puerta de elegir título sabe qué pipeline sigue" "$PU ver $GT | jq -e '.tipo == \"elegir-titulo\" and .al_aprobar == \"pipeline:pieza\" and .rehacer == \"titular\"'"
$C config demo politicas.tope_semanal 1 >/dev/null   # ya hay una pieza nueva esta semana: lanzar otra a mano no se puede…
no "con el tope semanal alcanzado, una pieza nueva no se lanza a mano" "$EN lanzar demo pieza --param tema='Otro tema' --param pilar=oficio"
$PU decidir-local $GT algunas 'Título 2 con la miniatura B' > "$T/dl.out" 2>&1
si "…pero elegir título lanza la pipeline siguiente (la continuación ya la aprobó una persona)" "grep -q 'Firmada por Ana (local): lanzado pieza-' $T/dl.out"
G2=$(ls $K/encargos | grep '^pieza-' | grep -v "^$EID\$" | head -1)
si "la continuación hereda parámetros, salidas y la elección" "[ -n '$G2' ] && jq -e '.params == {\"tema\": \"Qué es X\", \"pilar\": \"oficio\"} and .origen == \"$TM\" and (.heredados | index(\"titulos.json\")) and (.heredados | index(\"eleccion.md\"))' $K/encargos/$G2/encargo.json && grep -q 'Título 2 con la miniatura B' $K/encargos/$G2/eleccion.md && [ -f $K/encargos/$G2/brief-origen.md ]"
si "y cuenta como vídeo nuevo (su origen no lo era)" "tail -1 $K/encargos.jsonl | jq -e '.nueva_pieza == true and .origen == \"$TM\"'"
etapas "$G2" documentar >/dev/null
si "la etapa ve lo heredado como previo" "grep -q 'eleccion.md (from $TM)' $K/encargos/$G2/.estado/ultimo-prompt.txt && grep -q 'brief.json (from $TM)' $K/encargos/$G2/.estado/ultimo-prompt.txt"
$C config demo politicas.tope_semanal 0 >/dev/null

# ── script del canal al aprobar ──
cat > "$K/extensiones/pipelines/con-script.json" <<'J'
{"id":"con-script","nombre":"Con script","parametros":{"n":"vuelta"},"etapas":[{"id":"nota","titulo":"Nota {n}","perfil":"yt-guionista","skill":"nota-propia","salida":"nota.md"}],
 "puerta":{"tipo":"decision","al_aprobar":"script:exportar.sh {encargo} extra"}}
J
printf '#!/usr/bin/env bash\necho "$1 $2 $HYT_FIRMA" > "$HERMES_YT_HOME/script-hecho"\n' > "$K/extensiones/exportar.sh"
CS=$($EN lanzar demo con-script --param n=1 | jq -r .encargo); GC=$(etapas "$CS" nota | jq -r '.puerta // empty')
si "script: lanza el script del canal con el encargo y la firma" "$PU decidir-local $GC acepto | grep -q 'lanzado exportar.sh' && sleep 1 && grep -q '^$CS extra Ana (local)' $HERMES_YT_HOME/script-hecho"
cat > "$K/extensiones/pipelines/script-fuera.json" <<'J'
{"id":"script-fuera","nombre":"Script que no existe","etapas":[{"id":"nota","titulo":"Nota","perfil":"yt-guionista","skill":"nota-propia","salida":"nota.md"}],
 "puerta":{"tipo":"decision","al_aprobar":"script:no-esta.sh"}}
J
SF=$($EN lanzar demo script-fuera | jq -r .encargo); GF=$(etapas "$SF" nota | jq -r '.puerta // empty')
si "si el script no existe, la puerta queda en error visible (no firmada)" "! $PU decidir-local $GF acepto && $PU ver $GF | jq -e '.estado == \"error\" and (.error | test(\"no-esta.sh\"))'"

# ── aviso grave: no se aprueba (solo rehacer o rechazar); --forzar desde local, con motivo y registrado ──
J1=$($EN lanzar demo con-script --param n=2 | jq -r .encargo); GJ=$(etapas "$J1" nota | jq -r '.puerta // empty')
python3 - "$GJ" <<PY && ok "con un aviso grave no se aprueba, y la opción de aprobar no se ofrece" || bad "aviso grave"
exec(open("$T/py").read())
g = sys.argv[1]
p = PU.leer(g); p["revision"] = {"avisos": [{"grave": True, "codigo": "x", "texto": "x"}], "graves": 1}; PU.B.escribir(PU.indice(g), p)
assert rechaza(lambda: PU.decidir(g, "acepto", "", "ana", "telegram", "111"))
assert rechaza(lambda: PU.decidir(g, "acepto", "", "ana", "telegram", "111", {"forzado": "porque sí"}))   # forzar, solo en local
assert [o["verbo"] for o in PU.opciones_vigentes(PU.leer(g))] == ["cambios", "rechazo"]
assert PU.leer(g)["estado"] == "abierta"
PY
no "decidir-local sin --forzar tampoco aprueba" "$PU decidir-local $GJ acepto"
si "con --forzar y motivo sí, y queda escrito" "$PU decidir-local $GJ acepto --forzar 'lo reviso yo' && tail -1 $K/puertas.jsonl | jq -e '.forzado == \"lo reviso yo\"'"

# ── la verificación pide cambios: una vuelta automática a escribir; la segunda vez sigue hasta la puerta ──
EV=$($EN lanzar demo pieza --param tema='Vuelta' --param pilar=oficio | jq -r .encargo); DV=$K/encargos/$EV
etapas "$EV" documentar escribir >/dev/null
OUT=$(FALSO_MODO=cambios etapas "$EV" verificar)
si "CAMBIOS en la verificación: la tarjeta no sigue y el encargo queda en-vuelta" "echo '$OUT' | jq -e '.outcome == \"failed\" and .vuelta == \"escribir\"' && jq -e '.estado == \"en-vuelta\" and .vuelta_pendiente.desde == \"escribir\"' $DV/encargo.json && jq -e '.veredicto == \"CAMBIOS\"' $DV/verificacion-1.json"
si "etapas.jsonl lo apunta como «cambios», no como fallo" "tail -1 $K/etapas.jsonl | jq -e '.resultado == \"cambios\"'"
si "hyt vueltas la lanza: tarjetas nuevas desde escribir" "python3 $P/hyt_cli.py vueltas | grep -q '$EV' && jq -e '.estado == \"en-curso\" and (.vuelta_pendiente | not)' $DV/encargo.json && grep -q -- '--idempotency-key $EV-escribir-r1' $FALSO_LLAMADAS"
si "lo que pidió la verificación va aparte y llega a quien escribe" "[ -f $DV/.estado/feedback-verificacion-escribir.txt ] && [ ! -f $DV/.estado/feedback-escribir.txt ] && bash $ROOT/etapa.sh demo $EV escribir >/dev/null && grep -q 'asked for changes' $DV/.estado/ultimo-prompt.txt && grep -q 'corregir la cifra' $DV/.estado/ultimo-prompt.txt"
OUT2=$(FALSO_MODO=cambios etapas "$EV" verificar)
si "segunda vez CAMBIOS: ya no vuelve, sigue" "echo '$OUT2' | jq -e '.outcome == \"done\"' && jq -e '.estado == \"en-curso\" and .vueltas_verificacion == 1' $DV/encargo.json"
GV=$(etapas "$EV" cierre | jq -r '.puerta // empty')
si "y llega a su puerta" "[ -n '$GV' ] && $PU ver $GV | jq -e '.estado == \"abierta\"'"

# ── tope de decisiones pendientes por canal ──
$C alta otro "Otro Canal" "Otra Persona" >/dev/null
echo '{"max_decisiones": 3}' > "$HERMES_YT_HOME/yt.json"
for n in 1 2 3; do $EN lanzar otro guion --param tema="Tema $n" --param pilar=p >/dev/null; done   # la de producción
si "guion (la pipeline de producción) lanza una tarjeta por etapa" "[ \$(grep -c 'kanban --board otro create' $FALSO_LLAMADAS) = \$((3 * \$(jq '.etapas | length' $ROOT/pipelines/guion.json))) ]"
no "con 3 decisiones pendientes en un canal, no se lanza otra" "$EN lanzar otro guion --param tema='Tema 4' --param pilar=p"
si "una persona puede pedir la excepción" "$EN lanzar otro guion --param tema='Tema 4' --param pilar=p --excepcion"
si "y el tope se cambia en yt.json (max_decisiones)" "echo '{\"max_decisiones\": 9}' > $HERMES_YT_HOME/yt.json && $EN lanzar otro guion --param tema='Tema 5' --param pilar=p"
exit $fail
