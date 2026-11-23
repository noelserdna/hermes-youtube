#!/usr/bin/env bash
# Modelos por etapa (perfil → global → canal; formato por ejecutor y proveedor) y pipelines (validación, plan por
# capacidades del canal, políticas: pausa, tope semanal, excepción).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HOME="$T/casa"; mkdir -p "$HOME/.hermes/profiles/yt-guionista" "$HOME/.hermes/profiles/yt-gpt"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
C="python3 $P/hyt_canales.py"; M="python3 $P/hyt_modelos.py"; PL="python3 $P/hyt_pipelines.py"
K="$HERMES_YT_HOME/canales"
igual() { [ "$2" = "$3" ] && ok "$1" || bad "$1 (salió «$2», esperaba «$3»)"; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }

$C alta demo "Canal Demo" "Persona Ejemplo" >/dev/null
printf 'model:\n  default: claude-sonnet-5-5\n  provider: anthropic\n' > "$HOME/.hermes/profiles/yt-guionista/config.yaml"
printf 'model:\n  provider: openai-codex\n  default: gpt-6-sol\n' > "$HOME/.hermes/profiles/yt-gpt/config.yaml"
mkdir -p "$HOME/.hermes/profiles/yt-comentado"
printf 'model:\n  # Default model\n  default: "claude-sonnet-5-5"\n\n  # Inference provider:\n  #   "auto" - x\n  provider: "anthropic"\nterminal:\n  provider: otro\n' > "$HOME/.hermes/profiles/yt-comentado/config.yaml"

# ── modelos ──
igual "equilibrado: escribir con Opus en Claude Code" "$($M para escribir claude)" opus
igual "equilibrado: verificar con Sonnet" "$($M para verificar claude)" sonnet
igual "etapa desconocida: el ligero" "$($M para inventada claude)" sonnet
igual "Hermes con Anthropic directo: id de Anthropic" "$($M para escribir hermes --perfil yt-guionista)" claude-opus-5-5
igual "Hermes con OpenRouter: id de OpenRouter" "$($M para verificar hermes --proveedor openrouter)" anthropic/claude-sonnet-5.5
igual "config con comentarios y líneas en blanco" "$($M para escribir hermes --perfil yt-comentado)" claude-opus-5-5
igual "Hermes con ChatGPT: no fuerza modelo" "$($M para escribir hermes --perfil yt-gpt)" ""
si "toda etapa de las pipelines del plugin tiene modelo propio (está en ETAPAS_MODELO), y no sobra ninguna" \
   "python3 -c \"import json, glob, sys; sys.path.insert(0, '$P'); import hyt_modelos as m; assert sorted(e for e, _ in m.ETAPAS_MODELO) == sorted({s['id'] for f in glob.glob('$ROOT/pipelines/*.json') for s in json.load(open(f))['etapas']})\""
si "las etapas que piensan van con Opus y existen" "python3 -c \"import sys; sys.path.insert(0, '$P'); import hyt_modelos as m; e = dict(m.ETAPAS_MODELO); assert set(m.PIENSAN) <= set(e); assert all(m.PERFILES['equilibrado'][x] == 'opus' for x in m.PIENSAN); assert {'generar', 'angulo', 'titular', 'escaleta', 'escribir', 'voz', 'cierre', 'perfil'} <= set(m.PIENSAN)\""
si "perfil calidad" "$M perfil calidad"
igual "calidad: verificar con Opus" "$($M para verificar claude)" opus
si "cambio global de una etapa" "$M poner verificar fable"
igual "el global manda sobre el perfil" "$($M para verificar claude)" fable
si "cambio del canal" "$M poner verificar sonnet --canal demo"
igual "el del canal manda sobre el global" "$($M para verificar claude --canal demo)" sonnet
igual "otro canal sigue con el global" "$($M para verificar claude)" fable
no "Haiku no en una etapa de juicio" "$M poner escribir haiku"
no "modelo con caracteres raros" "$M poner verificar 'rm -rf'"
si "quitar el cambio del canal" "$M poner verificar - --canal demo"
igual "sin cambio del canal vuelve al global" "$($M para verificar claude --canal demo)" fable
igual "id completo de OpenRouter a Claude Code" "$($M poner describir anthropic/claude-opus-5.5 >/dev/null; $M para describir claude)" claude-opus-5-5
si "la configuración global vive en yt.json" "jq -e '.perfil_modelos == \"calidad\" and .modelos.verificar == \"fable\"' $HERMES_YT_HOME/yt.json"

