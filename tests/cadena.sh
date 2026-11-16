#!/usr/bin/env bash
# Cadena de puertas, papeles y tope de rondas, sin IA: el orden de la cadena, el salto de la puerta de datos, la
# verificación dato a dato, el ajuste por datos corregidos (que no es una ronda), rehacer (que sí lo es) y su tope,
# quién puede decidir cada puerta y la salida de emergencia de quien administra.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0 ROOT
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"; export P
C="python3 $P/hyt_canales.py"; K="$HERMES_YT_HOME/canales/demo"
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

$C alta demo "Canal Demo" "Persona Ejemplo" >/dev/null
$C config demo personas '{"marta":{"nombre":"Marta","correo":"marta@ejemplo.com","roles":["marketing"]},"dario":{"nombre":"Darío","correo":"","roles":["datos"]},"pepa":{"nombre":"Pepa","correo":"","roles":["presentador"]}}' >/dev/null
echo '{"max_decisiones": 0}' > "$HERMES_YT_HOME/yt.json"
aprobadores() {  # aprobadores <clave de quien usa esta máquina (medio local)>
  jq -n --arg u "$(id -un)" --arg local "$1" '{
    marta: {nombre: "Marta", medios: {telegram: "1"}, canales: ["demo"]},
    dario: {nombre: "Darío", medios: {telegram: "2"}, canales: ["demo"]},
    pepa:  {nombre: "Pepa",  medios: {telegram: "3"}, canales: ["*"]},
    ajena: {nombre: "Ajena", medios: {telegram: "5"}, canales: ["otro"]},
    admin: {nombre: "Admin", medios: {telegram: "9"}, canales: ["*"]}} | .[$local].medios.local = $u' > "$HERMES_YT_HOME/aprobadores.json"
}
aprobadores admin
mkdir -p "$K/extensiones/pipelines"
cat > "$K/extensiones/pipelines/video.json" <<'J'
{"id":"video","nombre":"Vídeo","parametros":{"tema":"De qué va"},"etapas":[
  {"id":"escribir","titulo":"Escribir: {tema}","perfil":"yt-guionista","skill":"escribir-guion","salida":"guion.md"},
  {"id":"ajustar","titulo":"Ajustar: {tema}","perfil":"yt-guionista","skill":"ajustar","salida":"ajustes.json"},
  {"id":"cierre","titulo":"Cierre: {tema}","perfil":"yt-editor-jefe","skill":"cierre","salida":"cierre.json"}],
 "puertas":[{"tipo":"revision","papel":"marketing"},{"tipo":"datos","papel":"datos","si_vacio":"saltar"},{"tipo":"revision-final","papel":"presentador"}],
 "rehacer":"ajustar","al_aprobar":"script:hecho.sh {encargo}"}
J
cat > "$K/extensiones/pipelines/corta.json" <<'J'
{"id":"corta","nombre":"Cadena corta","parametros":{"tema":"De qué va"},"etapas":[{"id":"escribir","titulo":"Escribir: {tema}","perfil":"yt-guionista","skill":"escribir-guion","salida":"guion.md"}],
 "puertas":[{"tipo":"revision","papel":"marketing"},{"tipo":"datos","papel":"datos","si_vacio":"saltar"}]}
J
cat > "$K/extensiones/pipelines/libre.json" <<'J'
{"id":"libre","nombre":"Sin papel","parametros":{"tema":"De qué va"},"etapas":[{"id":"escribir","titulo":"Escribir: {tema}","perfil":"yt-guionista","skill":"escribir-guion","salida":"guion.md"}],
 "puerta":{"tipo":"revision","al_aprobar":"nada"}}
J
printf '#!/usr/bin/env bash\necho "$1" >> "$HERMES_YT_HOME/hechos"\n' > "$K/extensiones/hecho.sh"

cat > "$T/py" <<'PY'
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["P"])
import hyt_base as B, hyt_canales as C, hyt_encargos as E, hyt_pipelines as PL, hyt_puertas as PU
ROOT, HOME = os.environ["ROOT"], Path(os.environ["HERMES_YT_HOME"])
TG = {"marta": "1", "dario": "2", "pepa": "3", "ajena": "5", "admin": "9"}
def rechaza(f, trozo=""):
    try: f()
    except B.Rechazo as x:
        assert trozo in str(x), (trozo, str(x)); return True
    return False
