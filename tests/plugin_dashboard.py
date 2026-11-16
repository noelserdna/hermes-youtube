"""API de la pestaña YouTube con un panel falso (sesión inyectada): identidad, canales, puertas (solo lectura), disco,
vídeos, datos por verificar (por papel), publicados y las acciones de marketing."""
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
ok(all(x in js for x in ('"/videos/"', '"/datos"', '"/datos/" + p.puerta + "/aprobar"', '"/publicados/"', '"/acciones/"', '"/exportar/"', "navigator.clipboard", ".select()"))
   and all(f'["{n}"' in js for n in ("Canales", "Vídeos", "Datos por verificar", "Publicados", "Acciones", "Decisiones")),
   "la pestaña tiene sus seis secciones, llama a las rutas nuevas y copia con el portapapeles (o seleccionando el texto)")

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
                            "pilares": ["El oficio"], "pilares_id": ["oficio"], "capacidades": ["pilares"], "pausado": False, "encargos": [], "puertas": 1},
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

# ── vídeos ──
vs = cli.get(A + "/videos/demo").json()
v = next(x for x in vs if x["encargo"] == e["id"])
ok(v["estado_id"] == "datos" and v["estado"] == "En verificación de datos" and v["ronda"] == 2 and v["puerta"] == {"id": gd, "tipo": "datos", "papel": "datos"},
   f"vídeos: cada uno con su estado visible, su ronda y la puerta en la que espera ({v})")
ok(cli.get(A + "/videos/no-existe").status_code == 409, "los vídeos de un canal que no existe: 409")

# ── datos por verificar: uno a uno, por quien tiene el papel de esa puerta ──
(m.E.carpeta("demo", e["id"]) / "datos.json").write_text(json.dumps({"datos": [
    {"id": "d1", "dato": "El 60 % del agua", "frase": "Con un sesenta por ciento basta.", "motivo": "externo", "fuente": "charlas/v01", "versiones": ["60", "65"], "estado": "pendiente", "valor": ""},
    {"id": "d2", "dato": "Desde 2019", "frase": "Lo hago desde 2019.", "motivo": "externo", "fuente": "", "estado": "pendiente", "valor": ""},
    {"id": "d3", "dato": "Tres cazuelas", "estado": "pendiente"}]}))
d = cli.get(A + "/datos").json()
ok(len(d) == 1 and d[0]["puerta"] == gd and d[0]["pendientes"] == 3 and d[0]["papel"] == "datos" and d[0]["puedes"] is False
   and d[0]["datos"][0] == {"id": "d1", "dato": "El 60 % del agua", "frase": "Con un sesenta por ciento basta.", "motivo": "externo", "fuente": "charlas/v01",
                            "versiones": ["60", "65"], "estado": "pendiente", "valor": ""},
   "datos por verificar: cada puerta de datos abierta con sus datos (frase, motivo y fuente); quien administra los ve pero no los verifica desde el panel")
r = cli.post(A + f"/datos/{gd}/d1", json={"estado": "verificado"})
ok(r.status_code == 409 and "papel «datos»" in r.json()["detail"], "sin el papel de la puerta no se verifica un dato (ni quien administra, por el panel)")
ap = json.loads((T / "home/aprobadores.json").read_text())
ap["bea"] = {"nombre": "Bea", "medios": {"dashboard": "bea@ejemplo.com"}, "canales": ["demo"]}
(T / "home/aprobadores.json").write_text(json.dumps(ap))
m.C.config("demo", "personas", {"ana": {"nombre": "Ana", "correo": "", "roles": ["datos", "marketing"]}, "bea": {"nombre": "Bea", "correo": "", "roles": ["presentador"]}})
ok(cli.get(A + "/datos").json()[0]["puedes"] is True, "con el papel «datos», sí")
r = cli.post(A + f"/datos/{gd}/d1", json={"estado": "verificado"}).json()
ok(r["dato"]["estado"] == "verificado" and r["pendientes"] == 2, "verificar un dato")
ok(cli.post(A + f"/datos/{gd}/d2", json={"estado": "corregido"}).status_code == 409, "corregir sin el valor correcto: 409")
r = cli.post(A + f"/datos/{gd}/d2", json={"estado": "corregido", "valor": "Desde 2018"}).json()
ok(r["dato"]["estado"] == "corregido" and r["dato"]["valor"] == "Desde 2018" and r["pendientes"] == 1, "corregir un dato con su valor")
ok(cli.post(A + f"/datos/{gd}/aprobar").status_code == 409 and m.PU.leer(gd)["estado"] == "abierta", "con datos pendientes no se da la puerta por verificada")
ok(cli.post(A + f"/datos/{gd}/d3", json={"estado": "eliminado"}).json()["pendientes"] == 0 and cli.post(A + f"/datos/{gd}/d9", json={"estado": "verificado"}).status_code == 409
   and cli.post(A + f"/datos/{gd}/d1", json={"estado": "dudoso"}).status_code == 409, "eliminar un dato; un dato o un estado que no existen: 409")
