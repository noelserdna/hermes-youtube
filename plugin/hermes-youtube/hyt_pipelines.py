"""Pipelines como datos: qué etapas tiene cada trabajo, quién hace cada una y en qué puerta acaba.

Una pipeline es un JSON en pipelines/<id>.json (del plugin) o en canales/<slug>/extensiones/pipelines/<id>.json (del
canal: añade pipelines propias o sustituye una del plugin con el mismo id).

  {"id": "guion", "nombre": "Guion", "descripcion": "…",
   "requiere": ["fuentes"],                  capacidades del canal sin las que no se puede lanzar
   "nueva_pieza": true,                      cuenta para el tope semanal del canal
   "parametros": {"tema": "De qué trata"},   obligatorios al lanzar
   "etapas": [{"id": "documentar", "titulo": "Documentar: {tema}", "perfil": "yt-investigador",
               "skill": "documentar", "ejecutor": "hermes", "max_runtime": "60m",
               "requiere": [], "salida": "material.md"}, …],
   "puerta": {"tipo": "revision", "al_aprobar": "nada", "rehacer": "escribir"}}   (se abre al acabar la última etapa)

al_aprobar: nada | pipeline:<id> (sigue con otra pipeline: mismos parámetros y las salidas de este encargo) |
script:<fichero de extensiones/> [args con {encargo} y {carpeta}] (un script propio del canal).

Una pipeline acaba en UNA puerta (`puerta`) o en una CADENA (`puertas`: una lista, en orden; cada una con su `tipo`,
el `papel` que la decide y, si acaso, `si_vacio: saltar`):

  "puertas": [{"tipo": "revision", "papel": "marketing"}, {"tipo": "datos", "papel": "datos", "si_vacio": "saltar"},
              {"tipo": "revision-final", "papel": "presentador"}],
  "rehacer": "ajustar", "al_aprobar": "nada"

`rehacer` (la etapa desde la que se rehace) y `al_aprobar` (lo que pasa al aprobar la ÚLTIMA puerta) son de la pipeline:
van dentro de `puerta` o como campos de la pipeline. Quien los necesite, que los pida con `puertas_de()`,
`rehacer_de()` y `al_aprobar_de()`, no leyendo `puerta` a pelo.

Una etapa con `requiere` que el canal no cumple se salta; una pipeline con `requiere` que no cumple no se lanza y dice
qué falta.

CLI:
  hyt_pipelines.py listar [--canal SLUG]
  hyt_pipelines.py ver <id> [--canal SLUG]
  hyt_pipelines.py plan <id> --canal SLUG       etapas que correrían para ese canal
  hyt_pipelines.py validar-todas
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
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
Rechazo = B.Rechazo

PERFILES_ROL = ("yt-analista", "yt-estratega", "yt-espectador", "yt-titulador", "yt-miniaturista", "yt-investigador",
                "yt-guionista", "yt-verificador", "yt-retencion", "yt-doble", "yt-editor-jefe")
EJECUTORES = ("hermes", "claude")
PAPELES = ("marketing", "datos", "presentador")   # los mismos que hyt_canales.ROLES
SI_VACIO = ("saltar",)
TIPOS_PUERTA = ("alta", "elegir-temas", "elegir-titulo", "revision", "datos", "revision-final", "voz", "decision")
AL_APROBAR = re.compile(r"^(nada|pipeline:[a-z0-9-]+|script:[A-Za-z0-9._-]+( [^;&|`$<>]*)?)$")
ID = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
DURACION = re.compile(r"^\d{1,3}[mh]$")


def raiz() -> Path:
    """Carpeta del arnés: el repo (desarrollo) o ~/.hermes/hermes-youtube/actual (instalado)."""
    for r in (AQUI.parent.parent, B.home() / "actual"):
        if (r / "pipelines").is_dir():
            return r
    return AQUI.parent.parent


def _dirs(slug: str | None) -> list:
    ds = [raiz() / "pipelines"]
    if slug:
        ds.append(B.home() / "canales" / B.validar_slug(slug) / "extensiones" / "pipelines")
    return ds


def listar(slug: str | None = None) -> dict:
    """{id: pipeline}; las del canal sustituyen a las del plugin con el mismo id."""
    out = {}
    for d in _dirs(slug):
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            p = B.leer(f)
            if isinstance(p, dict) and p.get("id"):
                out[p["id"]] = {**p, "_origen": str(f)}
    return out


def cargar(pid: str, slug: str | None = None) -> dict:
    p = listar(slug).get(pid)
    if not p:
        raise Rechazo(f"No conozco la pipeline «{pid}». Hay: {', '.join(sorted(listar(slug))) or 'ninguna'}")
    return p


# Datos que el CÓDIGO deja en la carpeta del encargo antes de una etapa («prepara»: [...]): las cifras no las calcula
# el modelo. Cada una escribe datos-<nombre>.json (ver hyt_etapa.preparar). Todavía no hay ninguna: el mecanismo queda.
PREPARA = ("fuente", "fuentes", "inventario", "referencias", "voz", "eleccion", "ajustes")   # antes de la etapa
TRAS = ("piezas", "seleccionar", "brief", "opciones", "material", "datos", "descripcion", "paquete")   # después


def puertas_de(p: dict | None) -> list:
    """Las puertas de una pipeline (o de un encargo), en orden: su cadena (`puertas`) o su puerta única (`puerta`)."""
    p = p or {}
    cadena = p.get("puertas")
    if isinstance(cadena, list) and cadena:
        return [g for g in cadena if isinstance(g, dict)]
    puerta = p.get("puerta")
    return [puerta] if isinstance(puerta, dict) and puerta else []


def rehacer_de(p: dict | None) -> str:
    """La etapa desde la que se rehace cuando una persona lo pide en una puerta ("" = la última)."""
    p = p or {}
    return str(p.get("rehacer") or (p.get("puerta") or {}).get("rehacer") or "")


def al_aprobar_de(p: dict | None) -> str:
    """Lo que ejecuta el notario al aprobarse la última puerta."""
    p = p or {}
    return str(p.get("al_aprobar") or (p.get("puerta") or {}).get("al_aprobar") or "nada")


def _valida_puerta(g, donde: str) -> list:
    if not isinstance(g, dict) or g.get("tipo") not in TIPOS_PUERTA:
        return [f"{donde}.tipo: uno de {', '.join(TIPOS_PUERTA)}"]
    e = []
    if g.get("papel") and g["papel"] not in PAPELES:
        e.append(f"{donde}.papel: uno de {', '.join(PAPELES)} (o sin papel)")
    if g.get("si_vacio") is not None and g["si_vacio"] not in SI_VACIO:
        e.append(f"{donde}.si_vacio: {' | '.join(SI_VACIO)}")
    elif g.get("si_vacio") and g["tipo"] != "datos":
        e.append(f"{donde}.si_vacio: solo en una puerta de tipo datos")
    return e


def validar(p: dict) -> list:
    e = []
    if not ID.match(str(p.get("id", ""))):
        e.append("id: minúsculas, números y guiones")
    if not p.get("nombre"):
        e.append("nombre: obligatorio")
    if not isinstance(p.get("requiere", []), list):
        e.append("requiere: una lista")
    if not isinstance(p.get("parametros", {}), dict):
        e.append("parametros: un objeto {nombre: descripción}")
    etapas = p.get("etapas")
    if not isinstance(etapas, list) or not etapas:
        e.append("etapas: al menos una")
        etapas = []
    vistos = set()
    for i, s in enumerate(etapas):
        donde = f"etapas[{i}]"
        if not isinstance(s, dict):
            e.append(f"{donde}: un objeto"); continue
        if not ID.match(str(s.get("id", ""))):
            e.append(f"{donde}.id no válido")
        elif s["id"] in vistos:
            e.append(f"{donde}.id «{s['id']}» repetido")
        prep = s.get("prepara", [])
        if not isinstance(prep, list) or any(x not in PREPARA for x in prep):
            e.append(f"{donde}.prepara: una lista de {', '.join(PREPARA) or '(todavía no hay preparaciones)'}")
        tras = s.get("tras", [])
        if not isinstance(tras, list) or any(x not in TRAS for x in tras):
            e.append(f"{donde}.tras: una lista de {', '.join(TRAS) or '(todavía no hay pasos)'}")
        if s.get("si_cambios") is not None and s.get("si_cambios") not in vistos:
            e.append(f"{donde}.si_cambios: el id de una etapa ANTERIOR (a la que vuelve si la verificación pide cambios)")
        vistos.add(s.get("id"))
        if s.get("ejecutor", "hermes") not in EJECUTORES:
            e.append(f"{donde}.ejecutor: uno de {', '.join(EJECUTORES)}")
        if s.get("perfil") not in PERFILES_ROL:
            e.append(f"{donde}.perfil: uno de {', '.join(PERFILES_ROL)}")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,60}", str(s.get("skill", ""))):
            e.append(f"{donde}.skill: el nombre de una skill")
        if not DURACION.match(str(s.get("max_runtime", "60m"))):
            e.append(f"{donde}.max_runtime: p. ej. 30m o 2h")
        if not isinstance(s.get("requiere", []), list):
            e.append(f"{donde}.requiere: una lista")
        for marca in re.findall(r"\{(\w+)\}", s.get("titulo", "")):
            if marca not in (p.get("parametros") or {}):
                e.append(f"{donde}.titulo usa {{{marca}}}, que no es un parámetro")
    mem = p.get("memoria")
    if mem is not None and (not isinstance(mem, dict) or not mem.get("pagina") or not mem.get("de")):
        e.append("memoria: {pagina, de, seccion?} (la página fija de la wiki que escribe al acabar)")
    puerta, cadena = p.get("puerta"), p.get("puertas")
    if puerta is not None:
        e += _valida_puerta(puerta, "puerta")
        if isinstance(puerta, dict) and puerta.get("si_vacio"):
            e.append("puerta.si_vacio: solo dentro de una cadena («puertas»)")
    if cadena is not None:
        if not isinstance(cadena, list) or not cadena:
            e.append("puertas: una lista con al menos una puerta, en orden")
        else:
            for i, g in enumerate(cadena):
                e += _valida_puerta(g, f"puertas[{i}]")
            if all(isinstance(g, dict) and g.get("si_vacio") for g in cadena):
                e.append("puertas: al menos una que no se salte (sin si_vacio): siempre decide una persona")
    if not AL_APROBAR.match(al_aprobar_de(p)):
        e.append("al_aprobar: nada | pipeline:<id> | script:<fichero> [args]")
    if rehacer_de(p) and rehacer_de(p) not in vistos:
        e.append("rehacer: el id de una de sus etapas")
    if (p.get("rehacer") or p.get("al_aprobar")) and puerta is None and cadena is None:
        e.append("rehacer y al_aprobar solo tienen sentido con «puerta» o «puertas»")
    return e


def plan(pid: str, slug: str) -> dict:
    """Las etapas que correrían para este canal, y las que se saltan y por qué. Rechazo si no se puede lanzar."""
    C = _cargar("hyt_canales")
    cfg = C.leer(slug)
    p = cargar(pid, slug)
    err = validar(p)
    if err:
        raise Rechazo(f"La pipeline «{pid}» no es válida:\n- " + "\n- ".join(err))
    caps = C.capacidades(cfg)
    falta = [r for r in p.get("requiere", []) if not _cumple(r, caps)]
    if falta:
        raise Rechazo(f"«{p['nombre']}» necesita {', '.join(falta)}, y {cfg['nombre']} no lo tiene configurado")
    corren, saltadas = [], []
    for s in p["etapas"]:
        f = [r for r in s.get("requiere", []) if not _cumple(r, caps)]
        (saltadas if f else corren).append({**s, "falta": f} if f else s)
    if not corren:
        raise Rechazo(f"Para {cfg['nombre']} no quedaría ninguna etapa de «{p['nombre']}»")
    return {"pipeline": p, "etapas": corren, "saltadas": saltadas}


def _cumple(req: str, caps: set) -> bool:
    """«fuentes» lo cumple el canal que las tiene; «a|b», cualquiera de los dos."""
    return any(r in caps for r in req.split("|"))


def politicas(pid: str, slug: str, excepcion: bool = False, hoy: date | None = None) -> None:
    """Rechazo si las políticas del canal impiden lanzar ahora esta pipeline. `excepcion`: una persona lo pidió
    expresamente (salta el tope, nunca la pausa) y queda anotado."""
    C = _cargar("hyt_canales")
    cfg = C.leer(slug)
    pol = cfg.get("politicas") or {}
    if pol.get("pausado"):
        raise Rechazo(f"{cfg['nombre']} está en pausa: no se lanza nada hasta reanudarlo")
    p = cargar(pid, slug)
    if not p.get("nueva_pieza") or excepcion:
        return
    hoy = hoy or datetime.now(timezone.utc).date()
    tope = int(pol.get("tope_semanal") or 0)
    if tope:
        desde = (hoy - timedelta(days=7)).isoformat()
        n = 0
        try:
            for linea in (C.carpeta(slug) / "encargos.jsonl").read_text().splitlines():
                r = json.loads(linea)
                if r.get("nueva_pieza") and str(r.get("ts", ""))[:10] > desde:
                    n += 1
        except OSError:
            pass
        if n >= tope:
            raise Rechazo(f"{cfg['nombre']} ya tiene {n} vídeo(s) nuevo(s) esta semana (tope {tope})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt_pipelines.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("listar"); l.add_argument("--canal")
    v = sub.add_parser("ver"); v.add_argument("id"); v.add_argument("--canal")
    pl = sub.add_parser("plan"); pl.add_argument("id"); pl.add_argument("--canal", required=True)
    sub.add_parser("validar-todas")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "listar":
            for pid, p in listar(x.canal).items():
                print(f"{pid:22} {p.get('nombre', '')}")
        elif x.cmd == "ver":
            print(json.dumps(cargar(x.id, x.canal), ensure_ascii=False, indent=2))
        elif x.cmd == "plan":
            r = plan(x.id, x.canal)
            for s in r["etapas"]:
                print(f"▶ {s['id']:18} {s['perfil']:18} {s['skill']}")
            for s in r["saltadas"]:
                print(f"· {s['id']:18} se salta: falta {', '.join(s['falta'])}")
            for g in puertas_de(r["pipeline"]):
                print(f"🚪 {g['tipo']}" + (f" ({g['papel']})" if g.get("papel") else ""))
        elif x.cmd == "validar-todas":
            mal = 0
            for pid, p in listar().items():
                err = validar(p)
                if err:
                    mal += 1
                    print(f"{pid}: " + "; ".join(err))
            print("ok" if not mal else f"{mal} con errores")
            return 1 if mal else 0
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