def correr(eid, *etapas):
    r = {}
    for e in etapas:
        out = subprocess.run(["bash", f"{ROOT}/etapa.sh", "demo", eid, e], capture_output=True, text=True).stdout
        r = json.loads(out.strip().splitlines()[-1]); assert r["outcome"] == "done", r
    return r
def nuevo(tema, pipeline="video", datos=None):
    """Lanza, deja datos.json si se pide, corre todas sus etapas y devuelve (encargo, puerta abierta)."""
    e = E.lanzar("demo", pipeline, {"tema": tema})
    if datos is not None: poner_datos(e["id"], datos)
    r = correr(e["id"], *[s["id"] for s in e["etapas"]])
    return e["id"], r["puerta"]
def poner_datos(eid, estados):
    B.escribir(E.carpeta("demo", eid) / "datos.json", {"datos": [{"id": i, "dato": f"dato {i}", "estado": s, "valor": ""} for i, s in enumerate(estados, 1)]})
def datos(eid): return {x["id"]: x for x in B.leer(E.carpeta("demo", eid) / "datos.json")["datos"]}
def decide(g, quien, verbo, texto=""):
    """Decide por Telegram y firma (la ventana para deshacer está a cero). Devuelve la puerta firmada."""
    PU.decidir(g, verbo, texto, quien, "telegram", TG[quien]); return PU.firmar(g)
def enc(eid): return E.leer("demo", eid)
def abierta(eid):
    ps = [p for p in PU.puertas() if p.get("encargo") == eid]
    assert len(ps) <= 1, "nunca hay dos puertas pendientes del mismo encargo"
    return ps[0] if ps else None
def hechos(): return (HOME / "hechos").read_text().split() if (HOME / "hechos").exists() else []
def historial(eid): return [json.loads(l) for l in (E.carpeta("demo", eid) / ".estado/historial.jsonl").read_text().splitlines()]
def registro(): return [json.loads(l) for l in (C.carpeta("demo") / "puertas.jsonl").read_text().splitlines()]
PY
caso() { python3 - <<PY && ok "$1" || bad "$1"
exec(open("$T/py").read())
$2
PY
}

caso "orden de la cadena: revisión (marketing) → datos (datos) → revisión final (presentador); solo la última ejecuta al_aprobar" '
eid, g = nuevo("orden", datos=["pendiente"])
p = PU.leer(g)
assert (p["tipo"], p["papel"], p["indice"], p["total"], p["ronda"]) == ("revision", "marketing", 0, 3, 0), p
assert p["rehacer"] == "ajustar" and p["al_aprobar"].startswith("script:hecho.sh") and "Puerta 1 de 3" in p["texto"]
assert enc(eid)["estado"] == "en-puerta" and enc(eid)["puerta_indice"] == 0 and enc(eid)["puerta_id"] == g
f = decide(g, "marta", "acepto")
g2 = abierta(eid)
assert f["resultado"] == "aprobado: pasa a la puerta datos (datos) [" + g2["id"] + "]" and f["firma"] == "Marta (telegram)", f
assert (g2["tipo"], g2["papel"], g2["indice"]) == ("datos", "datos", 1) and [o["etiqueta"] for o in g2["opciones"]] == ["✅ Datos verificados", "🗑 Rechazar"]
assert enc(eid)["estado"] == "en-puerta" and enc(eid)["puerta_indice"] == 1 and enc(eid)["puerta_id"] == g2["id"] and hechos() == []
PU.verificar_dato(g2["id"], 1, "verificado", "", "dario", "telegram", "2")
f = decide(g2["id"], "dario", "acepto")
g3 = abierta(eid)
assert "pasa a la puerta revision-final (presentador)" in f["resultado"] and (g3["tipo"], g3["papel"], g3["indice"]) == ("revision-final", "presentador", 2)
assert hechos() == [] and enc(eid)["estado"] == "en-puerta"
f = decide(g3["id"], "pepa", "acepto")
time.sleep(1)
assert f["resultado"].startswith("lanzado hecho.sh") and hechos() == [eid] and enc(eid)["estado"] == "cerrado" and abierta(eid) is None
assert [(r["tipo"], r["verbo"], r["persona"]) for r in registro() if not r.get("evento")] == [("revision", "acepto", "marta"), ("datos", "acepto", "dario"), ("revision-final", "acepto", "pepa")]
'

