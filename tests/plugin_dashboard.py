"""API de la pestaña YouTube con un panel falso (sesión inyectada): identidad, canales, puertas (solo lectura) y disco."""
import importlib.util, json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
T = Path(tempfile.mkdtemp()); os.environ.update(HERMES_YT_HOME=str(T / "home"), HERMES_YT_DESHACER_S="60", HYT_SIN_PASOS="1",
                                                HERMES_BIN=str(ROOT / "tests/dobles/hermes"), FALSO_LLAMADAS=str(T / "llamadas"),
                                                FALSO_TABLEROS=str(T / "tableros"))
spec = importlib.util.spec_from_file_location("hyt_dashboard", ROOT / "plugin/hermes-youtube/dashboard/plugin_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
fallos = 0
def ok(c, t):
    global fallos
    print(("ok   " if c else "FAIL ") + t); fallos += (not c)

manifest = json.loads((ROOT / "plugin/hermes-youtube/dashboard/manifest.json").read_text())
ok(manifest["name"] == "hermes-youtube" and manifest["label"] == "YouTube" and manifest["tab"]["path"] == "/youtube"
   and manifest["entry"] == "dist/index.js" and manifest["api"] == "plugin_api.py", "manifest: pestaña «YouTube» en /youtube")
js = (ROOT / "plugin/hermes-youtube/dashboard/dist/index.js").read_text()
ok('const API = "/api/plugins/hermes-youtube"' in js and 'register("hermes-youtube"' in js and '"/canales"' in js, "la pestaña llama a /api/plugins/hermes-youtube")

SESION = {"email": "ana@ejemplo.com"}
app = FastAPI(); app.include_router(m.router, prefix="/api/plugins/hermes-youtube")
@app.middleware("http")
async def sesion(request: Request, call_next):
    if SESION.get("email"):
        request.state.session = NS(email=SESION["email"], user_id="u1", provider="test")
    return await call_next(request)
cli = TestClient(app); A = "/api/plugins/hermes-youtube"
m.C.alta("demo", "Canal Demo", "Persona Ejemplo")
m.C.config("demo", "pilares", [{"id": "oficio", "nombre": "El oficio", "tipo": "pilar"}])
(T / "home/aprobadores.json").write_text(json.dumps({"ana": {"nombre": "Ana", "medios": {"dashboard": "ana@ejemplo.com", "telegram": "111"}, "canales": ["*"]},
                                                    "leo": {"nombre": "Leo", "medios": {"telegram": "leo@ejemplo.com"}, "canales": ["*"]}}))
g = m.PU.abrir("demo", tipo="decision", titulo="📊 Una decisión", texto="3 propuestas")["id"]

SESION["email"] = "otro@ejemplo.com"
ok(cli.get(A + "/canales").status_code == 403, "quien no está en aprobadores no entra")
SESION["email"] = "leo@ejemplo.com"
ok(cli.get(A + "/canales").status_code == 403, "ni quien está, pero no por el medio dashboard")
SESION["email"] = None
ok(cli.get(A + "/canales").status_code == 403 and cli.get(A + "/puertas").status_code == 403 and cli.get(A + "/sistema").status_code == 403,
   "sin sesión (y sin modo local) no entra en ninguna ruta")
SESION["email"] = "ana@ejemplo.com"
c = cli.get(A + "/canales").json()
ok(len(c) == 1 and c[0] == {"slug": "demo", "nombre": "Canal Demo", "presentador": "Persona Ejemplo", "idioma": "es-ES",
                            "pilares": ["El oficio"], "capacidades": ["pilares"], "pausado": False, "encargos": [], "puertas": 1},
   f"los canales con quién presenta, sus pilares y sus puertas ({c})")
m.C.config("demo", "politicas.pausado", True)
ok(cli.get(A + "/canales").json()[0]["pausado"] is True, "un canal en pausa lo dice")
ps = cli.get(A + "/puertas").json()
ok(len(ps) == 1 and ps[0]["canal"] == "demo" and [o["verbo"] for o in ps[0]["opciones"]] == ["acepto", "cambios", "rechazo"] and "revision" not in ps[0],
   "las puertas pendientes con sus opciones")
ok(cli.post(A + f"/decidir/{g}", json={"verbo": "acepto"}).status_code in (404, 405), "el panel no decide (no hay /decidir)")
ok(cli.post(A + f"/deshacer/{g}").status_code in (404, 405), "ni deshace")
ok(m.PU.leer(g)["estado"] == "abierta", "la puerta sigue abierta")
d = cli.get(A + "/sistema").json()
ok(len(d["disco"]) >= 1 and {"punto", "usado_pct", "libres_gb", "total_gb", "aviso"} <= set(d["disco"][0]), "el disco, para verlo lo primero")
# cada encargo dice en qué puerta de su cadena está (tipo y papel) y su ronda
m.C.config("demo", "politicas.pausado", False)
e = m.E.lanzar("demo", "guion", {"tema": "Un guion", "pilar": "oficio"})
enc = m.E.leer("demo", e["id"]); enc["rondas"] = 2; enc["puerta_indice"] = 1; m.E.guardar("demo", enc)
(m.E.carpeta("demo", e["id"]) / "datos.json").write_text(json.dumps({"datos": [{"id": 1, "dato": "x", "estado": "pendiente"}, {"id": 2, "dato": "y", "estado": "verificado"}]}))
gd = m.PU.abrir("demo", e["id"])["id"]
en = cli.get(A + "/canales").json()[0]["encargos"]
ok(en == [{"id": e["id"], "nombre": "Guion", "estado": "en-puerta", "ronda": 2, "puerta": {"tipo": "datos", "papel": "datos", "indice": 2, "total": 3}}],
   f"cada encargo, con su ronda y su puerta de la cadena: tipo, papel y posición ({en})")
p = next(x for x in cli.get(A + "/puertas").json() if x["id"] == gd)
ok((p["tipo"], p["papel"], p["indice"], p["total"], p["ronda"], p["datos_pendientes"]) == ("datos", "datos", 1, 3, 2, 1)
   and [o["etiqueta"] for o in p["opciones"]] == ["✅ Datos verificados", "🗑 Rechazar"], "la puerta de datos dice quién la decide y cuántos datos faltan")
otro = m.E.lanzar("demo", "propuesta")
en = {x["id"]: x for x in cli.get(A + "/canales").json()[0]["encargos"]}
ok(en[otro["id"]]["puerta"] is None and en[otro["id"]]["ronda"] == 0, "un encargo en marcha aún no está en ninguna puerta")
ok(all(cli.get(A + r).status_code == 404 for r in ("/webs", "/metricas/demo", "/cambios/demo")), "las rutas que no se han portado no existen")
sys.exit(1 if fallos else 0)
