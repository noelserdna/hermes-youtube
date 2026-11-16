"""Qué modelo hace cada etapa (copiado y adaptado de hermes-sdd, hsdd_proyectos.py y docs/ejecutores.md).

Orden de precedencia, de menos a más:
  1. el perfil de modelos global (yt.json → perfil_modelos: calidad | equilibrado | rapido)
  2. los cambios por etapa globales (yt.json → modelos.<etapa>)
  3. los del canal (canal.json → modelos.<etapa>), que mandan

Los modelos se guardan como alias (fable, opus, sonnet, haiku: siempre el último de cada familia) o con su nombre
completo. Cada ejecutor los recibe en su formato: Claude Code acepta el alias tal cual; un perfil de Hermes necesita
el id de SU proveedor (OpenRouter: anthropic/claude-opus-5.5; Anthropic directo: claude-opus-5-5; otro proveedor, como
ChatGPT: no se fuerza nada y usa el modelo del perfil).

Lección de hermes-sdd: nada de Haiku en juicios que acaban en una probabilidad (con Haiku todo salía en la banda de
duda).

CLI:
  hyt_modelos.py ver [--canal SLUG]            modelo por etapa y de dónde sale
  hyt_modelos.py para <etapa> <ejecutor> [--canal SLUG] [--perfil PERFIL_HERMES]
  hyt_modelos.py perfil <calidad|equilibrado|rapido>
  hyt_modelos.py poner <etapa> <alias|id|-> [--canal SLUG]     (- quita el cambio)
"""
from __future__ import annotations

import argparse
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
Rechazo = B.Rechazo

# Etapas conocidas (las pipelines pueden traer otras: si no están aquí, usan el modelo «ligero» del perfil)
ETAPAS_MODELO = [
    ("inventario", "Inventario de piezas"), ("perfil", "Perfil de voz"),
    ("generar", "Generar temas"), ("puntuar", "Puntuar temas"),
    ("angulo", "Ángulo y brief"), ("titular", "Títulos"), ("miniaturas", "Ideas de miniatura"),
    ("espectador", "Prueba del espectador"),
    ("documentar", "Documentar el tema"), ("escaleta", "Escaleta"), ("escribir", "Escribir el guion"),
    ("verificar", "Verificar los datos"), ("retencion", "Crítica de retención"), ("voz", "Crítica de voz"),
    ("ajustar", "Ajustar el guion"),
    ("describir", "Descripción y capítulos"), ("cierre", "Cierre del paquete"),
]
# juicio y escritura: donde más rinde un modelo grande
PIENSAN = ("generar", "angulo", "titular", "escaleta", "escribir", "voz", "ajustar", "cierre", "perfil")
PERFILES = {
    "calidad": {e: "opus" for e, _ in ETAPAS_MODELO},
    "equilibrado": {e: ("opus" if e in PIENSAN else "sonnet") for e, _ in ETAPAS_MODELO},
    "rapido": {e: "sonnet" for e, _ in ETAPAS_MODELO},
}
NOMBRE_PERFIL = {"calidad": "Calidad: Opus en todo", "equilibrado": "Equilibrado: Opus decide y escribe, Sonnet el resto",
                 "rapido": "Rápido: Sonnet en todo"}
PERFIL_DEFECTO = "equilibrado"
LIGERO = "sonnet"   # etapas que no están en la lista
ALIAS = {"fable": "Fable (el más reciente de Claude)", "opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku (no para juicios)"}
OPENROUTER_DEFECTO = {"fable": "anthropic/claude-fable-5.2", "opus": "anthropic/claude-opus-5.5",
                      "sonnet": "anthropic/claude-sonnet-5.5", "haiku": "anthropic/claude-haiku-5.5"}


def config_global() -> dict:
    return B.leer(B.home() / "yt.json", {}) or {}


def _canal(slug: str | None) -> dict:
    if not slug:
        return {}
    return _cargar("hyt_canales").leer(slug)