caso "la puerta de datos se salta si no hay datos.json o no queda ningún dato pendiente; si era la última, la anterior cierra" '
eid, g = nuevo("sin datos")
f = decide(g, "marta", "acepto")
assert "pasa a la puerta revision-final" in f["resultado"] and abierta(eid)["indice"] == 2 and enc(eid)["puerta_indice"] == 2, f
eid, g = nuevo("todos verificados", datos=["verificado", "verificado"])
decide(g, "marta", "acepto"); assert abierta(eid)["tipo"] == "revision-final"
eid, g = nuevo("con uno pendiente", datos=["verificado", "pendiente"])
decide(g, "marta", "acepto"); assert abierta(eid)["tipo"] == "datos"
eid, g = nuevo("corta sin datos", pipeline="corta")
f = decide(g, "marta", "acepto")
assert f["resultado"] == "aprobado" and enc(eid)["estado"] == "cerrado" and abierta(eid) is None, f
eid, g = nuevo("corta con datos", pipeline="corta", datos=["pendiente"])
decide(g, "marta", "acepto"); assert abierta(eid)["tipo"] == "datos" and enc(eid)["estado"] == "en-puerta"
'

caso "datos: no se aprueba con datos pendientes (ni forzando); verificar_dato con sus tres estados, con papel y registrado" '
eid, g = nuevo("datos", datos=["pendiente", "pendiente", "pendiente"])
decide(g, "marta", "acepto"); g = abierta(eid)["id"]
p = PU.leer(g)
assert PU.datos_pendientes(p) == 3 and PU.graves(p) == 1 and [o["verbo"] for o in PU.opciones_vigentes(p)] == ["rechazo"]
assert rechaza(lambda: PU.decidir(g, "acepto", "", "dario", "telegram", "2"), "Quedan 3 dato(s) por verificar")
assert rechaza(lambda: PU.decidir_local(g, "acepto", "", "tengo prisa"), "Quedan 3 dato(s)")          # esto no se fuerza
assert rechaza(lambda: PU.decidir(g, "cambios", "x", "dario", "telegram", "2"), "Opción no válida")    # en datos no hay «rehacer»
assert rechaza(lambda: PU.verificar_dato(g, 1, "verificado", "", "marta", "telegram", "1"), "papel «datos»")
assert rechaza(lambda: PU.verificar_dato(g, 1, "verificado", "", "dario", "telegram", "1"), "No estás autorizado")   # identidad de otra
assert rechaza(lambda: PU.verificar_dato(g, 1, "dudoso", "", "dario", "telegram", "2"), "verificado, corregido, eliminado")
assert rechaza(lambda: PU.verificar_dato(g, 2, "corregido", "  ", "dario", "telegram", "2"), "valor correcto")
assert rechaza(lambda: PU.verificar_dato(g, 99, "verificado", "", "dario", "telegram", "2"), "No conozco el dato 99")
assert all(x["estado"] == "pendiente" for x in datos(eid).values())
d = PU.verificar_dato(g, 1, "verificado", "no se guarda", "dario", "telegram", "2")
assert (d["estado"], d["valor"], d["verificado_por"]) == ("verificado", "", "dario")
PU.verificar_dato(g, "2", "corregido", "son 40, no 400", "dario", "telegram", "2")                    # el id, como texto o número
assert PU.datos_pendientes(PU.leer(g)) == 1 and rechaza(lambda: PU.decidir(g, "acepto", "", "dario", "telegram", "2"), "Quedan 1")
PU.verificar_dato(g, 3, "eliminado", "", "dario", "telegram", "2")
assert {i: (x["estado"], x["valor"]) for i, x in datos(eid).items()} == {1: ("verificado", ""), 2: ("corregido", "son 40, no 400"), 3: ("eliminado", "")}
PU.verificar_dato(g, 3, "verificado", "", "dario", "telegram", "2")                                    # mientras está abierta, se puede cambiar
ev = [r for r in registro() if r.get("evento") == "dato" and r["encargo"] == eid]
assert [(r["dato"], r["estado"], r["valor"], r["persona"], r["medio"], r["puerta"]) for r in ev] == [
    (1, "verificado", "", "dario", "telegram", g), (2, "corregido", "son 40, no 400", "dario", "telegram", g),
    (3, "eliminado", "", "dario", "telegram", g), (3, "verificado", "", "dario", "telegram", g)], ev