# ── pipelines ──
si "todas las pipelines del plugin son válidas" "$PL validar-todas"
igual "las seis pipelines de partida" "$($PL listar | awk '{print $1}' | tr '\n' ' ')" "guion-investigado guion inventario perfil-voz propuesta titulo-miniatura "
si "el plan de guion: una línea por etapa y su cadena de puertas" "[ \$($PL plan guion --canal demo | grep -c '^▶') = \$(jq '.etapas | length' $ROOT/pipelines/guion.json) ] && [ \$($PL plan guion --canal demo | grep -c '^🚪') = 3 ] && $PL plan guion --canal demo | grep -q '🚪 revision (marketing)'"
si "cada pipeline acaba en su puerta o en su cadena, con el papel que decide" "python3 -c \"
import sys; sys.path.insert(0, '$P'); import hyt_pipelines as m
L = m.listar()
tipos = {pid: [(g['tipo'], g.get('papel', '')) for g in m.puertas_de(p)] for pid, p in L.items()}
assert all(papel == '' for _, papel in tipos.pop('inventario'))      # el inventario, con puerta o sin ella, no pide papel
cadena = [('revision', 'marketing'), ('datos', 'datos'), ('revision-final', 'presentador')]
assert tipos == {'guion': cadena, 'guion-investigado': cadena,
                 'perfil-voz': [('voz', 'presentador')], 'propuesta': [('elegir-temas', 'marketing')], 'titulo-miniatura': [('elegir-titulo', 'marketing')]}, tipos
assert m.puertas_de(L['guion'])[1]['si_vacio'] == 'saltar' and 'puerta' not in L['guion']
assert m.al_aprobar_de(L['titulo-miniatura']) == 'pipeline:guion+guion-investigado' and m.al_aprobar_de(L['guion']) == 'nada' and m.rehacer_de(L['guion']) == 'ajustar'
assert m.listar()['guion']['nueva_pieza'] is True and m.puertas_de({}) == [] and m.puertas_de(None) == []\""
mkdir -p "$K/demo/extensiones/pipelines"
cat > "$K/demo/extensiones/pipelines/con-requisito.json" <<'J'
{"id":"con-requisito","nombre":"Con requisito","requiere":["inventario"],"etapas":[
  {"id":"uno","titulo":"Uno","perfil":"yt-analista","skill":"inventario"},
  {"id":"dos","titulo":"Dos","perfil":"yt-doble","skill":"voz","requiere":["voz"]}]}
J
no "una pipeline que requiere inventario no se planifica sin él" "$PL plan con-requisito --canal demo"
echo '{}' > "$K/demo/inventario.json"
si "con inventario sí, y la etapa que requiere voz se salta" "$PL plan con-requisito --canal demo | grep -q 'dos.*se salta: falta voz'"
mkdir -p "$K/demo/wiki/concepts"; echo "# Voz" > "$K/demo/wiki/concepts/voz.md"
si "con voz, la etapa corre" "$PL plan con-requisito --canal demo | grep -q '▶ dos'"
cat > "$K/demo/extensiones/pipelines/inventario.json" <<'J'
{"id":"inventario","nombre":"Inventario propio","etapas":[{"id":"inventario","titulo":"Inventario propio","perfil":"yt-analista","skill":"inventario-propio","ejecutor":"hermes"}]}
J
si "la pipeline del canal sustituye a la del plugin" "$PL ver inventario --canal demo | grep -q inventario-propio"
si "otros canales ven la del plugin" "$C alta otro 'Otro Canal' 'Otra Persona' >/dev/null; $PL ver inventario --canal otro | grep -q '\"skill\": \"inventario\"'"
cat > "$K/demo/extensiones/pipelines/mala.json" <<'J'
{"id":"mala","nombre":"Mala","etapas":[{"id":"x","titulo":"{nada}","perfil":"root","skill":"x y","ejecutor":"bash"}]}
J
no "una pipeline mal escrita no se planifica" "$PL plan mala --canal demo"

