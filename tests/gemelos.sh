#!/usr/bin/env bash
# Dos versiones del mismo guion (gemelos), sin IA: «pipeline:a+b» lanza las dos con la misma elección; la primera que
# acaba espera a la otra; con las dos acabadas se abre UNA puerta para elegir versión; la elegida sigue su cadena y la
# otra se archiva; si un gemelo falla, el otro sigue solo; y el que llega tarde no abre otra puerta.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0 ROOT
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"; export P
C="python3 $P/hyt_canales.py"; K="$HERMES_YT_HOME/canales/demo"
$C alta demo "Canal Demo" "Persona Ejemplo" >/dev/null
$C config demo personas '{"marta":{"nombre":"Marta","correo":"marta@ejemplo.com","roles":["marketing"]},"pepa":{"nombre":"Pepa","correo":"","roles":["presentador","datos"]}}' >/dev/null
echo '{"max_decisiones": 0}' > "$HERMES_YT_HOME/yt.json"
jq -n --arg u "$(id -un)" '{marta: {nombre: "Marta", medios: {telegram: "1"}, canales: ["demo"]},
  pepa: {nombre: "Pepa", medios: {telegram: "3"}, canales: ["demo"]}, admin: {nombre: "Admin", medios: {local: $u}, canales: ["*"]}}' > "$HERMES_YT_HOME/aprobadores.json"
mkdir -p "$K/extensiones/pipelines"
cat > "$K/extensiones/pipelines/titulo.json" <<'J'
{"id":"titulo","nombre":"Título","parametros":{"tema":"De qué va"},"etapas":[
  {"id":"titular","titulo":"Titular: {tema}","perfil":"yt-titulador","skill":"titular","salida":"eleccion.json"}],
 "puerta":{"tipo":"elegir-titulo","papel":"marketing","al_aprobar":"pipeline:va+vb"}}
J
for v in a:propia b:investigada; do cat > "$K/extensiones/pipelines/v${v%%:*}.json" <<J
{"id":"v${v%%:*}","nombre":"Versión ${v#*:}","version":"${v#*:}","parametros":{"tema":"De qué va"},"etapas":[
  {"id":"escribir","titulo":"Escribir: {tema}","perfil":"yt-guionista","skill":"escribir-guion","salida":"guion.md"},
  {"id":"ajustar","titulo":"Ajustar: {tema}","perfil":"yt-guionista","skill":"ajustar","salida":"ajustes.json"}],
 "puertas":[{"tipo":"revision","papel":"marketing"},{"tipo":"revision-final","papel":"presentador"}],
 "rehacer":"ajustar","al_aprobar":"nada"}
J
done

cat > "$T/py" <<'PY'
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, os.environ["P"])
import hyt_base as B, hyt_encargos as E, hyt_puertas as PU
ROOT = os.environ["ROOT"]
TG = {"marta": "1", "pepa": "3"}
def rechaza(f, trozo=""):
    try: f()
    except B.Rechazo as x:
        assert trozo in str(x), (trozo, str(x)); return True
    return False
def correr(eid, *etapas):
    r = {}
    for e in etapas or [s["id"] for s in E.leer("demo", eid)["etapas"]]:
        out = subprocess.run(["bash", f"{ROOT}/etapa.sh", "demo", eid, e], capture_output=True, text=True).stdout
        r = json.loads(out.strip().splitlines()[-1]); assert r["outcome"] == "done", r
    return r
def decide(g, quien, verbo, texto=""):
    PU.decidir(g, verbo, texto, quien, "telegram", TG[quien]); return PU.firmar(g)
def enc(eid): return E.leer("demo", eid)
def abiertas(eid): return [p for p in PU.puertas() if p.get("encargo") == eid]
def gemelos(tema):
    """Lanza el título, lo aprueba y devuelve los dos encargos gemelos (A, B)."""
    t = E.lanzar("demo", "titulo", {"tema": tema})
    g = correr(t["id"])["puerta"]
    f = decide(g, "marta", "algunas", "el 1")
    return f, sorted((e["id"] for e in E.listar("demo") if e.get("origen") == t["id"]), key=lambda i: enc(i)["version_letra"])
PY
caso() { python3 - <<PY && ok "$1" || bad "$1"
exec(open("$T/py").read())
$2
PY
}

caso "«pipeline:a+b» lanza dos gemelos con la misma elección, letras A y B y su versión" '
f, (a, b) = gemelos("pago sin banco")
assert f["resultado"].startswith("lanzadas 2 versiones: A " + a + ", B " + b), f
A, Bb = enc(a), enc(b)
assert A["gemelos"] == Bb["gemelos"] == [a, b] and (A["version_letra"], Bb["version_letra"]) == ("A", "B")
assert (A["version"], Bb["version"]) == ("propia", "investigada") and A["origen"] == Bb["origen"]
assert "eleccion.json" in A["heredados"] and "eleccion.json" in Bb["heredados"]
'

