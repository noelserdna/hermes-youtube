"""hermes-youtube — medio DASHBOARD: la pestaña «YouTube» del panel web de Hermes (/api/plugins/hermes-youtube/).

Enseña los canales, sus vídeos con su estado, las puertas y los publicados, y deja hacer desde el panel lo que es del
panel: verificar los datos uno a uno (quien tiene el papel de esa puerta), dar la puerta de datos por verificada, llevar
la lista de publicados y las acciones de marketing (pedir una propuesta, un tema propio, marcar grabado o publicado y
exportar un vídeo aprobado). Las demás puertas se deciden por correo o en Telegram: aquí son de solo lectura.

La identidad sale de la sesión del panel (con login: el email o el id de la cuenta; en modo local, 127.0.0.1 y sin
login: el usuario del sistema). Debe figurar en aprobadores.json con el medio "dashboard". Copiado y adaptado de
hermes-sdd (dashboard/plugin_api.py).
"""
from __future__ import annotations

import getpass
import importlib.util
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
