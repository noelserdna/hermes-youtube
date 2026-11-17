"""hermes-youtube — medio DASHBOARD: la pestaña «YouTube» del panel web de Hermes (/api/plugins/hermes-youtube/).

Enseña los canales, sus vídeos con su estado, las puertas y los publicados, y deja hacer desde el panel lo que es del
panel: verificar los datos uno a uno (quien tiene el papel de esa puerta), dar la puerta de datos por verificada, llevar
la lista de publicados y las acciones de marketing (pedir una propuesta, un tema propio, marcar grabado o publicado y
exportar un vídeo aprobado). Las demás puertas se deciden por correo o en Telegram: aquí son de solo lectura.

También enseña la configuración entera de cada canal (sin claves) y deja cambiar solo lo seguro: los números de sus
reglas, sus listas de textos y el pie de la descripción. Las personas, sus papeles, los ejecutores, los modelos y lo que
el canal permite no se cambian desde el panel (con la coordinadora). Cada cambio queda en config.jsonl del canal con
«panel:<persona>».

La identidad sale de la sesión del panel (con login: el email o el id de la cuenta; en modo local, 127.0.0.1 y sin
login: el usuario del sistema). Debe figurar en aprobadores.json con el medio "dashboard". Copiado y adaptado de
hermes-sdd (dashboard/plugin_api.py).
"""
from __future__ import annotations

import getpass
import importlib.util
import json
import re
import socket
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

AQUI = Path(__file__).resolve().parent.parent