p = PU.leer(g); assert PU.datos_pendientes(p) == 0 and PU.graves(p) == 0 and len(PU.opciones_vigentes(p)) == 2
otra, g0 = nuevo("otra")
assert rechaza(lambda: PU.verificar_dato(g0, 1, "verificado", "", "dario", "telegram", "2"), "no es de verificación de datos")
decide(g, "dario", "rechazo", "los datos no se sostienen")
assert enc(eid)["estado"] == "descartado" and rechaza(lambda: PU.verificar_dato(g, 1, "verificado", "", "dario", "telegram", "2"), "ya está resuelta")
'

caso "corregir un dato relanza «ajustar» sin sumar ronda y la cadena vuelve a la primera puerta; ya ajustado, no se repite" '
eid, g = nuevo("ajuste", datos=["pendiente", "pendiente"])
decide(g, "marta", "acepto"); g = abierta(eid)["id"]
PU.verificar_dato(g, 1, "verificado", "", "dario", "telegram", "2")
PU.verificar_dato(g, 2, "corregido", "fue en 2019", "dario", "telegram", "2")
f = decide(g, "dario", "acepto")
e = enc(eid)
assert f["resultado"] == "datos corregidos (1): se ajusta desde ajustar y vuelve a la primera puerta", f
assert e["estado"] == "en-curso" and e.get("rondas", 0) == 0 and e["relanzamientos"] == 1 and e["puerta_indice"] == 0 and "puerta_id" not in e and abierta(eid) is None
h = historial(eid)[-1]; assert (h["accion"], h["desde"], h["ronda"], h["texto"]) == ("ajuste-datos", "ajustar", 0, "datos corregidos por una persona"), h
assert "datos corregidos por una persona" in (E.carpeta("demo", eid) / ".estado/feedback-ajustar.txt").read_text()
llamadas = Path(os.environ["FALSO_LLAMADAS"]).read_text()
assert f"--idempotency-key {eid}-ajustar-r1" in llamadas and f"--idempotency-key {eid}-cierre-r1" in llamadas and f"{eid}-escribir-r1" not in llamadas
g = correr(eid, "ajustar", "cierre")["puerta"]
p = PU.leer(g); assert (p["tipo"], p["indice"], p["ronda"]) == ("revision", 0, 0), p             # otra vez la primera, sin ronda
decide(g, "marta", "acepto")
assert abierta(eid)["tipo"] == "revision-final"                                                 # ya no quedan pendientes: datos se salta
# si aparece un dato nuevo, la puerta de datos vuelve; el que ya se ajustó no relanza otra vez
d = B.leer(E.carpeta("demo", eid) / "datos.json"); d["datos"].append({"id": 3, "dato": "dato 3", "estado": "pendiente", "valor": ""})
B.escribir(E.carpeta("demo", eid) / "datos.json", d)
f = decide(abierta(eid)["id"], "pepa", "cambios", "frase 2: más corta")
g = correr(eid, "ajustar", "cierre")["puerta"]; decide(g, "marta", "acepto"); g = abierta(eid)["id"]
assert PU.leer(g)["tipo"] == "datos"
PU.verificar_dato(g, 3, "verificado", "", "dario", "telegram", "2")
f = decide(g, "dario", "acepto")
assert "pasa a la puerta revision-final" in f["resultado"] and enc(eid)["rondas"] == 1 and enc(eid)["relanzamientos"] == 2, f
'

caso "rehacer en la última puerta vuelve a la primera y suma ronda; rechazar en cualquiera descarta" '
eid, g = nuevo("rehacer")
decide(g, "marta", "acepto"); g = abierta(eid)["id"]
assert PU.leer(g)["tipo"] == "revision-final"
assert rechaza(lambda: PU.decidir(g, "cambios", "", "pepa", "telegram", "3"), "necesita un texto")
f = decide(g, "pepa", "cambios", "frase 14: yo diría «a fuego lento»")
e = enc(eid)
assert f["resultado"] == "se rehace desde ajustar (ronda 1 de 3)" and e["estado"] == "en-curso" and e["rondas"] == 1 and e["puerta_indice"] == 0, (f, e)
assert "frase 14" in (E.carpeta("demo", eid) / ".estado/feedback-ajustar.txt").read_text() and historial(eid)[-1]["accion"] == "rehacer"
g = correr(eid, "ajustar", "cierre")["puerta"]
p = PU.leer(g)
assert (p["tipo"], p["papel"], p["indice"], p["ronda"]) == ("revision", "marketing", 0, 1) and "Puerta 1 de 3 · ronda 1 de 3" in p["texto"], p
f = decide(g, "marta", "rechazo", "el tema ya no interesa")
assert f["resultado"] == "descartado" and enc(eid)["estado"] == "descartado" and enc(eid)["descartado_motivo"] == "el tema ya no interesa" and abierta(eid) is None and eid not in hechos()
'

