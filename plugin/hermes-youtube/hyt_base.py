"""Utilidades comunes de hermes-youtube: dónde vive el estado, lectura y escritura atómica de JSON, cerrojo entre procesos
y el error con mensaje para la persona. Copiado y adaptado de hermes-sdd (hsdd_nucleo.py).

El estado nunca vive en el repositorio del plugin: está en HERMES_YT_HOME (por defecto ~/.hermes/hermes-youtube), con
los datos de cada canal en canales/<slug>/.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def home() -> Path:
    """Se lee en cada llamada (no al importar) para que las pruebas y la CLI puedan cambiar HERMES_YT_HOME."""
    return Path(os.environ.get("HERMES_YT_HOME", Path.home() / ".hermes" / "hermes-youtube"))


def desacoplar(cmd: list) -> list:
    """Un proceso largo (despliegue, script de una puerta) que debe sobrevivir a un reinicio del gateway: con systemd de
    usuario (linger) se lanza en su propio scope, fuera del cgroup del servicio; si no hay, tal cual (start_new_session)."""
    if os.environ.get("HYT_SIN_SCOPE") or not shutil.which("systemd-run"):
        return cmd
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not os.path.isdir(xdg):
        return cmd
    return ["env", f"XDG_RUNTIME_DIR={xdg}", "systemd-run", "--user", "--scope", "--quiet", "--collect", *cmd]


class Rechazo(Exception):
    """Algo que la persona (o el agente) pidió y no se puede hacer; el mensaje se le enseña tal cual."""


def leer(p: Path, defecto=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return defecto


def escribir(p: Path, datos, modo: int | None = None) -> None:
    """Escritura atómica (temporal + rename): un lector nunca ve un JSON a medias."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n")
    if modo is not None:
        os.chmod(tmp, modo)
    tmp.replace(p)


def anotar(p: Path, registro: dict) -> None:
    """Añade una línea a un .jsonl (los registros solo crecen)."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextlib.contextmanager
def cerrojo(nombre: str = "estado"):
    """Exclusión entre procesos (gateway, panel, CLI) para leer-modificar-escribir. Sección corta y sin esperas."""
    d = home() / ".cerrojos"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / nombre, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
RESERVADOS = {"default", "todo", "todos", "local", "cartera", "global"}


def validar_slug(slug: str) -> str:
    if not isinstance(slug, str) or not SLUG.match(slug) or "--" in slug:
        raise Rechazo("El nombre corto del canal va en minúsculas, con letras, números y guiones (3-40 caracteres)")
    if slug in RESERVADOS:
        raise Rechazo(f"«{slug}» es un nombre reservado")
    return slug


# ── disco ────────────────────────────────────────────────────────────────────────────────────────────────────────────
AVISO_DISCO = 85   # % usado a partir del que el estado y el panel avisan (HYT_AVISO_DISCO lo cambia)


def disco(rutas=None) -> list:
    """[{punto, usado_pct, libres_gb, total_gb, aviso}] de cada sistema de ficheros distinto entre las rutas (por
    defecto la carpeta de datos de hermes-youtube)."""
    umbral = int(os.environ.get("HYT_AVISO_DISCO") or AVISO_DISCO)
    vistos, out = set(), []
    for r in (rutas if rutas is not None else _rutas_disco()):
        r = Path(os.path.expanduser(str(r)))
        while not r.exists() and r != r.parent:
            r = r.parent
        try:
            dev = r.stat().st_dev
            u = shutil.disk_usage(r)
        except OSError:
            continue
        if dev in vistos:
            continue
        vistos.add(dev)
        pct = round(u.used * 100 / u.total) if u.total else 0
        out.append({"punto": _punto_montaje(r), "usado_pct": pct, "libres_gb": round(u.free / 1e9, 1),
                    "total_gb": round(u.total / 1e9, 1), "aviso": pct >= umbral})
    return out


def _punto_montaje(r: Path) -> str:
    r = r.resolve()
    while not os.path.ismount(r) and r != r.parent:
        r = r.parent
    return str(r)


def _rutas_disco() -> list:
    """Todo lo de hermes-youtube (canales, fuentes, encargos, wiki) vive bajo su carpeta de datos."""
    return [home()]


def disco_linea(d: list | None = None) -> str:
    """«💾 Disco: 84 % usado, 4,8 GB libres» (una entrada por sistema de ficheros si hay varios)."""
    d = disco() if d is None else d
    partes = []
    for x in d:
        libres = f"{x['libres_gb']:.1f}".replace(".", ",")
        donde = f" en {x['punto']}" if len(d) > 1 else ""
        partes.append(f"{'⚠️' if x['aviso'] else '💾'} Disco{donde}: {x['usado_pct']} % usado, {libres} GB libres")
    return " · ".join(partes)
