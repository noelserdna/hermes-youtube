"""El estado REAL de un canal (o de todos) en cada turno de conversación, sin modelo.

Lo inyecta el plugin con el hook pre_llm_call en la conversación de la coordinadora (todos los canales): puertas
abiertas con fecha y edad, encargos en marcha y lo que pasó en los últimos 7 días. Corto (≈1.500 caracteres por canal)
y recalculado en cada turno: no envejece como un resumen en el prompt, que se congela al abrir la sesión.

  hyt_estado.py turno <canal>    ·    hyt_estado.py canales
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
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
PU = _cargar("hyt_puertas")

MAX_CANAL = 1500
DIAS_RECIENTE = 7
# lo que parezca una clave no entra nunca en el contexto (puede venir de una salida que copió algo de más)
_CLAVE = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|"
                    r"AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|[A-Za-z0-9+/_-]{40,})")


def tapar(texto: str) -> str:
    return _CLAVE.sub("[clave tapada]", texto)


def _ts(t) -> float:
    try:
        return datetime.strptime(str(t)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _jsonl(p: Path) -> list:
    try:
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _edad(segundos: float) -> str:
    h = segundos / 3600
    return f"{int(h)} h" if h < 48 else f"{int(h // 24)} días"


def _titular(d: Path, salida: str | None) -> str:
    """Primera línea con contenido de una salida (sin marcas de título)."""
    if not salida or not (d / salida).exists():
        return ""
    try:
        for l in (d / salida).read_text(errors="replace").splitlines():
            l = l.strip().lstrip("#").strip()
            if l and not l.startswith(("---", "VEREDICTO")):
                return l[:140]
    except OSError:
        pass
    return ""


def _donde(p: dict) -> str:
    """«puerta 2/3: datos (decide: datos) · ronda 1» de una puerta de un encargo."""
    partes = []
    if p.get("encargo"):
        total = int(p.get("total") or 1)
        partes.append((f"puerta {int(p.get('indice') or 0) + 1}/{total}: " if total > 1 else "puerta: ") + str(p.get("tipo")))
    if p.get("papel"):
        partes.append(f"decide: {p['papel']}")
    if p.get("ronda"):
        partes.append(f"ronda {p['ronda']}")
    return " · ".join(partes)


def turno(slug: str, ahora: float | None = None) -> str:
    ahora = ahora or time.time()
    cfg = C.leer(slug)
    d = C.carpeta(slug)
    lineas = [f"## Estado real de {cfg.get('nombre') or slug} ({datetime.now().strftime('%d-%m %H:%M')}, se recalcula en cada turno)"]

    puertas = [p for p in PU.puertas(("abierta", "decidida", "error")) if p.get("canal") == slug]
    if puertas:
        lineas.append("Puertas pendientes:")
        for p in sorted(puertas, key=lambda x: x.get("creada", "")):
            pend = PU.datos_pendientes(p)
            extra = (f" · {pend} dato(s) por verificar" if pend else
                     " · ⛔ aviso grave: no se puede aprobar" if PU.graves(p) else "")
            donde = _donde(p)
            lineas.append(f"- {p['titulo'][:70]} ({p['estado']}, desde {str(p.get('creada', ''))[:10]}, "
                          f"hace {_edad(ahora - _ts(p.get('creada')))}){' · ' + donde if donde else ''}{extra} [{p['id']}]")
    else:
        lineas.append("Puertas pendientes: ninguna.")

    abiertos = [e for e in E.listar(slug, abiertos=True) if e.get("estado") != "en-puerta"]
    if abiertos:
        lineas.append("En marcha:")
        for e in abiertos[-6:]:
            ronda = f" · ronda {e['rondas']}" if e.get("rondas") else ""
            lineas.append(f"- {e.get('nombre', '')} · {e.get('estado')}{ronda} · desde {str(e.get('creado', ''))[:10]} [{e['id']}]")

    desde = ahora - DIAS_RECIENTE * 86400
    hechos = []
    for r in _jsonl(d / "puertas.jsonl"):
        if _ts(r.get("ts")) >= desde and not r.get("evento"):   # los datos verificados uno a uno no se cuentan aquí
            hechos.append(f"{str(r.get('ts'))[:10]} puerta {r.get('tipo')}: {r.get('verbo')} → {str(r.get('resultado', ''))[:60]}")
    if hechos:
        lineas.append(f"Últimos {DIAS_RECIENTE} días:")
        lineas += [f"- {h}" for h in hechos[-6:]]

    # el último resultado sin puerta de cada tipo (aunque tenga más de 7 días): lo que se sabe, con su fecha
    ultimos: dict = {}
    for e in E.listar(slug):
        if e.get("informe") and e.get("estado") == "hecho":
            ultimos[e.get("pipeline")] = e
    if ultimos:
        lineas.append("Último resultado sin puerta de cada tipo:")
        for pid, e in sorted(ultimos.items(), key=lambda kv: kv[1].get("creado", ""), reverse=True)[:6]:
            de = E.carpeta(slug, e["id"])
            salida = None
            try:
                etapas = _cargar("hyt_pipelines").cargar(pid, slug)["etapas"]
                salida = next((s.get("salida") for s in reversed(etapas) if s.get("salida")), None)
            except Exception:   # noqa: BLE001 — una pipeline que ya no existe no rompe el estado
                pass
            tit = _titular(de, salida)
            lineas.append(f"- {e.get('nombre')} ({str(e.get('creado', ''))[:10]}): {tit or 'ver ' + str(de / (salida or ''))}")

    try:
        notas = _cargar("hyt_wiki").ultimas(slug, 3)
    except Exception:   # noqa: BLE001
        notas = []
    if notas:
        lineas.append("Memoria (últimas notas de la wiki): " + " | ".join(n[2:90] for n in notas))

    texto = tapar("\n".join(lineas))
    return texto if len(texto) <= MAX_CANAL else texto[:MAX_CANAL - 20] + "\n… (recortado)"


def canales(ahora: float | None = None) -> str:
    """Una línea por canal, más el disco, el latido del bucle de puertas y la última copia."""
    lineas = [f"## Estado real de los canales ({datetime.now().strftime('%d-%m %H:%M')})", B.disco_linea()]
    lat = B.leer(B.home() / "latido.json")
    if isinstance(lat, dict) and lat.get("ts"):
        lineas.append(f"Bucle de puertas: último latido {str(lat.get('ts'))[:16]}")
    cop = B.leer(B.home() / "copia.json")
    if isinstance(cop, dict):
        lineas.append(f"Copia: {'bien' if cop.get('ok') else 'FALLÓ: ' + str(cop.get('motivo', ''))[:80]} ({str(cop.get('ts', ''))[:16]})")
    if (B.home() / "pausa").exists():
        lineas.append("⏸ Todo en pausa")
    for slug in C.listar():
        try:
            cfg = C.leer(slug)
        except B.Rechazo:
            continue
        ps = [p for p in PU.puertas(("abierta", "decidida", "error")) if p.get("canal") == slug]
        marcha = [e for e in E.listar(slug, abiertos=True) if e.get("estado") != "en-puerta"]
        parados = sum(1 for e in marcha if e.get("estado") == "parado")
        lineas.append(f"- {cfg.get('nombre') or slug} ({slug}): {len(ps)} puerta(s), {len(marcha)} en marcha"
                      + (f", {parados} parado(s)" if parados else "")
                      + (" · ⏸ en pausa" if (cfg.get("politicas") or {}).get("pausado") else ""))
    lineas.append("Para el detalle de un canal: hyt estado <canal>")
    return tapar("\n".join(lineas))[:3000]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["turno"] and len(a) == 2:
        print(turno(a[1]))
    elif a[:1] == ["canales"]:
        print(canales())
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
