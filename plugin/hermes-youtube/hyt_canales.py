"""Canales de hermes-youtube: cada canal de YouTube tiene su carpeta en HERMES_YT_HOME/canales/<slug>/.

  canal.json      configuración (plantillas/canal.json), validada antes de cada escritura
  secretos.env    claves del canal (600); nunca se vuelcan en ninguna salida
  wiki/           memoria del canal (llm-wiki, git propio)
  fuentes/        material propio ya cargado (fuentes/indice.json lo enumera)
  inventario.json piezas extraídas de las fuentes
  encargos/ logs/ extensiones/
  config.jsonl    historial de cambios de configuración (quién, qué, antes, después)

CLI:
  hyt_canales.py alta <slug> <nombre> <presentador>
  hyt_canales.py listar [--json]
  hyt_canales.py ver <slug>
  hyt_canales.py config <slug> <clave.con.puntos> <valor>   (valor JSON o texto)
  hyt_canales.py capacidades <slug>
  hyt_canales.py validar <slug>
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str):
    """Módulos hermanos sin paquete instalable (Hermes carga el plugin desde su carpeta)."""
    if nombre in sys.modules:
        return sys.modules[nombre]
    spec = importlib.util.spec_from_file_location(nombre, AQUI / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


B = _cargar("hyt_base")
Rechazo = B.Rechazo

ROLES = ("marketing", "datos", "presentador")
TIPOS_PILAR = ("pilar", "prueba")
IDIOMA = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ID_PILAR = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# reglas numéricas del canal: (mínimo, máximo) admitidos. Los valores los pone cada canal; el plugin solo acota.
REGLAS = {"titulo_max": (20, 100), "titulos_internos": (1, 100), "titulos_presentados": (1, 20), "miniaturas": (1, 10),
          "ppm": (60, 300), "ppm_medido": (0, 300), "intro_max_palabras": (10, 400), "promesa_extra_palabras": (0, 200),
          "rondas_max": (1, 10), "temas_por_pilar": (1, 20), "reenganches": (0, 20)}
LISTAS_TEXTO = ("formatos", "prohibidas", "cierres_prohibidos", "titulo_cliches", "nombres_vetados", "extensiones")
# listas de patrones: cada elemento es un texto o {"patron": expresión regular, "nombre"?: cómo llamarlo, "grave"?: bool}
LISTAS_PATRON = ("excluido", "sin_promesas")
SUBCARPETAS = ("wiki", "fuentes", "logs", "extensiones")


def plantilla() -> dict:
    raiz = AQUI.parent.parent   # repo/plugin/hermes-youtube → repo; instalado: actual/plugin/hermes-youtube → actual
    for p in (raiz / "plantillas" / "canal.json", B.home() / "actual" / "plantillas" / "canal.json", AQUI / "canal.json"):
        if p.exists():
            return json.loads(p.read_text())
    raise Rechazo("No encuentro la plantilla del canal (plantillas/canal.json)")


def carpeta(slug: str) -> Path:
    return B.home() / "canales" / B.validar_slug(slug)


def listar() -> list:
    d = B.home() / "canales"
    return sorted(p.parent.name for p in d.glob("*/canal.json")) if d.is_dir() else []


def leer(slug: str) -> dict:
    cfg = B.leer(carpeta(slug) / "canal.json")
    if not cfg:
        raise Rechazo(f"No conozco el canal «{slug}». Canales: {', '.join(listar()) or 'ninguno'}")
    return cfg


def _zona_valida(z: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(z)
        return True
    except Exception:
        return False


def _entero(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _lista_texto(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def _patron(x) -> bool:
    if isinstance(x, str):
        return bool(x.strip())
    if not isinstance(x, dict) or not isinstance(x.get("patron"), str) or not x["patron"].strip():
        return False
    if not isinstance(x.get("nombre", ""), str) or not isinstance(x.get("grave", False), bool):
        return False
    try:
        re.compile(x["patron"])
    except re.error:
        return False
    return True


def texto_patron(x) -> str:
    """Un elemento de una lista de patrones, contado para una persona o un agente."""
    if isinstance(x, dict):
        nombre, patron = str(x.get("nombre") or "").strip(), str(x.get("patron") or "")
        return f"{nombre} (patrón: {patron})" if nombre else patron
    return str(x)


def validar(cfg: dict) -> list:
    """Lista de errores (en castellano, para la persona); vacía si la configuración es coherente."""
    e = []
    try:
        B.validar_slug(cfg.get("slug", ""))
    except Rechazo as x:
        e.append(str(x))
    for k in ("nombre", "presentador"):
        if not isinstance(cfg.get(k), str) or not cfg[k].strip():
            e.append(f"{k}: obligatorio (un texto)")
    if not IDIOMA.match(str(cfg.get("idioma", ""))):
        e.append("idioma: código de idioma, con país si hace falta (es, es-ES, en-US…)")
    if not _zona_valida(str(cfg.get("zona_horaria", ""))):
        e.append("zona_horaria: no la reconozco (p. ej. Europe/Madrid)")
    pilares = cfg.get("pilares", [])
    if not isinstance(pilares, list):
        e.append("pilares: una lista de {\"id\", \"nombre\", \"tipo\": \"pilar|prueba\"}")
    else:
        vistos = set()
        for p in pilares:
            if not (isinstance(p, dict) and ID_PILAR.match(str(p.get("id", ""))) and isinstance(p.get("nombre"), str)
                    and p["nombre"].strip() and p.get("tipo", "pilar") in TIPOS_PILAR):
                e.append(f"pilares: {p} no tiene la forma {{\"id\": \"minúsculas-y-guiones\", \"nombre\": \"…\", "
                         f"\"tipo\": \"{'|'.join(TIPOS_PILAR)}\"}}")
            elif p["id"] in vistos:
                e.append(f"pilares: el id «{p['id']}» está repetido")
            else:
                vistos.add(p["id"])
    for k in LISTAS_TEXTO:
        if not _lista_texto(cfg.get(k, [])):
            e.append(f"{k}: una lista de textos (sin elementos vacíos)")
    for k in LISTAS_PATRON:
        v = cfg.get(k, [])
        if not isinstance(v, list) or not all(_patron(x) for x in v):
            e.append(f"{k}: una lista de textos o de {{\"nombre\", \"patron\", \"grave\"}} (el patrón, una expresión regular válida)")
    reglas = cfg.get("reglas")
    if not isinstance(reglas, dict):
        e.append("reglas: un objeto")
    else:
        for k, (lo, hi) in REGLAS.items():
            v = reglas.get(k)
            if not _entero(v) or not lo <= v <= hi:
                e.append(f"reglas.{k}: un número entero entre {lo} y {hi}")
        m = reglas.get("minutos")
        if not (isinstance(m, list) and len(m) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                           for x in m) and 0 < m[0] <= m[1] <= 240):
            e.append("reglas.minutos: [mínimo, máximo] en minutos (p. ej. [13, 15])")
        if (_entero(reglas.get("titulos_presentados")) and _entero(reglas.get("titulos_internos"))
                and reglas["titulos_presentados"] > reglas["titulos_internos"]):
            e.append("reglas.titulos_presentados: no puede ser mayor que reglas.titulos_internos")
    tr = cfg.get("transcripcion", {})
    if not isinstance(tr, dict):
        e.append("transcripcion: un objeto {correcciones, ruido}")
    else:
        co = tr.get("correcciones", {})
        if not (isinstance(co, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in co.items())):
            e.append("transcripcion.correcciones: un objeto {\"lo que transcribe mal\": \"lo correcto\"}")
        if not _lista_texto(tr.get("ruido", [])):
            e.append("transcripcion.ruido: una lista de textos")
    if not isinstance(cfg.get("marca", {}), dict):
        e.append("marca: un objeto (vacío si el canal no la ha definido)")
    if not isinstance(cfg.get("descripcion_pie", ""), str):
        e.append("descripcion_pie: un texto")
    personas = cfg.get("personas", {})
    if not isinstance(personas, dict):
        e.append("personas: un objeto {clave: {nombre, correo, roles}}")
    else:
        for k, p in personas.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", str(k)):
                e.append(f"personas: la clave «{k}» va en minúsculas, con letras, números y guiones")
                continue
            if not isinstance(p, dict) or not isinstance(p.get("nombre"), str) or not p["nombre"].strip():
                e.append(f"personas.{k}.nombre: obligatorio")
                continue
            if p.get("correo") and not CORREO.match(str(p["correo"])):
                e.append(f"personas.{k}.correo: no parece una dirección de correo")
            roles = p.get("roles", [])
            if not isinstance(roles, list) or any(r not in ROLES for r in roles):
                e.append(f"personas.{k}.roles: una lista con {', '.join(ROLES)}")
    permite = cfg.get("permite", {})
    if not (isinstance(permite, dict) and all(isinstance(v, bool) for v in permite.values())):
        e.append("permite: un objeto de interruptores true/false")
    pol = cfg.get("politicas") or {}
    if not isinstance(pol.get("pausado", False), bool):
        e.append("politicas.pausado: true o false")
    if not _entero(pol.get("tope_semanal", 0)) or pol.get("tope_semanal", 0) < 0:
        e.append("politicas.tope_semanal: un número entero (0 = sin tope)")
    for k in ("modelos", "ejecutores", "telegram"):
        if not isinstance(cfg.get(k, {}), dict):
            e.append(f"{k}: un objeto")
    return e


def capacidades(cfg: dict) -> set:
    """Lo que el canal ya tiene. Las pipelines y sus etapas declaran lo que necesitan (`requiere`)."""
    c = set()
    if cfg.get("pilares"):
        c.add("pilares")
    try:
        d = carpeta(cfg.get("slug", ""))
    except Rechazo:
        return c
    if (d / "wiki" / "concepts" / "voz.md").is_file():
        c.add("voz")
    if _con_entradas(B.leer(d / "fuentes" / "indice.json")):
        c.add("fuentes")
    if (d / "inventario.json").is_file():
        c.add("inventario")
    return c


def _con_entradas(indice) -> bool:
    """El índice de fuentes tiene alguna entrada: una lista no vacía, o un objeto con alguna colección no vacía (si no
    tiene colecciones dentro, basta con que no esté vacío)."""
    if isinstance(indice, list):
        return bool(indice)
    if isinstance(indice, dict):
        hijos = [v for v in indice.values() if isinstance(v, (list, dict))]
        return any(hijos) if hijos else bool(indice)
    return False


def _guardar(slug: str, cfg: dict) -> None:
    errores = validar(cfg)
    if errores:
        raise Rechazo("La configuración no es válida:\n- " + "\n- ".join(errores))
    B.escribir(carpeta(slug) / "canal.json", cfg)
    try:   # la página «canal» de su memoria sigue a la configuración
        _cargar("hyt_wiki").regenerar_canal(slug)
    except Exception:   # noqa: BLE001
        pass


def alta(slug: str, nombre: str, presentador: str, quien: str = "") -> dict:
    """Crea el canal desde la plantilla. No lanza nada: las fuentes, el inventario y la voz vienen después."""
    B.validar_slug(slug)
    d = carpeta(slug)
    with B.cerrojo("canales"):
        if (d / "canal.json").exists():
            raise Rechazo(f"El canal «{slug}» ya existe")
        cfg = plantilla()
        cfg.update(slug=slug, nombre=(nombre or "").strip() or slug, presentador=(presentador or "").strip())
        _guardar(slug, cfg)
        for s in SUBCARPETAS:
            (d / s).mkdir(parents=True, exist_ok=True)
        sec = d / "secretos.env"
        if not sec.exists():
            sec.write_text("# Claves de este canal (KEY=valor). Solo las lee el plugin; nunca se muestran.\n")
        os.chmod(sec, 0o600)
        B.anotar(d / "config.jsonl", {"ts": B.ahora(), "quien": quien, "accion": "alta", "nombre": cfg["nombre"],
                                      "presentador": cfg["presentador"]})
    return cfg


def _poner(cfg: dict, clave: str, valor) -> tuple:
    partes = clave.split(".")
    if not all(re.fullmatch(r"[a-z_][a-z0-9_-]*", p) for p in partes):
        raise Rechazo(f"Clave no válida: {clave}")
    if partes[0] in ("slug", "version"):
        raise Rechazo(f"«{partes[0]}» no se cambia")
    nodo = cfg
    for p in partes[:-1]:
        if not isinstance(nodo.get(p), dict):
            if p in nodo:
                raise Rechazo(f"«{p}» no es un objeto")
            nodo[p] = {}
        nodo = nodo[p]
    antes = copy.deepcopy(nodo.get(partes[-1]))
    nodo[partes[-1]] = valor
    return antes, valor


def config(slug: str, clave: str, valor, quien: str = "") -> dict:
    """Cambia un valor (clave con puntos) validando la configuración completa antes de escribir."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            pass   # texto
    with B.cerrojo("canales"):
        cfg = leer(slug)
        antes, despues = _poner(cfg, clave, valor)
        _guardar(slug, cfg)
        B.anotar(carpeta(slug) / "config.jsonl",
                 {"ts": B.ahora(), "quien": quien, "accion": "config", "clave": clave, "antes": antes, "despues": despues})
    return cfg