caso "tope de rondas: con rondas_max 3 se rehace tres veces; a la cuarta petición el encargo queda descartado" '
assert E.rondas_max("demo") == 3
eid, g = nuevo("tope")
for ronda in (1, 2, 3):
    f = decide(g, "marta", "cambios", f"cambio {ronda}")
    assert f["resultado"] == f"se rehace desde ajustar (ronda {ronda} de 3)" and enc(eid)["rondas"] == ronda, f
    g = correr(eid, "ajustar", "cierre")["puerta"]
    assert PU.leer(g)["ronda"] == ronda and PU.leer(g)["indice"] == 0
antes = Path(os.environ["FALSO_LLAMADAS"]).read_text().count(f"--idempotency-key {eid}-")
f = decide(g, "marta", "cambios", "cambio 4")
e = enc(eid)
assert f["estado"] == "firmada" and f["resultado"] == "descartado: superó las 3 rondas", f
assert e["estado"] == "descartado" and e["descartado_motivo"] == "superó las 3 rondas" and e["rondas"] == 3 and "puerta_id" not in e
assert Path(os.environ["FALSO_LLAMADAS"]).read_text().count(f"--idempotency-key {eid}-") == antes        # no se crean tarjetas
h = historial(eid)[-1]; assert h["accion"] == "descartado-por-rondas" and h["texto"] == "cambio 4", h
assert registro()[-1]["resultado"] == "descartado: superó las 3 rondas" and eid not in [x["id"] for x in E.listar("demo", abiertos=True)]
# el tope es del canal: con rondas_max 1, la segunda petición descarta; reintentos, vueltas y ajustes no gastan ronda
C.config("demo", "reglas.rondas_max", 1)
eid, g = nuevo("tope uno")
r = E.rehacer_desde("demo", eid, "cierre", "", "prueba", accion="reintentar", cuenta_ronda=False)
assert r.get("rondas", 0) == 0 and r["relanzamientos"] == 1 and r["estado"] == "en-curso"
r = E.rehacer_desde("demo", eid, "ajustar", "uno", "prueba"); assert r["rondas"] == 1 and r["relanzamientos"] == 2
r = E.rehacer_desde("demo", eid, "ajustar", "", "prueba", accion="ajuste-datos", cuenta_ronda=False); assert r["estado"] == "en-curso" and r["rondas"] == 1
r = E.rehacer_desde("demo", eid, "ajustar", "dos", "prueba"); assert r["estado"] == "descartado" and r["descartado_motivo"] == "superó las 1 rondas"
C.config("demo", "reglas.rondas_max", 3)
'

caso "papeles: solo decide quien tiene el papel de la puerta; quien administra, solo por el medio local; sin papel, cualquiera autorizado" '
eid, g = nuevo("papeles")
for quien, trozo in (("dario", "papel «marketing»"), ("pepa", "papel «marketing»"), ("admin", "papel «marketing»"), ("ajena", "No estás autorizado")):
    assert rechaza(lambda: PU.decidir(g, "acepto", "", quien, "telegram", TG[quien]), trozo), quien
assert PU.leer(g)["estado"] == "abierta"
for persona, papel, medio, puede in (("marta", "marketing", "telegram", True), ("marta", "datos", "telegram", False), ("marta", "datos", "local", False),
                                     ("marta", "", "telegram", True), ("dario", "datos", "dashboard", True), ("pepa", "presentador", "telegram", True),
                                     ("admin", "marketing", "telegram", False), ("admin", "marketing", "dashboard", False), ("admin", "marketing", "local", True),
                                     ("admin", "", "telegram", True), ("ajena", "", "telegram", False), ("ajena", "marketing", "local", False),
                                     ("nadie", "", "local", False)):
    assert PU.puede_decidir(persona, "demo", papel, medio) is puede, (persona, papel, medio)