python3 - "$P" <<'PY' && ok "validar: perfiles, ejecutores, tipos de puerta, al_aprobar, rehacer, si_cambios y prepara" || bad "validar"
import sys
sys.path.insert(0, sys.argv[1])
import hyt_pipelines as PL
assert PL.PERFILES_ROL == ("yt-analista", "yt-estratega", "yt-espectador", "yt-titulador", "yt-miniaturista", "yt-investigador",
                           "yt-investigador-web", "yt-guionista", "yt-verificador", "yt-retencion", "yt-doble", "yt-editor-jefe")
assert PL.EJECUTORES == ("hermes", "claude")
assert PL.TIPOS_PUERTA == ("alta", "elegir-temas", "elegir-titulo", "revision", "datos", "revision-final", "voz", "decision")
def p(**k):
    base = {"id": "xx", "nombre": "x", "etapas": [{"id": "aa", "perfil": "yt-guionista", "skill": "escaleta"},
                                                  {"id": "bb", "perfil": "yt-verificador", "skill": "verificar"}]}
    return {**base, **k}
assert PL.validar(p()) == [], PL.validar(p())
for bien in ("nada", "pipeline:guion", "pipeline:guion+guion-investigado", "script:exportar.sh", "script:exportar.sh {encargo} extra"):
    assert PL.validar(p(puerta={"tipo": "revision", "al_aprobar": bien})) == [], bien
for mal in ("publicar", "gestiones", "apuntar", "instalar:x/y@abcdef1", "script:a.sh; rm -rf /", "pipeline:", "pipeline:guion+", "otra-cosa"):
    assert PL.validar(p(puerta={"tipo": "revision", "al_aprobar": mal})), mal
assert PL.validar(p(puerta={"tipo": "publicar"}))                                   # tipo que ya no existe
assert PL.validar(p(puerta={"tipo": "revision", "rehacer": "zeta"}))                # rehacer a una etapa que no es suya
assert PL.validar(p(puerta={"tipo": "revision", "rehacer": "aa"})) == []
def etapas(**k):
    return p(etapas=[{"id": "aa", "perfil": "yt-guionista", "skill": "escaleta"}, {"id": "bb", "perfil": "yt-verificador", "skill": "verificar", **k}])
