"""hermes-youtube — medio DASHBOARD: la pestaña «YouTube» del panel web de Hermes (/api/plugins/hermes-youtube/).

Solo lectura por ahora: enseña los canales, lo que tienen en marcha y las puertas, pero NO decide (las puertas se
deciden en Telegram o en local). La identidad sale de la sesión del panel (con login: el email o el id de la cuenta;
en modo local, 127.0.0.1 y sin login: el usuario del sistema). Debe figurar en aprobadores.json con el medio
"dashboard". Copiado y adaptado de hermes-sdd (dashboard/plugin_api.py).

El panel completo (vídeos con su estado y su ronda, verificación de datos uno a uno, publicados y acciones) llega en
un paso posterior: sus rutas irán aquí.
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
