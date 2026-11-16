#!/usr/bin/env bash
# El armazón de la revisión mecánica (registro de reglas por tipo de puerta, vacío de partida; avisos y graves; un
# aviso grave impide aprobar) y las lecciones entre canales (proponer con evidencia, reglas generales, confirmar, usar
# en otros canales, revisar tras 3 usos, wiki global).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
python3 "$P/hyt_canales.py" alta cocina "Cocina Lenta" "Marta Ejemplo" >/dev/null
for w in otro1 otro2 otro3; do python3 "$P/hyt_canales.py" alta $w "Canal $w" "Persona $w" >/dev/null; done
echo "{\"ana\":{\"nombre\":\"Ana\",\"medios\":{\"telegram\":\"111\",\"local\":\"$(id -un)\"},\"canales\":[\"*\"]}}" > "$HERMES_YT_HOME/aprobadores.json"

python3 - "$P" "$T" <<'PY' && ok "veredicto: la última línea VEREDICTO manda; sin ella o sin fichero, vacío" || bad "veredicto"
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import hyt_revision as R
f = Path(sys.argv[2]) / "v.md"
assert R._veredicto(f) == ""
f.write_text("Todo bien.\n"); assert R._veredicto(f) == ""
f.write_text("VEREDICTO: CAMBIOS\n...\nVEREDICTO: **APROBADO**\n"); assert R._veredicto(f) == "APROBADO"
f.write_text("veredicto: cambios\n"); assert R._veredicto(f) == "CAMBIOS"
a = []; R._aviso(a, True, "codigo", "Texto"); assert a == [{"grave": True, "codigo": "codigo", "texto": "Texto"}]
PY

python3 - "$P" <<'PY' && ok "revisión: las tres reglas registradas (paquete, opciones de título, temas) no dan avisos mientras falten sus ficheros" || bad "reglas sin sus ficheros"
import sys
sys.path.insert(0, sys.argv[1])
import hyt_revision as R, hyt_pipelines as PL
nombres = {t: [f.__name__ for f in R.reglas_de(t)] for t in PL.TIPOS_PUERTA}
assert nombres == {"alta": [], "elegir-temas": ["_temas"], "elegir-titulo": ["_opciones"], "revision": ["_paquete"],
                   "datos": ["_paquete"], "revision-final": ["_paquete"], "voz": [], "decision": []}, nombres
for tipo in PL.TIPOS_PUERTA:                                   # una puerta suelta, sin encargo
    assert R.revisar("cocina", None, tipo) == {"avisos": [], "graves": 0}, tipo
e = R.E.lanzar("cocina", "propuesta")
d = R.E.carpeta("cocina", e["id"])
assert not any((d / f).exists() for f in ("paquete.json", "opciones.json", "temas.json"))
for tipo in PL.TIPOS_PUERTA:                                   # y la de un encargo que aún no ha dejado esos ficheros
    assert R.revisar("cocina", e["id"], tipo) == {"avisos": [], "graves": 0}, tipo
try:
    R.revisar("no-existe", None, "decision"); raise SystemExit("un canal que no existe no se revisa")
except R.B.Rechazo:
    pass
PY

python3 - "$P" <<'PY' && ok "revisión: reglas por tipo de puerta y comunes («*»), contexto de la regla, graves contados; una regla rota no tumba la revisión" || bad "reglas registradas"
import sys
sys.path.insert(0, sys.argv[1])
import hyt_revision as R
vistos = []
@R.regla("revision", "revision-final")
def _corto(ctx, avisos):
    vistos.append(ctx)
    if not (ctx["carpeta"] / "guion.md").exists():
        R._aviso(avisos, True, "sin-guion", "No hay guion")
@R.regla("*")
def _siempre(ctx, avisos):
    R._aviso(avisos, False, "nota", "Una nota para todas las puertas")
@R.regla("voz")
def _rota(ctx, avisos):
    raise ValueError("ups")
e = R.E.listar("cocina")[0]
r = R.revisar("cocina", e["id"], "revision")
assert [(a["codigo"], a["grave"]) for a in r["avisos"]] == [("nota", False), ("sin-guion", True)] and r["graves"] == 1, r
ctx = vistos[0]
assert ctx["canal"] == "cocina" and ctx["encargo_id"] == e["id"] and ctx["tipo"] == "revision"
assert ctx["carpeta"] == R.E.carpeta("cocina", e["id"]) and ctx["encargo"]["pipeline"] == "propuesta" and ctx["cfg"]["nombre"] == "Cocina Lenta"
(ctx["carpeta"] / "guion.md").write_text("x")
assert R.revisar("cocina", e["id"], "revision-final") == {"avisos": [{"grave": False, "codigo": "nota", "texto": "Una nota para todas las puertas"}], "graves": 0}
assert [a["codigo"] for a in R.revisar("cocina", e["id"], "elegir-temas")["avisos"]] == ["nota"]      # las de otro tipo no se aplican
r = R.revisar("cocina", e["id"], "voz")
assert [(a["codigo"], a["grave"]) for a in r["avisos"]] == [("nota", False), ("regla-rota", False)] and "ups" in r["avisos"][1]["texto"], r
PY