assert PL.validar(etapas(si_cambios="aa")) == []
assert PL.validar(etapas(si_cambios="bb"))                                          # a sí misma o a una posterior, no
assert PL.validar(etapas(ejecutor="replay")) and PL.validar(etapas(perfil="yt-redactor"))
assert PL.validar(etapas(prepara=["resumen"])) and PL.validar(etapas(prepara=[])) == []   # solo las preparaciones conocidas
assert PL.validar(etapas(max_runtime="mucho")) and PL.validar(p(memoria={"pagina": "voz"}))
assert PL.validar(p(memoria={"pagina": "voz", "de": "perfil-voz.md"})) == []
assert PL.PREPARA and PL.TRAS and PL.validar(etapas(prepara=[PL.PREPARA[0]], tras=[PL.TRAS[0]])) == [] and PL.validar(etapas(tras=["inventado"]))
# cadena de puertas: `puertas` (con papel y si_vacio) y, a nivel de pipeline, `rehacer` y `al_aprobar`
import hyt_canales
assert PL.PAPELES == hyt_canales.ROLES and PL.SI_VACIO == ("saltar",)
cadena = [{"tipo": "revision", "papel": "marketing"}, {"tipo": "datos", "papel": "datos", "si_vacio": "saltar"}, {"tipo": "revision-final", "papel": "presentador"}]
c = p(puertas=cadena, rehacer="aa", al_aprobar="pipeline:guion")
assert PL.validar(c) == [], PL.validar(c)
assert [g["tipo"] for g in PL.puertas_de(c)] == ["revision", "datos", "revision-final"] and PL.rehacer_de(c) == "aa" and PL.al_aprobar_de(c) == "pipeline:guion"
mixta = p(puertas=cadena, puerta={"tipo": "revision", "rehacer": "bb", "al_aprobar": "script:x.sh"})     # ambos: manda la cadena
assert PL.validar(mixta) == [] and len(PL.puertas_de(mixta)) == 3 and PL.rehacer_de(mixta) == "bb" and PL.al_aprobar_de(mixta) == "script:x.sh"
unica = p(puerta={"tipo": "voz", "papel": "presentador", "rehacer": "aa"})
assert PL.validar(unica) == [] and PL.puertas_de(unica) == [unica["puerta"]] and PL.rehacer_de(unica) == "aa" and PL.al_aprobar_de(unica) == "nada"
assert PL.rehacer_de(p()) == "" and PL.al_aprobar_de(None) == "nada"
for mala in (p(puertas=[]), p(puertas="revision"), p(puertas=[{"tipo": "publicar"}]), p(puertas=[{"tipo": "revision", "papel": "jefa"}]),
             p(puertas=[{"tipo": "revision", "si_vacio": "saltar"}, {"tipo": "revision-final"}]),      # si_vacio, solo en datos
             p(puertas=[{"tipo": "datos", "si_vacio": "esperar"}, {"tipo": "revision"}]),
             p(puertas=[{"tipo": "datos", "si_vacio": "saltar"}]),                                     # siempre decide alguien
             p(puerta={"tipo": "datos", "si_vacio": "saltar"}), p(puerta={"tipo": "revision", "papel": "jefa"}),
             p(puertas=cadena, rehacer="zeta"), p(puertas=cadena, al_aprobar="publicar"), p(rehacer="aa"), p(al_aprobar="pipeline:guion")):
    assert PL.validar(mala), mala
PY

python3 - "$P" <<'PY' && ok "políticas: pausa, tope semanal y excepción (sin congelación)" || bad "políticas"
import importlib.util, json, sys
from datetime import date
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_pipelines", Path(sys.argv[1]) / "hyt_pipelines.py")
PL = importlib.util.module_from_spec(spec); sys.modules["hyt_pipelines"] = PL; spec.loader.exec_module(PL)
C = PL._cargar("hyt_canales")
def rechaza(f):
    try: f(); return False
    except PL.Rechazo: return True
hoy = date(2026, 11, 14)
PL.politicas("guion", "demo", hoy=hoy)                          # sin políticas: pasa
C.config("demo", "politicas.tope_semanal", 1)
f = C.carpeta("demo") / "encargos.jsonl"
f.write_text(json.dumps({"ts": "2026-11-12T10:00:00Z", "nueva_pieza": True}) + "\n")
assert rechaza(lambda: PL.politicas("guion", "demo", hoy=hoy))
PL.politicas("propuesta", "demo", hoy=hoy)                      # lo que no es un vídeo nuevo no cuenta para el tope
PL.politicas("guion", "demo", excepcion=True, hoy=hoy)          # excepción pedida por una persona
f.write_text(json.dumps({"ts": "2026-11-01T10:00:00Z", "nueva_pieza": True}) + "\n")
PL.politicas("guion", "demo", hoy=hoy)                          # el de hace dos semanas no cuenta
f.write_text(json.dumps({"ts": "2026-11-12T10:00:00Z", "nueva_pieza": False}) + "\n")
PL.politicas("guion", "demo", hoy=hoy)                          # ni lo que no fue un vídeo nuevo
C.config("demo", "politicas.pausado", True)
assert rechaza(lambda: PL.politicas("propuesta", "demo", hoy=hoy))
assert rechaza(lambda: PL.politicas("guion", "demo", excepcion=True, hoy=hoy))   # la pausa no tiene excepción
assert "congelado_hasta" not in json.dumps(C.plantilla())
PY

