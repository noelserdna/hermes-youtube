"""Revisión mecánica en cada puerta (sin IA). Copiado y adaptado de hermes-sdd (hsdd_revision.py).

Sale arriba del texto de la puerta como «🧭 Revisión: N aviso(s)». No bloquea a la persona, pero **un aviso grave
impide aprobar la puerta**: solo se puede rehacer o rechazar.

  hyt_revision.py revisar <canal> <encargo> <tipo>

Este módulo es el armazón: el registro de reglas por tipo de puerta (REGLAS) está vacío a propósito. Cada regla es
una función `regla(ctx, avisos)` que añade avisos con `_aviso(avisos, grave, codigo, texto)`; `ctx` trae
{canal, encargo_id, tipo, carpeta, encargo, cfg}. Se registra con el decorador:

    @regla("revision", "revision-final")
    def _duracion(ctx, avisos): ...

«*» como tipo la aplica a todas las puertas. Cada aviso: {grave: bool, codigo, texto}. Cada regla nueva se calibra
antes contra encargos reales: un aviso grave falso bloquea un guion bueno.
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


def _veredicto(f: Path) -> str:
    """APROBADO | CAMBIOS | "" según la última línea «VEREDICTO: …» del fichero."""
    try:
        texto = f.read_text(errors="replace")
    except OSError:
        return ""
    if str(f).endswith(".json"):   # las salidas estructuradas lo llevan en el campo «veredicto»
        try:
            v = str((json.loads(texto) or {}).get("veredicto") or "").strip().upper()
        except (ValueError, AttributeError):
            return ""
        return v if v in ("APROBADO", "CAMBIOS") else ""
    m = re.findall(r"VEREDICTO:\s*\**\s*(APROBADO|CAMBIOS)", texto, re.I)
    return m[-1].upper() if m else ""


def _aviso(lista: list, grave: bool, codigo: str, texto: str) -> None:
    lista.append({"grave": grave, "codigo": codigo, "texto": texto})


# Reglas por tipo de puerta: {tipo: [funciones]}. Las reglas en sí están en hyt_reglas.py (funciones puras, cada una
# con su prueba); aquí solo se decide cuáles tocan en cada puerta y sobre qué ficheros del encargo.
REGLAS: dict = {}


def regla(*tipos: str):
    """Decorador: registra una regla para esos tipos de puerta («*» = todas)."""
    def registrar(f):
        for t in tipos:
            REGLAS.setdefault(t, []).append(f)
        return f
    return registrar


def reglas_de(tipo: str) -> list:
    return [*REGLAS.get("*", []), *REGLAS.get(tipo, [])]


def _lee_json(f: Path):
    return _cargar("hyt_pasos")._json(f, None)


@regla("revision", "revision-final", "datos")
def _paquete(ctx, avisos):
    """El paquete entero: guion, descripción, título elegido y datos. Solo cuando el encargo ya lo ha montado."""
    d = ctx["carpeta"]
    if d and (d / "paquete.json").exists():
        avisos += _cargar("hyt_pasos").revisar_paquete(ctx["canal"], d)


@regla("elegir-titulo")
def _opciones(ctx, avisos):
    d = ctx["carpeta"]
    op = _lee_json(d / "opciones.json") if d else None
    if op:
        R = _cargar("hyt_reglas")
        claves = (op.get("brief") or {}).get("palabras_clave")
        avisos += R.titulos(op.get("titulos") or [], ctx["cfg"], claves)
        avisos += R.miniaturas(op.get("miniaturas") or [], ctx["cfg"], op.get("titulos") or [])


@regla("elegir-temas")
def _temas(ctx, avisos):
    d = ctx["carpeta"]
    t = _lee_json(d / "temas.json") if d else None
    if t:
        avisos += _cargar("hyt_reglas").temas(t.get("temas") or [], ctx["cfg"])
        for a in t.get("avisos") or []:
            _aviso(avisos, False, "pilar-corto", a)


def revisar(slug: str, eid: str | None, tipo: str) -> dict:
    """Pasa las reglas del tipo de puerta. Una regla que revienta no tumba la revisión: deja un aviso (no grave)."""
    avisos: list = []
    ctx = {"canal": slug, "encargo_id": eid, "tipo": tipo, "carpeta": E.carpeta(slug, eid) if eid else None,
           "encargo": E.leer(slug, eid) if eid else None, "cfg": C.leer(slug)}
    for f in reglas_de(tipo):
        try:
            f(ctx, avisos)
        except Exception as x:   # noqa: BLE001
            _aviso(avisos, False, "regla-rota", f"La regla «{getattr(f, '__name__', '?').strip('_')}» falló: {str(x)[:120]}")
    return {"avisos": avisos, "graves": sum(1 for a in avisos if a["grave"])}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) != 4 or a[0] != "revisar":
        print("uso: hyt_revision.py revisar <canal> <encargo> <tipo>", file=sys.stderr)
        sys.exit(2)
    try:
        print(json.dumps(revisar(a[1], a[2], a[3]), ensure_ascii=False, indent=2))
    except B.Rechazo as x:
        print(str(x), file=sys.stderr)
        sys.exit(2)