f = PU.decidir_local(g, "acepto")                                    # la salida de emergencia: quien administra, en esta máquina
assert f["firma"] == "Admin (local)" and abierta(eid)["tipo"] == "revision-final", f
g = abierta(eid)["id"]
PU.decidir(g, "acepto", "", "pepa", "telegram", "3")
C.config("demo", "personas.pepa.roles", ["marketing"])                # pierde el papel antes de la firma: el notario lo vuelve a comprobar
assert rechaza(lambda: PU.firmar(g), "no está autorizado") and PU.leer(g)["estado"] == "error" and enc(eid)["estado"] == "en-puerta"
C.config("demo", "personas.pepa.roles", ["presentador"])
libre, g = nuevo("libre", pipeline="libre")
assert PU.leer(g)["papel"] == "" and decide(g, "dario", "acepto")["resultado"] == "aprobado"       # sin papel, como siempre
'
aprobadores dario   # ahora quien usa esta máquina es Darío, que está en el canal con el papel «datos»: no es administrador
caso "quien tiene entrada en el canal pero no el papel no decide ni siquiera en local" '
eid, g = nuevo("local sin papel", datos=["pendiente"])
assert rechaza(lambda: PU.decidir_local(g, "acepto"), "papel «marketing»") and PU.leer(g)["estado"] == "abierta"
decide(g, "marta", "acepto"); g = abierta(eid)["id"]
assert PU.dato_local(g, 1, "corregido", "el dato bueno")["verificado_por"] == "dario"
assert "se ajusta desde ajustar" in PU.decidir_local(g, "acepto")["resultado"]                      # en su puerta sí
'
aprobadores admin

caso "el estado y hyt estado dicen en qué puerta de la cadena está cada encargo, quién la decide y su ronda" '
import hyt_estado as ES, hyt_cli as CLI
eid, g = nuevo("estado", datos=["pendiente", "verificado"])
decide(g, "marta", "cambios", "otra vez"); g = correr(eid, "ajustar", "cierre")["puerta"]
assert E.situacion(enc(eid)) == {"ronda": 1, "puerta": {"tipo": "revision", "papel": "marketing", "indice": 1, "total": 3}}
t = ES.turno("demo"); linea = next(l for l in t.splitlines() if g in l)
assert "puerta 1/3: revision · decide: marketing · ronda 1" in linea, linea
decide(g, "marta", "acepto"); g = abierta(eid)["id"]
linea = next(l for l in ES.turno("demo").splitlines() if g in l)
assert "puerta 2/3: datos · decide: datos · ronda 1 · 1 dato(s) por verificar" in linea, linea
linea = next(l for l in CLI.estado("demo").splitlines() if eid in l and "•" in l)
assert linea.endswith("en-puerta · 3/3 etapas · puerta 2/3: datos (datos) · ronda 1"), linea
assert E.situacion_texto({"estado": "en-curso"}) == "" and E.situacion({"estado": "en-curso", "rondas": 2}) == {"ronda": 2, "puerta": None}
libre, gl = nuevo("estado libre", pipeline="libre")
assert E.situacion_texto(enc(libre)) == "puerta: revision"
assert "dato" not in "".join(l for l in ES.turno("demo").splitlines() if "puerta datos" in l and "→" in l)   # los eventos de dato no salen como decisiones
'

# la cadena de la pipeline de producción (guion) y la CLI del medio local
caso "guion (producción): al acabar se abre su primera puerta, la de revisión de marketing, y rehace desde «ajustar»" '
e = E.lanzar("demo", "guion", {"tema": "Un guion", "pilar": "p"})
g = correr(e["id"], *[s["id"] for s in e["etapas"]])["puerta"]
p = PU.leer(g)
assert (p["tipo"], p["papel"], p["indice"], p["total"], p["rehacer"], p["al_aprobar"]) == ("revision", "marketing", 0, 3, "ajustar", "nada"), p
(E.carpeta("demo", e["id"]) / "datos.json").write_text(json.dumps({"datos": [{"id": "d1", "dato": "una cifra", "estado": "pendiente", "valor": ""}]}))
decide(g, "marta", "acepto"); print(abierta(e["id"])["id"], file=open(os.environ["HERMES_YT_HOME"] + "/puerta-datos", "w"))
'
GD=$(cat "$HERMES_YT_HOME/puerta-datos")
PUC="python3 $P/hyt_puertas.py"
si "hyt_puertas.py dato-local: quien administra verifica un dato desde esta máquina y dice cuántos quedan" "$PUC dato-local $GD d1 corregido 'la cifra buena' | grep -q 'Dato d1: corregido → la cifra buena · quedan 0 por verificar'"
si "y un estado que no existe se rechaza" "! $PUC dato-local $GD d1 dudoso"
si "la memoria del canal no confunde un dato verificado con una decisión" "! grep -q 'None' $K/wiki/concepts/decisiones.md 2>/dev/null"
exit $fail