# ── herencia: el canal solo dice lo que cambia; lo demás sigue al plugin ──
X="$K/demo/extensiones/pipelines"; mkdir -p "$X"
etapa() { $PL ver "$1" --canal demo | python3 -c "import json,sys;p=json.load(sys.stdin);print(' '.join(s['id']+':'+str(s.get('$3','')) for s in p['etapas'] if s['id']=='$2' or '$2'=='*'))"; }
cat > "$X/guion.json" <<'J'
{"id": "guion", "hereda": "guion", "descripcion": "propia",
 "cambia": {"escribir": {"max_runtime": "90m", "ejecutor": "claude"}},
 "añade": [{"tras_de": "verificar", "id": "extra", "titulo": "Extra", "perfil": "yt-editor-jefe", "skill": "cierre", "salida": "extra.md"}],
 "quita": ["retencion"],
 "puertas": [{"tipo": "revision", "papel": "presentador"}]}
J
igual "herencia: cambia solo esos campos" "$(etapa guion escribir max_runtime) $(etapa guion escribir ejecutor)" "escribir:90m escribir:claude"
igual "herencia: lo demás viene del plugin" "$(etapa guion escribir skill) $(etapa guion verificar skill)" "escribir:escribir-guion verificar:verificar"
igual "herencia: añade tras una etapa y quita otra" "$(etapa guion '*' id | tr ' ' '\n' | cut -d: -f1 | tr '\n' ' ')" "documentar escaleta escribir verificar extra voz ajustar describir cierre "
igual "herencia: un canal de una persona deja una sola puerta" "$($PL ver guion --canal demo | python3 -c 'import json,sys;p=json.load(sys.stdin);print(len(p["puertas"]), p["puertas"][0]["papel"], p["descripcion"], p["_hereda"], "tema" in json.dumps(p["parametros"]))')" "1 presentador propia guion True"
si "herencia: una pipeline heredada es válida" "! $PL validar-todas --canal demo | grep -q '^guion:'"
si "herencia: el plan la usa" "$PL plan guion --canal demo | grep -q extra"
igual "herencia: otro canal sigue con la del plugin" "$($C alta otro 'Otro' 'Persona Dos' >/dev/null; $PL ver guion --canal otro | python3 -c 'import json,sys;p=json.load(sys.stdin);print(len(p["etapas"]), len(p["puertas"]))')" "9 3"
echo '{"id": "guion", "hereda": "guion", "cambia": {"redactor-viejo": {"skill": "x"}}}' > "$X/guion.json"
si "herencia: nombrar una etapa que el plugin no tiene es un error" "{ $PL validar-todas --canal demo || true; } | grep -q '^guion:.*redactor-viejo'"
no "herencia: y no se puede lanzar" "$PL plan guion --canal demo"
echo '{"id": "otra", "hereda": "no-existe", "nombre": "x"}' > "$X/guion.json"
si "herencia: de una pipeline que no existe, error" "{ $PL validar-todas --canal demo || true; } | grep -q '^otra:.*no-existe'"
rm -f "$X/guion.json"
igual "el plugin lo hace todo con Hermes (Claude Code solo si el canal lo pide)" "$(python3 -c "import json,glob;print(set(s.get('ejecutor','hermes') for f in glob.glob('$ROOT/pipelines/*.json') for s in json.load(open(f))['etapas']))")" "{'hermes'}"

exit $fail
