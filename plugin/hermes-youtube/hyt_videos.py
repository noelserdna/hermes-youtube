"""Los vídeos de un canal: en qué estado está cada uno, cuáles se han grabado y publicado, y la entrega del paquete.

Un vídeo nace cuando alguien elige un tema (su encargo de título y miniatura) y sigue en su encargo de guion. El estado
visible se deduce de esos encargos y de sus puertas; nadie lo escribe a mano, salvo «grabado» y «publicado», que marca
una persona.

  Elegido → Título y miniatura elegidos → En revisión de marketing → En verificación de datos →
  En revisión de quien presenta → Aprobado → Grabado → Publicado        (y Rehaciendo o Descartado por el camino)

  canales/<canal>/videos.json     {"marcas": {encargo: {estado, fecha, url, quien}}, "publicados": [{id, titulo, pilar, url, fecha}]}

  hyt_videos.py lista <canal>
  hyt_videos.py grabado|publicado <canal> <encargo> [url]
  hyt_videos.py exportar <canal> <encargo> guion|titulo|descripcion|miniatura
  hyt_videos.py publicados <canal>
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str):
    if nombre in sys.modules:
        return sys.modules[nombre]
    spec = importlib.util.spec_from_file_location(nombre, AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


B = _cargar("hyt_base")
C = _cargar("hyt_canales")
E = _cargar("hyt_encargos")
T = _cargar("hyt_texto")
Rechazo = B.Rechazo

EMPAQUE, GUION = "titulo-miniatura", "guion"       # las dos pipelines por las que pasa un vídeo
GUIONES = (GUION, "guion-investigado")              # las versiones del guion (gemelos: una se elige)
ESTADOS = {"elegido": "Elegido", "titulo-elegido": "Título y miniatura elegidos", "eligiendo": "Eligiendo versión",
           "revision": "En revisión de marketing",
           "datos": "En verificación de datos", "revision-final": "En revisión de quien presenta",
           "rehaciendo": "Rehaciendo", "aprobado": "Aprobado", "grabado": "Grabado", "publicado": "Publicado",
           "descartado": "Descartado"}
ORDEN = list(ESTADOS)
PARTES = ("guion", "titulo", "descripcion", "miniatura")
ABIERTOS = ("elegido", "titulo-elegido", "eligiendo", "revision", "datos", "revision-final", "rehaciendo", "aprobado", "grabado")


def _fichero(slug: str) -> Path:
    return C.carpeta(slug) / "videos.json"


def _datos(slug: str) -> dict:
    d = B.leer(_fichero(slug), None) or {}
    return {"marcas": d.get("marcas") or {}, "publicados": d.get("publicados") or []}


def _json(f: Path, defecto=None):
    return _cargar("hyt_pasos")._json(f, defecto)


def _ultimo_fallo(slug: str, eid: str) -> str:
    f = C.carpeta(slug) / "etapas.jsonl"
    motivo = ""
    if f.exists():
        for linea in f.read_text(encoding="utf-8").splitlines():
            try:
                x = json.loads(linea)
            except ValueError:
                continue
            if x.get("encargo") == eid and x.get("resultado") not in ("done", "cambios"):
                motivo = f"{x.get('etapa', '?')}: {str(x.get('motivo') or '')[:300]}"
            elif x.get("encargo") == eid:
                motivo = ""
    return motivo


def _titulo(slug: str, enc: dict) -> str:
    el = _json(E.carpeta(slug, enc["id"]) / "eleccion.json", {}) or {}
    return el.get("titulo") or (enc.get("params") or {}).get("tema", "") or enc["id"]


def _estado(slug: str, enc: dict, marcas: dict) -> tuple:
    """(estado_id, incidencia, preparando) de un encargo de vídeo."""
    est, guion = enc.get("estado"), enc.get("pipeline") in GUIONES or bool(enc.get("gemelos"))
    sit = E.situacion(enc)
    incidencia = _ultimo_fallo(slug, enc["id"]) or "parado" if est == "parado" else ""
    if est == "descartado":
        return "descartado", str(enc.get("descartado_motivo") or ""), False
    if not guion:
        return "elegido", incidencia, est in ("en-curso", "en-vuelta")
    if est in ("cerrado", "hecho"):
        return (marcas.get(enc["id"]) or {}).get("estado") or "aprobado", "", False
    if est == "en-puerta" and enc.get("puerta_id") and not enc.get("gemelos_resuelto") and enc.get("gemelos"):
        return "eligiendo", "", False
    if est == "en-puerta" and sit["puerta"]:
        tipo = sit["puerta"]["tipo"]
        return (tipo if tipo in ESTADOS else "revision"), "", False
    if est == "esperando-gemelo":
        return "titulo-elegido", "", True
    rehecho = sit["ronda"] > 0 or int(enc.get("relanzamientos") or 0) > 0
    return ("rehaciendo" if rehecho else "titulo-elegido"), incidencia, est in ("en-curso", "en-vuelta")


def lista(slug: str) -> list:
    """Todos los vídeos del canal, en marcha y terminados, del más reciente al más antiguo."""
    encargos = [e for e in E.listar(slug) if e.get("pipeline") in (EMPAQUE, *GUIONES) or e.get("gemelos")]
    con_guion = {e.get("origen") for e in encargos if (e.get("pipeline") in GUIONES or e.get("gemelos")) and e.get("origen")}
    # gemelos (versiones del mismo guion): un solo vídeo. Manda la versión elegida; antes, la primera que siga viva.
    por_id = {e["id"]: e for e in encargos}
    fuera = set()
    for e in encargos:
        ids = e.get("gemelos") or []
        if len(ids) < 2 or e["id"] in fuera:
            continue
        grupo = [por_id[x] for x in ids if x in por_id]
        rep = next((g for g in grupo if g.get("gemelos_resuelto") and g.get("estado") != "descartado"), None) \
            or next((g for g in sorted(grupo, key=lambda g: g.get("version_letra") or "Z") if g.get("estado") != "descartado"), None) \
            or grupo[0]
        fuera |= {g["id"] for g in grupo if g["id"] != rep["id"]}
    encargos = [e for e in encargos if e["id"] not in fuera]
    marcas = _datos(slug)["marcas"]
    tope = E.rondas_max(slug)
    out = []
    for e in encargos:
        if e.get("pipeline") == EMPAQUE and e["id"] in con_guion:
            continue                                    # su vida sigue en el encargo de guion
        est, incidencia, preparando = _estado(slug, e, marcas)
        sit = E.situacion(e)
        puerta = {"id": e.get("puerta_id", ""), "tipo": sit["puerta"]["tipo"], "papel": sit["puerta"]["papel"]} if sit["puerta"] else None
        if est == "eligiendo":
            try:
                g = _cargar("hyt_puertas").leer(e["puerta_id"])
            except Exception:   # noqa: BLE001
                g = {}
            puerta = {"id": e["puerta_id"], "tipo": "elegir-version", "papel": g.get("papel") or "marketing"}
        out.append({"encargo": e["id"], "titulo": _titulo(slug, e), "pilar": (e.get("params") or {}).get("pilar", ""),
                    "version": e.get("version") or "", "estado": ESTADOS[est], "estado_id": est, "ronda": sit["ronda"], "rondas_max": tope, "puerta": puerta,
                    "incidencia": incidencia, "preparando": preparando,
                    "actualizado": (marcas.get(e["id"]) or {}).get("fecha") or e.get("creado", "")})
    return sorted(out, key=lambda v: v["actualizado"], reverse=True)


def _video(slug: str, eid: str) -> dict:
    v = next((x for x in lista(slug) if x["encargo"] == eid), None)
    if not v:
        raise Rechazo(f"No hay ningún vídeo «{eid}» en {slug}")
    return v


def siguiente(slug: str, excepto: str = "") -> str:
    """El título de otro vídeo ya elegido y sin publicar: a donde puede llevar el cierre de un guion."""
    for v in sorted(lista(slug), key=lambda x: -ORDEN.index(x["estado_id"])):
        if v["encargo"] != excepto and v["estado_id"] in ABIERTOS and v["titulo"]:
            return v["titulo"]
    return ""


def publicados(slug: str) -> list:
    return sorted(_datos(slug)["publicados"], key=lambda p: p.get("fecha", ""), reverse=True)


def publicado_poner(slug: str, datos: dict, quien: str = "") -> dict:
    """Alta o edición (por `id`) de un vídeo publicado. La lista sirve para avisar de temas parecidos."""
    titulo = str(datos.get("titulo") or "").strip()
    if not titulo:
        raise Rechazo("Un vídeo publicado necesita al menos su título")
    with B.cerrojo("videos"):
        d = _datos(slug)
        ident = str(datos.get("id") or "").strip() or "v-" + re.sub(r"[^a-z0-9]+", "-", T.plano(titulo).replace("ñ", "n")).strip("-")[:50]
        nuevo = {"id": ident, "titulo": titulo, "pilar": str(datos.get("pilar") or ""), "url": str(datos.get("url") or ""),
                 "fecha": str(datos.get("fecha") or B.ahora()[:10])}
        d["publicados"] = [p for p in d["publicados"] if p.get("id") != ident] + [nuevo]
        B.escribir(_fichero(slug), d)
    B.anotar(C.carpeta(slug) / "acciones.jsonl", {"ts": B.ahora(), "accion": "publicado-poner", "id": ident, "quien": quien})
    return nuevo


def publicado_quitar(slug: str, ident: str, quien: str = "") -> None:
    with B.cerrojo("videos"):
        d = _datos(slug)
        if not any(p.get("id") == ident for p in d["publicados"]):
            raise Rechazo(f"No hay ningún vídeo publicado «{ident}»")
        d["publicados"] = [p for p in d["publicados"] if p.get("id") != ident]
        B.escribir(_fichero(slug), d)
    B.anotar(C.carpeta(slug) / "acciones.jsonl", {"ts": B.ahora(), "accion": "publicado-quitar", "id": ident, "quien": quien})


def marcar(slug: str, eid: str, estado: str, quien: str = "", url: str = "") -> dict:
    """«grabado» o «publicado», a mano. Al publicarlo entra solo en la lista de publicados."""
    if estado not in ("grabado", "publicado"):
        raise Rechazo("Solo se marcan a mano «grabado» y «publicado»")
    v = _video(slug, eid)
    if v["estado_id"] not in ("aprobado", "grabado", "publicado"):
        raise Rechazo(f"«{v['titulo']}» está en «{v['estado']}»: solo se marca un vídeo aprobado")
    with B.cerrojo("videos"):
        d = _datos(slug)
        d["marcas"][eid] = {"estado": estado, "fecha": B.ahora(), "url": url, "quien": quien}
        B.escribir(_fichero(slug), d)
    if estado == "publicado":
        publicado_poner(slug, {"id": eid, "titulo": v["titulo"], "pilar": v["pilar"], "url": url}, quien)
        B.anotar(C.carpeta(slug) / "temas.jsonl", {"ts": B.ahora(), "encargo": eid, "titulo": v["titulo"], "pilar": v["pilar"],
                                                   "estado": "publicado"})
    return _video(slug, eid)


def _miniatura(m: dict | None) -> str:
    if not m:
        return "(sin idea de miniatura elegida)"
    pres, comp = m.get("presentador") or {}, m.get("composicion") or {}
    filas = [("Qué se ve", m.get("que_se_ve")), ("Elementos", ", ".join(m.get("elementos") or [])),
             ("Texto", m.get("texto")), ("Texto alternativo", m.get("texto_alternativo")),
             ("Expresión", pres.get("expresion")), ("Mirada", pres.get("mirada")), ("Foto que hay que hacer", pres.get("foto_a_pedir")),
             ("Composición", " · ".join(str(x) for x in (comp.get("tipo"), comp.get("foco"), comp.get("fondo")) if x)),
             ("Qué dice el título y qué la miniatura", m.get("reparto")), ("Qué no revela", m.get("no_revela")),
             ("Tiene que leerse en el móvil", m.get("legible_en_movil")), ("Evitar", m.get("evitar")),
             ("Marca", m.get("marca")), ("Nota de quien la eligió", m.get("nota_de_la_persona"))]
    return "\n".join(f"{k}: {v}" for k, v in filas if v) + "\n"


def exportar(slug: str, eid: str, parte: str) -> str:
    """Una parte del paquete de un vídeo aprobado, en texto limpio: lista para copiar."""
    if parte not in PARTES:
        raise Rechazo("Se exporta: " + ", ".join(PARTES))
    v = _video(slug, eid)
    if v["estado_id"] not in ("aprobado", "grabado", "publicado"):
        raise Rechazo(f"«{v['titulo']}» está en «{v['estado']}»: el paquete se entrega cuando está aprobado")
    d = E.carpeta(slug, eid)
    el = _json(d / "eleccion.json", {}) or {}
    if parte == "titulo":
        return el.get("titulo", "") + "\n"
    if parte == "miniatura":
        return _miniatura(el.get("miniatura"))
    if parte == "descripcion":
        return (d / "descripcion.md").read_text(encoding="utf-8")
    return _cargar("hyt_pasos").limpio((d / "guion.md").read_text(encoding="utf-8"))   # sin marcas ni comentarios


def al_aprobar(slug: str, eid: str) -> None:
    """Un guion acaba de aprobarse del todo: el canal aprende de él. Se guarda como ejemplo de voz, se apunta cómo
    abría (para no abrir igual el siguiente) y sus piezas quedan marcadas como usadas en el inventario."""
    d = E.carpeta(slug, eid)
    if not (d / "guion.md").exists():
        return
    P = _cargar("hyt_pasos")
    guion = (d / "guion.md").read_text(encoding="utf-8")
    dest = C.carpeta(slug) / "guiones"
    dest.mkdir(exist_ok=True)
    (dest / f"{eid}.txt").write_text(P.limpio(guion), encoding="utf-8")
    intro = dict(T.bloques(guion)).get("intro", "")
    primeras = T.frases(T.sin_marcas(intro))
    formulas = ((_json(d / "escaleta.json", {}) or {}).get("intro") or {}).get("ganchos") or []
    if primeras:
        B.anotar(C.carpeta(slug) / "aperturas.jsonl", {"ts": B.ahora(), "encargo": eid, "frase": primeras[0], "formulas": formulas})
    citas = {" ".join(T.plano(str(m.get("cita", ""))).split()) for m in (_json(d / "material.json", {}) or {}).get("material") or []}
    usadas = {int(n) for n in re.findall(r"\[(\d+)\]", guion)}
    citas_usadas = {" ".join(T.plano(str(m.get("cita", ""))).split())
                    for m in (_json(d / "material.json", {}) or {}).get("material") or [] if m.get("n") in usadas} or citas
    with B.cerrojo("inventario"):
        inv = P.inventario(slug)
        for p in inv["piezas"]:
            propia = " ".join(T.plano(str(p.get("cita", ""))).split())
            if propia and any(propia in c or c in propia for c in citas_usadas if c) and eid not in (p.get("usado_en") or []):
                p["usado_en"] = (p.get("usado_en") or []) + [eid]
        B.escribir(C.carpeta(slug) / "inventario.json", inv)
    B.anotar(C.carpeta(slug) / "temas.jsonl", {"ts": B.ahora(), "encargo": eid, "titulo": _titulo(slug, E.leer(slug, eid)),
                                               "pilar": (E.leer(slug, eid).get("params") or {}).get("pilar", ""), "estado": "aprobado"})


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(a) == 2 and a[0] == "lista":
            for v in lista(a[1]):
                extra = (f" · ronda {v['ronda']}/{v['rondas_max']}" if v["ronda"] else "") + \
                        (" · preparando" if v["preparando"] else "") + (f" · ⚠️ {v['incidencia']}" if v["incidencia"] else "")
                print(f"{v['estado']:<32} {v['pilar']:<10} {v['titulo']}  ({v['encargo']}){extra}")
        elif len(a) >= 3 and a[0] in ("grabado", "publicado"):
            v = marcar(a[1], a[2], a[0], url=a[3] if len(a) > 3 else "")
            print(f"{v['estado']}: {v['titulo']}")
        elif len(a) == 4 and a[0] == "exportar":
            sys.stdout.write(exportar(a[1], a[2], a[3]))
        elif len(a) == 2 and a[0] == "publicados":
            for p in publicados(a[1]):
                print(f"{p['fecha']}  {p['pilar']:<10} {p['titulo']}  {p['url']}")
        else:
            print(__doc__)
            return 1
    except Rechazo as e:
        print(f"No se puede: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