def _cargar(nombre: str):
    if nombre in sys.modules:
        return sys.modules[nombre]
    spec = importlib.util.spec_from_file_location(nombre, AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


B, C, PU, E = _cargar("hyt_base"), _cargar("hyt_canales"), _cargar("hyt_puertas"), _cargar("hyt_encargos")
router = APIRouter()
CAMPOS = ("id", "tipo", "canal", "encargo", "titulo", "texto", "opciones", "estado", "creada", "firmar_en", "error",
          "firma", "resultado", "papel", "indice", "total", "ronda")


def _actor(request: Request) -> tuple:
    sesion = getattr(request.state, "session", None)
    if sesion is not None:
        ident, prueba = (sesion.email or sesion.user_id), {"proveedor": sesion.provider, "cuenta": sesion.user_id}
    elif getattr(request.state, "native_http_principal", None) and getattr(request.app.state, "auth_required", None) is False:
        ident, prueba = getpass.getuser(), {"modo": "desktop", "host": socket.gethostname().split(".")[0]}
    else:
        local = getattr(request.app.state, "auth_required", None) is False
        origen = request.client.host if request.client else ""
        if not local or origen not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(403, "sin sesión del panel no hay persona autorizada")
        ident, prueba = getpass.getuser(), {"modo": "local", "host": socket.gethostname().split(".")[0]}
    persona, _ = PU.persona_de("dashboard", ident)
    if not persona:
        raise HTTPException(403, f"{ident} no figura en aprobadores.json con el medio dashboard")
    return persona, ident, prueba


def _marketing(request: Request, slug: str) -> tuple:
    """Las acciones del panel son de marketing: quien tiene ese papel en el canal, o quien administra (autorizado en
    todos los canales y sin entrada entre las personas de este)."""
    persona, ident, prueba = _actor(request)
    try:
        en_canal = (C.leer(slug).get("personas") or {}).get(persona)
    except B.Rechazo as e:
        raise HTTPException(404, str(e))
    if not PU.puede_decidir(persona, slug):
        raise HTTPException(403, "no estás autorizado en este canal")
    if en_canal is None:
        if "*" not in ((B.leer(B.home() / "aprobadores.json", {}) or {}).get(persona) or {}).get("canales", ["*"]):
            raise HTTPException(403, "esta acción es de quien lleva marketing en el canal")
    elif "marketing" not in (en_canal.get("roles") or []):
        raise HTTPException(403, "esta acción es de quien lleva marketing en el canal")
    return persona, ident, prueba


def _V():
    return _cargar("hyt_videos")


async def _cuerpo(request: Request) -> dict:
    try:
        d = await request.json()
    except Exception:   # noqa: BLE001
        d = {}
    return d if isinstance(d, dict) else {}


def _accion(f):
    try:
        return f()
    except B.Rechazo as e:
        raise HTTPException(409, str(e))


def _vista(p: dict) -> dict:
    v = {k: p.get(k) for k in CAMPOS}
    v["decision"] = {k: (p.get("decision") or {}).get(k) for k in ("verbo", "texto", "at")}
    v["decidio"] = ((p.get("decision") or {}).get("actor") or {}).get("persona")
    v["datos_pendientes"] = PU.datos_pendientes(p)
    return v


@router.get("/canales")
async def canales(request: Request):
    _actor(request)
    def hacer():
        out = []
        for s in C.listar():
            cfg = C.leer(s)
            abiertos = E.listar(s, abiertos=True)
            pend = [p for p in PU.puertas(("abierta", "decidida", "error")) if p["canal"] == s]
            out.append({"slug": s, "nombre": cfg["nombre"], "presentador": cfg.get("presentador", ""),
                        "idioma": cfg.get("idioma", ""), "pilares": [p.get("nombre") for p in cfg.get("pilares") or []],
                        "pilares_id": [p.get("id") for p in cfg.get("pilares") or []],
                        "capacidades": sorted(C.capacidades(cfg)), "pausado": bool((cfg.get("politicas") or {}).get("pausado")),
                        "encargos": [{"id": e["id"], "nombre": e["nombre"], "estado": e.get("estado"), **E.situacion(e)}
                                     for e in abiertos],   # ronda y, si espera en una, su puerta (tipo, papel, n de m)
                        "puertas": len(pend)})
        return out
    return await run_in_threadpool(hacer)


@router.get("/sistema")
async def sistema(request: Request):
    _actor(request)
    return await run_in_threadpool(lambda: {"disco": B.disco()})


@router.get("/puertas")
async def puertas(request: Request):
    _actor(request)
    return [_vista(p) for p in PU.puertas(("abierta", "decidida", "error"))]


# ── vídeos ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@router.get("/videos/{slug}")
async def videos(slug: str, request: Request):
    _actor(request)
    return await run_in_threadpool(lambda: _accion(lambda: (C.leer(slug), _V().lista(slug))[1]))


# ── datos por verificar ─────────────────────────────────────────────────────────────────────────────────────────────
CAMPOS_DATO = ("id", "dato", "frase", "motivo", "fuente", "versiones", "estado", "valor")


@router.get("/datos")
async def datos(request: Request):
    persona, _, _ = _actor(request)
    def hacer():
        out = []
        for p in PU.puertas(("abierta",)):
            if p.get("tipo") != "datos" or not p.get("encargo"):
                continue
            out.append({"puerta": p["id"], "canal": p["canal"], "encargo": p["encargo"], "titulo": p["titulo"],
                        "papel": p.get("papel", ""), "pendientes": PU.datos_pendientes(p),
                        "puedes": PU.puede_decidir(persona, p["canal"], p.get("papel", ""), "dashboard"),
                        "datos": [{k: x.get(k) for k in CAMPOS_DATO} for x in PU.datos_de(p)]})
        return out
    return await run_in_threadpool(hacer)


@router.post("/datos/{puerta}/aprobar")
async def datos_aprobar(puerta: str, request: Request):
    persona, ident, prueba = _actor(request)
    def hacer():
        p = PU.leer(puerta)
        if p.get("tipo") != "datos":
            raise B.Rechazo("Desde el panel solo se decide la puerta de datos")
        return _vista(PU.decidir(puerta, "acepto", "", persona, "dashboard", ident, prueba))
    return await run_in_threadpool(lambda: _accion(hacer))


@router.post("/datos/{puerta}/{dato}")
async def datos_verificar(puerta: str, dato: str, request: Request):
    persona, ident, _ = _actor(request)
    c = await _cuerpo(request)
    def hacer():
        d = PU.verificar_dato(puerta, dato, str(c.get("estado") or ""), str(c.get("valor") or ""), persona, "dashboard", ident)
        return {"dato": {k: d.get(k) for k in CAMPOS_DATO}, "pendientes": PU.datos_pendientes(PU.leer(puerta))}
    return await run_in_threadpool(lambda: _accion(hacer))


# ── publicados ──────────────────────────────────────────────────────────────────────────────────────────────────────
@router.get("/publicados/{slug}")
async def publicados(slug: str, request: Request):
    _actor(request)
    return await run_in_threadpool(lambda: _accion(lambda: (C.leer(slug), _V().publicados(slug))[1]))


@router.post("/publicados/{slug}")
async def publicado_poner(slug: str, request: Request):
    persona, _, _ = _marketing(request, slug)
    c = await _cuerpo(request)
    datos_ = {k: str(c[k]).strip() for k in ("id", "titulo", "pilar", "url", "fecha") if str(c.get(k) or "").strip()}
    return await run_in_threadpool(lambda: _accion(lambda: _V().publicado_poner(slug, datos_, persona)))


@router.delete("/publicados/{slug}/{ident}")
async def publicado_quitar(slug: str, ident: str, request: Request):
    persona, _, _ = _marketing(request, slug)
    return await run_in_threadpool(lambda: _accion(lambda: (_V().publicado_quitar(slug, ident, persona), {"ok": True})[1]))


# ── acciones de marketing ───────────────────────────────────────────────────────────────────────────────────────────
def _lanzado(e: dict) -> dict:
    return {"encargo": e["id"], "nombre": e.get("nombre", ""), "duplicado": bool(e.get("duplicado"))}


@router.post("/acciones/{slug}/propuesta")
async def accion_propuesta(slug: str, request: Request):
    persona, _, _ = _marketing(request, slug)
    return await run_in_threadpool(lambda: _accion(lambda: _lanzado(E.lanzar(slug, "propuesta", {}, quien=f"{persona} (panel)"))))


@router.post("/acciones/{slug}/tema")
async def accion_tema(slug: str, request: Request):
    persona, _, _ = _marketing(request, slug)
    c = await _cuerpo(request)
    def hacer():
        tema, pilar = str(c.get("tema") or "").strip(), str(c.get("pilar") or "").strip()
        if not tema:
            raise B.Rechazo("Falta el tema")
        pilares = [x.get("id") for x in C.leer(slug).get("pilares") or [] if isinstance(x, dict)]
        if pilar and pilares and pilar not in pilares:
            raise B.Rechazo(f"No conozco el pilar «{pilar}». Los de este canal: {', '.join(pilares)}")
        return _lanzado(E.lanzar(slug, "titulo-miniatura", {"tema": tema[:200], "pilar": pilar or "sin-pilar"},
                                 brief=f"Tema propio, pedido desde el panel por {persona}.", quien=f"{persona} (panel)"))
    return await run_in_threadpool(lambda: _accion(hacer))


@router.post("/acciones/{slug}/marcar")
async def accion_marcar(slug: str, request: Request):
    persona, _, _ = _marketing(request, slug)
    c = await _cuerpo(request)
    def hacer():
        if c.get("estado") not in ("grabado", "publicado"):
            raise B.Rechazo("Se marca como grabado o como publicado")
        return _V().marcar(slug, str(c.get("encargo") or ""), c["estado"], persona, str(c.get("url") or ""))
    return await run_in_threadpool(lambda: _accion(hacer))


@router.get("/exportar/{slug}/{encargo}/{parte}")
async def exportar(slug: str, encargo: str, parte: str, request: Request):
    _marketing(request, slug)
    return await run_in_threadpool(lambda: _accion(lambda: {"parte": parte, "texto": _V().exportar(slug, encargo, parte)}))


# ── configuración de cada canal: se ve entera (sin claves); solo se cambia lo seguro ────────────────────────────────
# (clave, etiqueta, tipo, ayuda). tipo: numero | rango | lista | texto. Lo que no está aquí no se cambia desde el panel.
EDITABLES = [
    ("reglas.minutos", "Duración del vídeo (minutos)", "rango", "Mínimo y máximo, p. ej. 13-15."),
    ("reglas.ppm", "Palabras por minuto", "numero", "El ritmo con el que se calcula la duración del guion."),
    ("reglas.ppm_medido", "Palabras por minuto medidas", "numero", "Las de quien presenta, medidas en sus vídeos; 0 = sin medir."),
    ("reglas.titulo_max", "Largo máximo del título (caracteres)", "numero", ""),
    ("reglas.titulos_internos", "Títulos que se generan", "numero", "Los que se barajan antes de elegir."),
    ("reglas.titulos_presentados", "Títulos que se presentan", "numero", "No puede ser mayor que los que se generan."),
    ("reglas.miniaturas", "Miniaturas que se proponen", "numero", ""),
    ("reglas.intro_max_palabras", "Largo máximo de la intro (palabras)", "numero", ""),
    ("reglas.promesa_extra_palabras", "Palabras de más para la promesa", "numero", ""),
    ("reglas.rondas_max", "Rondas de cambios como máximo", "numero", ""),
    ("reglas.temas_por_pilar", "Temas por pilar en cada propuesta", "numero", ""),
    ("reglas.reenganches", "Reenganches en el guion", "numero", ""),
    ("formatos", "Formatos de vídeo", "lista", "Uno por línea."),
    ("prohibidas", "Palabras y expresiones prohibidas", "lista", "Una por línea."),
    ("cierres_prohibidos", "Cierres prohibidos", "lista", "Uno por línea."),
    ("titulo_cliches", "Clichés de título que no se usan", "lista", "Uno por línea."),
    ("nombres_vetados", "Nombres que no se mencionan", "lista", "Uno por línea."),
    ("descripcion_pie", "Pie de la descripción", "texto", "Lo que va al final de la descripción de cada vídeo."),
]
EDITABLE = {c: t for c, _, t, _ in EDITABLES}
NO_PANEL = ("Eso no se cambia desde el panel: las personas, sus papeles, los ejecutores, los modelos, lo que el canal "
            "permite y las claves, con la coordinadora.")


def _valor(cfg: dict, clave: str):
    v = cfg
    for p in clave.split("."):
        v = v.get(p) if isinstance(v, dict) else None
    return v


def _como_trabaja(slug: str, cfg: dict) -> list:
    PL, M = _cargar("hyt_pipelines"), _cargar("hyt_modelos")
    propios = cfg.get("ejecutores") or {}
    out = []
    for pid, p in sorted(PL.listar(slug).items()):
        etapas = []
        for s in p.get("etapas", []):
            if not isinstance(s, dict) or not s.get("id"):
                continue
            ej = propios.get(s["id"]) or s.get("ejecutor", "hermes")
            try:
                mod = M.para(s["id"], ej, slug, s.get("perfil"))
            except Exception:   # noqa: BLE001
                mod = ""
            etapas.append({"id": s["id"], "skill": s.get("skill"), "ejecutor": "Claude Code" if ej == "claude" else "Hermes",
                           "modelo": mod or "el del perfil"})
        out.append({"id": pid, "nombre": p.get("nombre", pid), "propia": "/canales/" in str(p.get("_origen", "")),
                    "hereda": p.get("_hereda"), "etapas": etapas,
                    "puertas": [{"tipo": g.get("tipo"), "papel": g.get("papel", "")} for g in PL.puertas_de(p)]})
    return out


RESERVADO = ("telegram",)   # adónde se avisa: no se enseña en el panel, tampoco en el historial


def _historial(slug: str) -> list:
    out = []
    try:
        lineas = (C.carpeta(slug) / "config.jsonl").read_text().splitlines()[-15:]
    except OSError:
        return out
    for l in lineas:
        try:
            r = json.loads(l)
        except ValueError:
            continue
        clave = str(r.get("clave") or r.get("accion") or "")
        reservado = clave.split(".")[0] in RESERVADO   # se ve que cambió, no el valor
        out.append({"ts": r.get("ts"), "quien": r.get("quien"), "clave": clave,
                    "antes": "…" if reservado else json.dumps(r.get("antes"), ensure_ascii=False)[:160],
                    "despues": "…" if reservado else json.dumps(r.get("despues"), ensure_ascii=False)[:160]})
    return list(reversed(out))


@router.get("/config/{slug}")
async def ver_config(slug: str, request: Request):
    _actor(request)
    def hacer():
        cfg = _accion(lambda: C.leer(slug))
        pol, tr = cfg.get("politicas") or {}, cfg.get("transcripcion") or {}
        limites = {f"reglas.{k}": v for k, v in C.REGLAS.items()}
        editables = []
        for clave, etiqueta, tipo, ayuda in EDITABLES:
            e = {"clave": clave, "etiqueta": etiqueta, "tipo": tipo, "ayuda": ayuda, "valor": _valor(cfg, clave)}
            if clave in limites:
                e["min"], e["max"] = limites[clave]
            editables.append(e)
        return {
            "slug": slug, "nombre": cfg["nombre"],
            "canal": {"Nombre": cfg["nombre"], "Presenta": cfg.get("presentador"), "Idioma": cfg.get("idioma"),
                      "Zona horaria": cfg.get("zona_horaria"), "En pausa": "sí" if pol.get("pausado") else "no",
                      "Vídeos nuevos por semana (tope)": pol.get("tope_semanal") or "sin tope",
                      "Extensiones": ", ".join(cfg.get("extensiones") or [])},
            "pilares": [{"id": p.get("id"), "nombre": p.get("nombre"), "tipo": p.get("tipo", "pilar")}
                        for p in cfg.get("pilares") or [] if isinstance(p, dict)],
            "editables": editables,
            "vetos": {"Temas excluidos": [C.texto_patron(x) for x in cfg.get("excluido") or []],
                      "Promesas que no se hacen": [C.texto_patron(x) for x in cfg.get("sin_promesas") or []],
                      "Ruido de la transcripción": list(tr.get("ruido") or []),
                      "Correcciones de la transcripción": [f"{k} → {v}" for k, v in (tr.get("correcciones") or {}).items()]},
            "marca": {str(k): (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)) for k, v in (cfg.get("marca") or {}).items()},
            "personas": [{"clave": k, "nombre": p.get("nombre"), "correo": p.get("correo") or "", "roles": p.get("roles") or []}
                         for k, p in (cfg.get("personas") or {}).items() if isinstance(p, dict)],
            "permite": {k: bool(v) for k, v in (cfg.get("permite") or {}).items()},
            "capacidades": sorted(C.capacidades(cfg)),
            "como_trabaja": _como_trabaja(slug, cfg), "historial": _historial(slug),
        }
    return await run_in_threadpool(hacer)