ev = [json.loads(l) for l in (T / "home/canales/demo/puertas.jsonl").read_text().splitlines()]
ok([(x["dato"], x["estado"], x["persona"], x["medio"]) for x in ev] == [("d1", "verificado", "ana", "dashboard"), ("d2", "corregido", "ana", "dashboard"), ("d3", "eliminado", "ana", "dashboard")],
   "cada dato verificado queda anotado, con quién y por el medio dashboard")
ok(cli.post(A + f"/datos/{g}/aprobar").status_code == 409 and m.PU.leer(g)["estado"] == "abierta", "desde el panel solo se decide la puerta de datos")
SESION["email"] = "bea@ejemplo.com"
ok(cli.post(A + f"/datos/{gd}/aprobar").status_code == 409 and cli.post(A + f"/datos/{gd}/d1", json={"estado": "eliminado"}).status_code == 409,
   "otra persona del canal sin ese papel no verifica ni aprueba")
SESION["email"] = "ana@ejemplo.com"
r = cli.post(A + f"/datos/{gd}/aprobar")
p = m.PU.leer(gd)
ok(r.status_code == 200 and r.json()["estado"] == "decidida" and p["decision"]["verbo"] == "acepto" and p["decision"]["actor"] == {"persona": "ana", "medio": "dashboard", "id": "ana@ejemplo.com"},
   "«Datos verificados» decide la puerta con la identidad del panel")
ok(cli.get(A + "/datos").json() == [], "y deja de estar entre los datos por verificar")

# ── publicados ──
r = cli.post(A + "/publicados/demo", json={"titulo": "El arroz que no se pasa", "pilar": "oficio", "url": "https://ejemplo.com/v/1", "fecha": "2026-10-01"})
pid = r.json()["id"]
ok(r.status_code == 200 and cli.get(A + "/publicados/demo").json() == [{"id": pid, "titulo": "El arroz que no se pasa", "pilar": "oficio", "url": "https://ejemplo.com/v/1", "fecha": "2026-10-01"}],
   "publicados: alta y lista")
cli.post(A + "/publicados/demo", json={"id": pid, "titulo": "El arroz que nunca se pasa", "pilar": "oficio"})
ps = cli.get(A + "/publicados/demo").json()
ok(len(ps) == 1 and ps[0]["titulo"] == "El arroz que nunca se pasa", "publicados: edición por su id")
ok(cli.post(A + "/publicados/demo", json={"pilar": "oficio"}).status_code == 409, "un publicado sin título: 409")
SESION["email"] = "bea@ejemplo.com"
ok(cli.get(A + "/publicados/demo").status_code == 200 and cli.post(A + "/publicados/demo", json={"titulo": "x"}).status_code == 403
   and cli.delete(A + f"/publicados/demo/{pid}").status_code == 403 and cli.post(A + "/acciones/demo/propuesta").status_code == 403
   and cli.post(A + "/acciones/demo/tema", json={"tema": "x"}).status_code == 403 and cli.get(A + f"/exportar/demo/{e['id']}/guion").status_code == 403,
   "quien no lleva marketing ve la lista, pero no la cambia ni lanza acciones")
SESION["email"] = "ana@ejemplo.com"
ok(cli.delete(A + f"/publicados/demo/{pid}").status_code == 200 and cli.get(A + "/publicados/demo").json() == [] and cli.delete(A + f"/publicados/demo/{pid}").status_code == 409,
   "publicados: baja; quitar uno que no está: 409")
ok(cli.post(A + "/publicados/no-existe", json={"titulo": "x"}).status_code == 404, "en un canal que no existe: 404")