caso "el primero que acaba espera; con los dos acabados se abre UNA puerta «elegir-version»" '
f, (a, b) = gemelos("doble gasto")
r = correr(a)
assert "puerta" not in r and enc(a)["estado"] == "esperando-gemelo" and not abiertas(a), r
r = correr(b); g = r["puerta"]; p = PU.leer(g)
assert p["tipo"] == "elegir-version" and p["papel"] == "marketing" and p["encargo"] == a
assert [(x["letra"], x["version"], x["encargo"]) for x in p["gemelos"]] == [("A", "propia", a), ("B", "investigada", b)]
assert enc(a)["puerta_id"] == enc(b)["puerta_id"] == g and enc(a)["estado"] == enc(b)["estado"] == "en-puerta"
assert len([x for x in PU.puertas() if x["tipo"] == "elegir-version"]) == 1
'

caso "elegir B: B pasa a su revisión, A se archiva con su motivo; una letra que no existe se rechaza" '
f, (a, b) = gemelos("nodos")
correr(a); g = correr(b)["puerta"]
assert rechaza(lambda: PU.decidir(g, "algunas", "la C", "marta", "telegram", "1"), "Di qué versión eliges")
assert rechaza(lambda: PU.decidir(g, "algunas", "", "pepa", "telegram", "3"))     # no tiene el papel
f = decide(g, "marta", "algunas", "Me quedo con la B")
assert f["resultado"].startswith("elegida la versión B (investigada): pasa a la puerta revision"), f
assert enc(a)["estado"] == "descartado" and "versión B" in enc(a)["descartado_motivo"] and "puerta_id" not in enc(a)
nb = abiertas(b); assert len(nb) == 1 and nb[0]["tipo"] == "revision" and enc(b)["gemelos_resuelto"] == "B"
f = decide(nb[0]["id"], "marta", "cambios", "frase 3: más corta")
r = correr(b, "ajustar")
assert PU.leer(r["puerta"])["tipo"] == "revision" and PU.leer(r["puerta"])["ronda"] == 1   # tras rehacer, su cadena normal
'

caso "elegir también por el nombre de la versión; rechazar descarta las dos" '
f, (a, b) = gemelos("consenso"); correr(a); g = correr(b)["puerta"]
f = decide(g, "marta", "algunas", "la propia"); assert "elegida la versión A" in f["resultado"] and enc(b)["estado"] == "descartado"
f, (a, b) = gemelos("minería"); correr(a); g = correr(b)["puerta"]
f = decide(g, "marta", "rechazo", "ninguna convence")
assert enc(a)["estado"] == enc(b)["estado"] == "descartado" and not abiertas(a) and not abiertas(b), f
'

caso "si un gemelo falla, el otro sigue solo; si el que falló acaba después, se archiva sin abrir otra puerta" '
f, (a, b) = gemelos("tarifas")
correr(a); assert enc(a)["estado"] == "esperando-gemelo"
e = enc(b); e["estado"] = "parado"; E.guardar("demo", e)
g = PU.gemelo_fallo("demo", b)
assert g and g["tipo"] == "revision" and g["encargo"] == a and enc(a)["gemelos_resuelto"]
r = correr(b)
assert "puerta" not in r and enc(b)["estado"] == "descartado" and "ya se había seguido" in enc(b)["descartado_motivo"]
f, (a, b) = gemelos("tarifas dos")
e = enc(b); e["estado"] = "parado"; E.guardar("demo", e)
g = correr(a)["puerta"]; assert PU.leer(g)["tipo"] == "revision"          # el otro ya estaba parado: sigue solo
'
caso "en la lista de vídeos los gemelos son un solo vídeo: «Eligiendo versión» y luego la versión elegida" '
import hyt_videos as V
f, (a, b) = gemelos("lista única")
mios = lambda: [v for v in V.lista("demo") if v["encargo"] in (a, b)]
assert len(mios()) == 1 and mios()[0]["encargo"] == a
correr(a); assert len(mios()) == 1 and mios()[0]["preparando"]
g = correr(b)["puerta"]
assert [(v["encargo"], v["estado_id"], v["puerta"]["tipo"]) for v in mios()] == [(a, "eligiendo", "elegir-version")], mios()
decide(g, "marta", "algunas", "B")
assert [(v["encargo"], v["estado_id"], v["version"]) for v in mios()] == [(b, "revision", "investigada")], mios()
'
caso "sustituir una puerta: la vieja queda reemplazada, la nueva lleva la nota; con gemelos, otra vez una sola puerta de elegir" '
f, (a, b) = gemelos("sustituir"); correr(a); g = correr(b)["puerta"]
n = PU.reemplazar(g, "Te lo vuelvo a mandar corregido.")
assert PU.leer(g)["estado"] == "reemplazada" and PU.leer(g)["sustituida_por"] == n["id"]
assert n["tipo"] == "elegir-version" and n["nota"] == "Te lo vuelvo a mandar corregido." and enc(a)["puerta_id"] == enc(b)["puerta_id"] == n["id"]
decide(n["id"], "marta", "algunas", "A"); r = abiertas(a)[0]
m = PU.reemplazar(r["id"], "Corregido")
assert m["tipo"] == "revision" and enc(a)["puerta_id"] == m["id"] and len(abiertas(a)) == 1
assert rechaza(lambda: PU.reemplazar(r["id"]), "Solo se sustituye una puerta abierta")
'
exit $fail