def _numero(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(x)
    return int(x) if float(x).is_integer() else x


@router.post("/config/{slug}")
async def cambiar_config(slug: str, request: Request):
    cuerpo = await _cuerpo(request)
    clave, valor = cuerpo.get("clave"), cuerpo.get("valor")
    tipo = EDITABLE.get(clave) if isinstance(clave, str) else None
    if not tipo:
        _actor(request)   # quien no tiene acceso al panel ni se entera de qué claves hay
        raise HTTPException(403, NO_PANEL)
    persona, _, _ = _marketing(request, slug)
    if tipo == "numero":
        if isinstance(valor, str) and re.fullmatch(r"\s*-?\d+\s*", valor):
            valor = int(valor)
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise HTTPException(422, "Un número entero.")
    elif tipo == "rango":
        if isinstance(valor, str):
            valor = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", valor)]
        try:
            valor = [_numero(x) for x in valor]
        except (TypeError, ValueError):
            valor = None
        if not valor or len(valor) != 2:
            raise HTTPException(422, "Dos números: el mínimo y el máximo (p. ej. 13-15).")
    elif tipo == "lista":
        if isinstance(valor, str):
            valor = valor.splitlines()
        if not isinstance(valor, list) or not all(isinstance(x, str) and len(x) <= 300 for x in valor):
            raise HTTPException(422, "Una lista de textos, uno por línea (de hasta 300 caracteres).")
        valor = [x.strip() for x in valor if x.strip()]
        if len(valor) > 200:
            raise HTTPException(422, "Una lista de hasta 200 líneas.")
    elif tipo == "texto":
        if not isinstance(valor, str) or len(valor) > 4000:
            raise HTTPException(422, "Un texto de hasta 4.000 caracteres.")
        valor = json.dumps(valor.strip(), ensure_ascii=False)   # C.config lee los textos como JSON: así «42» sigue siendo un texto
    def hacer():
        _accion(lambda: C.config(slug, clave, valor, f"panel:{persona}"))
        return {"ok": True}
    return await run_in_threadpool(hacer)