python3 - "$P" <<'PY' && ok "la puerta lleva la revisión arriba; con un aviso grave no se puede aprobar, solo rehacer o rechazar" || bad "revisión en la puerta"
import sys
sys.path.insert(0, sys.argv[1])
import hyt_revision as R, hyt_puertas as PU
@R.regla("decision")
def _grave(ctx, avisos):
    R._aviso(avisos, True, "prueba-grave", "Falta algo imprescindible")
    R._aviso(avisos, False, "prueba-leve", "Un detalle")
p = PU.abrir("cocina", tipo="decision", titulo="📊 Una decisión", texto="El cuerpo")
assert p["texto"].startswith("🧭 Revisión: 2 aviso(s)\n⛔ Falta algo imprescindible\n⚠️ Un detalle\n\nEl cuerpo"), p["texto"]
assert p["revision"]["graves"] == 1 and PU.graves(p) == 1
assert [o["verbo"] for o in PU.opciones_vigentes(p)] == ["cambios", "rechazo"]
try:
    PU.decidir(p["id"], "acepto", "", "ana", "telegram", "111"); raise SystemExit("se aprobó con un aviso grave")
except PU.Rechazo as x:
    assert "aviso grave" in str(x)
PU.decidir(p["id"], "rechazo", "No procede", "ana", "telegram", "111")
R.REGLAS.clear()
limpia = PU.abrir("cocina", tipo="decision", titulo="📊 Otra", texto="El cuerpo")
assert limpia["texto"] == "El cuerpo" and PU.graves(limpia) == 0 and len(PU.opciones_vigentes(limpia)) == 3
PY
E1=$(ls "$HERMES_YT_HOME/canales/cocina/encargos" | head -1)
python3 "$P/hyt_revision.py" revisar cocina "$E1" revision | jq -e '.avisos == [] and .graves == 0' >/dev/null && ok "hyt_revision.py revisar: JSON con avisos y graves" || bad "CLI de la revisión"

python3 - "$P" <<'PY' && ok "lecciones: evidencia, regla general, confirmar, otros canales, revisar a los 3, wiki global" || bad "lecciones"
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_lecciones", Path(sys.argv[1]) / "hyt_lecciones.py")
L = importlib.util.module_from_spec(spec); sys.modules["hyt_lecciones"] = L; spec.loader.exec_module(L)
C = L.C
def rechaza(f):
    try: f(); return False
    except L.Rechazo: return True
regla = "Antes de escribir la intro, comprobar que la promesa del título aparece en el material"
assert rechaza(lambda: L.proponer("cocina", "escribir", regla, ["no-existe"]))                      # evidencia falsa
(C.carpeta("cocina") / "puertas.jsonl").write_text(json.dumps({"puerta": "gabcdef1234"}) + "\n")
assert rechaza(lambda: L.proponer("cocina", "escribir", "En Cocina Lenta no abrir nunca con una pregunta", ["gabcdef1234"]))   # nombra el canal
assert rechaza(lambda: L.proponer("cocina", "escribir", "Cuando presenta Marta Ejemplo, intros de dos frases", ["gabcdef1234"]))  # y a quien presenta
assert rechaza(lambda: L.proponer("cocina", "escribir", "Mira https://x.com antes de nada, siempre", ["gabcdef1234"]))
assert rechaza(lambda: L.proponer("cocina", "escribir", "corta", ["gabcdef1234"]))
l = L.proponer("cocina", "escribir", regla, ["gabcdef1234"])
assert rechaza(lambda: L.proponer("cocina", "escribir", regla, ["gabcdef1234"]))                    # repetida
assert L.para_canal("otro1", "escribir") == []                                                    # sin confirmar no se usa
L.decidir(l["id"], "confirmar", "ana")
assert L.para_canal("cocina", "escribir") == []                                                   # no en su propio canal
assert L.para_canal("otro1", "titular") == []                                                     # solo en su etapa
assert L.para_canal("otro1", "escribir") == [regla]
L.para_canal("otro2", "escribir"); L.para_canal("otro3", "escribir")
assert next(x for x in L.todas() if x["id"] == l["id"])["estado"] == "revisar"
assert L.para_canal("cocina", None, anotar=False) == []
L.decidir(l["id"], "mantener", "ana")
x = next(x for x in L.todas() if x["id"] == l["id"]); assert x["estado"] == "confirmada" and x["usos"] == []
assert regla in (L.B.home() / "wiki/concepts/lecciones.md").read_text()
PY
python3 - "$P" <<'PY' && ok "una lección confirmada llega al contexto de la etapa de otro canal" || bad "lección en el contexto"
import sys
sys.path.insert(0, sys.argv[1])
import hyt_etapa as ET
c = ET.contexto("otro1", "escribir")
assert "## Lecciones de otros canales (confirmadas por una persona)" in c and "comprobar que la promesa del título" in c, c
assert "Lecciones de otros canales" not in ET.contexto("cocina", "escribir") and "Lecciones de otros canales" not in ET.contexto("otro1", "titular")
PY
python3 "$P/hyt_cli.py" leccion cocina titular "Medir cuántos títulos caben en móvil antes de proponerlos" gabcdef1234 >/dev/null && ok "hyt leccion la propone" || bad "hyt leccion"
python3 "$P/hyt_cli.py" lecciones | grep -q "propuesta .*titular .*Medir cuántos títulos" && ok "hyt lecciones las lista" || bad "hyt lecciones"
exit $fail