def _version(mid: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", mid.rsplit("-", 1)[-1]))


def modelos_openrouter() -> dict:
    """{familia: [ids de OpenRouter, del más nuevo al más viejo]} según la caché de modelos de Hermes."""
    try:
        texto = (Path.home() / ".hermes" / "models_dev_cache.json").read_text(errors="replace")
    except OSError:
        texto = ""
    fam: dict = {}
    for mid in sorted(set(re.findall(r'"(anthropic/claude-(fable|opus|sonnet|haiku)-[0-9][0-9.]*)"', texto))):
        fam.setdefault(mid[1], []).append(mid[0])
    return {f: sorted(ids, key=_version, reverse=True) for f, ids in fam.items()}


def efectivos(slug: str | None = None, cfg: dict | None = None) -> dict:
    """{etapa: (modelo, origen)} con origen perfil:<p> | global | canal."""
    cfg = cfg if cfg is not None else config_global()
    perfil = cfg.get("perfil_modelos") if cfg.get("perfil_modelos") in PERFILES else PERFIL_DEFECTO
    out = {e: (m, f"perfil:{perfil}") for e, m in PERFILES[perfil].items()}
    out.update({e: (m, "global") for e, m in (cfg.get("modelos") or {}).items() if m})
    out.update({e: (m, "canal") for e, m in (_canal(slug).get("modelos") or {}).items() if m})
    return out


def proveedor_de(perfil_hermes: str | None) -> str:
    """Proveedor del modelo de un perfil de Hermes, leyendo su config.yaml sin PyYAML (model: → provider:)."""
    if not perfil_hermes:
        return ""
    base = Path.home() / ".hermes"
    p = base / "config.yaml" if perfil_hermes == "default" else base / "profiles" / perfil_hermes / "config.yaml"
    try:
        texto = p.read_text(errors="replace")
    except OSError:
        return ""
    m = re.search(r"(?m)^model:[ \t]*\n((?:(?:[ \t]+.*|[ \t]*)\n?)*)", texto)   # hasta la siguiente clave sin sangría
    if not m:
        return ""
    pm = re.search(r"(?m)^[ \t]+provider:\s*['\"]?([\w.-]+)", m.group(1))
    return pm.group(1) if pm else ""


def para(etapa: str, ejecutor: str = "claude", slug: str | None = None, perfil_hermes: str | None = None,
         proveedor: str | None = None) -> str:
    """Modelo de una etapa en el formato de su ejecutor ("" = el de por defecto del ejecutor o del perfil)."""
    m = efectivos(slug).get(etapa, (LIGERO, ""))[0]
    if ejecutor == "claude":
        if m.startswith("anthropic/"):
            return m.split("/", 1)[1].replace(".", "-")
        return m
    if ejecutor == "hermes":
        prov = proveedor if proveedor is not None else proveedor_de(perfil_hermes)
        if prov == "openrouter":
            if m in ALIAS:
                ids = modelos_openrouter().get(m)
                return ids[0] if ids else OPENROUTER_DEFECTO[m]
            return m if "/" in m else ""
        if prov == "anthropic":
            if m in ALIAS:
                ids = modelos_openrouter().get(m)
                return (ids[0] if ids else OPENROUTER_DEFECTO[m]).split("/", 1)[1].replace(".", "-")
            return m.split("/", 1)[1].replace(".", "-") if m.startswith("anthropic/") else m
        return ""   # otro proveedor (p. ej. ChatGPT): el modelo del perfil
    return ""


def poner_perfil(perfil: str) -> dict:
    if perfil not in PERFILES:
        raise Rechazo(f"Perfil de modelos desconocido: {perfil}. Perfiles: {', '.join(PERFILES)}")
    with B.cerrojo("yt"):
        cfg = config_global()
        cfg["perfil_modelos"] = perfil
        B.escribir(B.home() / "yt.json", cfg)
    return cfg


def _valido(modelo: str) -> bool:
    return modelo in ALIAS or bool(re.fullmatch(r"[a-z0-9][a-z0-9._/-]{2,80}", modelo))


def poner(etapa: str, modelo: str, slug: str | None = None, quien: str = "") -> dict:
    """Cambia el modelo de una etapa (global o de un canal). «-» quita el cambio."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", etapa):
        raise Rechazo(f"Etapa no válida: {etapa}")
    if modelo != "-" and not _valido(modelo):
        raise Rechazo(f"Modelo no válido: {modelo}. Alias: {', '.join(ALIAS)}, o un id completo")
    if modelo == "haiku" and etapa in PIENSAN:
        raise Rechazo(f"Haiku no sirve para «{etapa}»: es una etapa de juicio")
    if slug:
        C = _cargar("hyt_canales")
        mods = dict(C.leer(slug).get("modelos") or {})
        if modelo == "-":
            mods.pop(etapa, None)
        else:
            mods[etapa] = modelo
        return C.config(slug, "modelos", mods, quien)
    with B.cerrojo("yt"):
        cfg = config_global()
        mods = dict(cfg.get("modelos") or {})
        if modelo == "-":
            mods.pop(etapa, None)
        else:
            mods[etapa] = modelo
        cfg["modelos"] = mods
        B.escribir(B.home() / "yt.json", cfg)
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt_modelos.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("ver"); v.add_argument("--canal")
    p = sub.add_parser("para"); p.add_argument("etapa"); p.add_argument("ejecutor")
    p.add_argument("--canal"); p.add_argument("--perfil"); p.add_argument("--proveedor")
    pf = sub.add_parser("perfil"); pf.add_argument("perfil")
    po = sub.add_parser("poner"); po.add_argument("etapa"); po.add_argument("modelo"); po.add_argument("--canal")
    po.add_argument("--quien", default="")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "ver":
            nombres = dict(ETAPAS_MODELO)
            for e, (m, o) in efectivos(x.canal).items():
                print(f"{nombres.get(e, e):32} {m:12} ({o})")
        elif x.cmd == "para":
            print(para(x.etapa, x.ejecutor, x.canal, x.perfil, x.proveedor))
        elif x.cmd == "perfil":
            print(NOMBRE_PERFIL[poner_perfil(x.perfil)["perfil_modelos"]])
        elif x.cmd == "poner":
            poner(x.etapa, x.modelo, x.canal, x.quien)
            print("ok")
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