# ── acciones de marketing ──
r = cli.post(A + "/acciones/demo/propuesta").json()
ok(r == {"encargo": otro["id"], "nombre": "Propuesta de temas", "duplicado": True}, f"pedir propuesta: si ya hay una en marcha, no lanza otra ({r})")
enc = m.E.leer("demo", otro["id"]); enc["estado"] = "descartado"; m.E.guardar("demo", enc)
r = cli.post(A + "/acciones/demo/propuesta").json()
ok(r["duplicado"] is False and m.E.leer("demo", r["encargo"])["quien"] == "ana (panel)", "pedir propuesta: la lanza a nombre de quien la pide")
ok(cli.post(A + "/acciones/demo/tema", json={"tema": "  "}).status_code == 409 and cli.post(A + "/acciones/demo/tema", json={"tema": "x", "pilar": "postres"}).status_code == 409,
   "tema propio: sin tema o con un pilar que no existe, 409")
r = cli.post(A + "/acciones/demo/tema", json={"tema": "El sofrito sin prisa", "pilar": "oficio"}).json()
t = m.E.leer("demo", r["encargo"])
ok(t["pipeline"] == "titulo-miniatura" and t["params"] == {"tema": "El sofrito sin prisa", "pilar": "oficio"} and t["quien"] == "ana (panel)", "tema propio: lanza título y miniatura con ese tema y su pilar")
ok(cli.post(A + "/acciones/demo/marcar", json={"encargo": e["id"], "estado": "grabado"}).status_code == 409 and cli.get(A + f"/exportar/demo/{e['id']}/guion").status_code == 409,
   "un vídeo que no está aprobado ni se marca ni se exporta")
ok(cli.post(A + "/acciones/demo/marcar", json={"encargo": e["id"], "estado": "aprobado"}).status_code == 409, "solo se marca grabado o publicado")
# un vídeo aprobado: se exporta, se marca grabado y, al publicarlo, entra en los publicados
ya = m.E.lanzar("demo", "guion", {"tema": "Caldo corto", "pilar": "oficio"}); dya = m.E.carpeta("demo", ya["id"])
(dya / "guion.md").write_text("## intro\nEl caldo no se hace solo. Se vigila.\n## cierre\nY eso es todo el secreto.\n")
(dya / "descripcion.md").write_text("Cómo hacer un caldo corto.\n\n00:00 El caldo\n")
(dya / "eleccion.json").write_text(json.dumps({"titulo": "Caldo corto: se vigila", "miniatura": {"n": 1, "que_se_ve": "Una olla al fuego", "texto": "VIGILA"}}))
enc = m.E.leer("demo", ya["id"]); enc["estado"] = "cerrado"; m.E.guardar("demo", enc)
x = {parte: cli.get(A + f"/exportar/demo/{ya['id']}/{parte}") for parte in ("guion", "titulo", "descripcion", "miniatura")}
ok(all(r.status_code == 200 and r.json()["parte"] == parte for parte, r in x.items()) and "El caldo no se hace solo." in x["guion"].json()["texto"] and "## intro" not in x["guion"].json()["texto"]
   and x["titulo"].json()["texto"].strip() == "Caldo corto: se vigila" and "00:00 El caldo" in x["descripcion"].json()["texto"] and "Una olla al fuego" in x["miniatura"].json()["texto"],
   "exportar las cuatro partes de un vídeo aprobado, en texto limpio")
ok(cli.get(A + f"/exportar/demo/{ya['id']}/todo").status_code == 409, "una parte que no existe: 409")
r = cli.post(A + "/acciones/demo/marcar", json={"encargo": ya["id"], "estado": "grabado"})
ok(r.status_code == 200 and r.json()["estado_id"] == "grabado", "marcar grabado")
r = cli.post(A + "/acciones/demo/marcar", json={"encargo": ya["id"], "estado": "publicado", "url": "https://ejemplo.com/v/2"})
pub = cli.get(A + "/publicados/demo").json()
ok(r.json()["estado_id"] == "publicado" and [(p["titulo"], p["url"]) for p in pub] == [("Caldo corto: se vigila", "https://ejemplo.com/v/2")], "marcar publicado: entra en la lista de publicados con su dirección")
ok(all(cli.get(A + r).status_code == 404 for r in ("/webs", "/metricas/demo", "/cambios/demo")), "las rutas que no se han portado no existen")
sys.exit(1 if fallos else 0)