def secretos(slug: str) -> dict:
    """Claves del canal más las globales (las del canal mandan). Solo para pasarlas a procesos; nunca se imprimen."""
    def leer_env(p: Path) -> dict:
        out = {}
        try:
            for linea in p.read_text().splitlines():
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
        return out
    return {**leer_env(B.home() / "secretos.env"), **leer_env(carpeta(slug) / "secretos.env")}


def resumen(cfg: dict) -> str:
    cap = sorted(capacidades(cfg))
    extra = ["⏸ en pausa"] if (cfg.get("politicas") or {}).get("pausado") else []
    return (f"{cfg['nombre']} ({cfg['slug']}) · presenta: {cfg.get('presentador') or '—'} · {cfg.get('idioma', '')}"
            f" · {len(cfg.get('pilares') or [])} pilar(es)"
            + (f" · {' · '.join(extra)}" if extra else "") + f"\n  capacidades: {', '.join(cap) or 'ninguna'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt_canales.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("alta"); a.add_argument("slug"); a.add_argument("nombre"); a.add_argument("presentador")
    a.add_argument("--quien", default="")
    l = sub.add_parser("listar"); l.add_argument("--json", action="store_true")
    for n in ("ver", "capacidades", "validar"):
        sub.add_parser(n).add_argument("slug")
    c = sub.add_parser("config"); c.add_argument("slug"); c.add_argument("clave"); c.add_argument("valor")
    c.add_argument("--quien", default="")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "alta":
            print(resumen(alta(x.slug, x.nombre, x.presentador, x.quien)))
        elif x.cmd == "listar":
            cs = listar()
            if x.json:
                print(json.dumps([leer(s) for s in cs], ensure_ascii=False))
            else:
                print("\n".join(resumen(leer(s)) for s in cs) or "Sin canales todavía.")
        elif x.cmd == "ver":
            print(json.dumps(leer(x.slug), ensure_ascii=False, indent=2))
        elif x.cmd == "capacidades":
            print(" ".join(sorted(capacidades(leer(x.slug)))))
        elif x.cmd == "validar":
            err = validar(leer(x.slug))
            print("ok" if not err else "\n".join(err))
            return 1 if err else 0
        elif x.cmd == "config":
            print(resumen(config(x.slug, x.clave, x.valor, x.quien)))
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
