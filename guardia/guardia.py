"""Guardia de la COORDINADORA de hermes-youtube (hook pre_tool_call de Hermes, fail-closed).
Copiado y adaptado de hermes-sdd (encargado/guardia.py).

  python3 -I guardia.py <arnés>       (lee el evento de stdin)

La coordinadora (perfil default) ve todos los canales. Tres niveles para mover el sistema, todos por la CLI `hyt`
(nunca por otra vía):
  · sola            consultar (también los vídeos y los publicados),     → se permite
                    exportar un vídeo aprobado, lanzar pipelines,
                    reintentar una vez, proponer lecciones, sembrar la memoria
  · con aprobación  alta, config, pausar, reanudar, modelos, fuentes,    → {"action":"approve"}: Hermes pregunta a la
                    lanzar con --excepcion                                 persona; en un cron no hay nadie y se deniega
  · nunca           decidir o firmar puertas, secretos, aprobadores,     → bloqueado (y la CLI ni siquiera lo ofrece)
                    código del arnés, configuración de Hermes
Además: ficheros solo en las wikis (la global y la de cada canal); terminal con una lista blanca de lectura; sin
execute_code, delegate_task ni cronjob.

Bloquear = imprimir {"decision":"block","reason":…} y salir con 2 (dialecto de Hermes). Permitir = salir con 0.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

ARNES = os.path.realpath(sys.argv[1])
ARNES_RUTAS = {ARNES, os.path.abspath(os.path.expanduser(sys.argv[1]))}
HYT = os.path.realpath(os.environ.get("HERMES_YT_HOME") or os.path.expanduser("~/.hermes/hermes-youtube"))
HOME = os.path.realpath(os.path.expanduser("~"))   # realpath: las rutas se comparan ya resueltas
CANALES = os.path.join(HYT, "canales")
APROBAR: list = []

# rutas de escritura: la wiki global y la de cada canal
ESCRIBE = [os.path.join(HYT, "wiki")]
if os.path.isdir(CANALES):
    ESCRIBE += [os.path.join(CANALES, s, "wiki") for s in sorted(os.listdir(CANALES))]
SECRETOS = re.compile(r"(secretos\.env|aprobadores\.json|yt\.json|auth\.json|\.env\b|"
                      r"\.ssh|id_(rsa|ed25519)|\.pem\b|cuota\.json)")

LECTURA = {"ls", "cat", "head", "tail", "grep", "egrep", "rg", "wc", "jq", "sort", "uniq", "cut", "tr", "diff", "tree",
           "file", "stat", "date", "echo", "printf", "pwd", "basename", "dirname", "realpath", "column", "nl", "true",
           "cd", "test", "[", "shasum", "sha256sum", "md5sum"}
GIT_LECTURA = {"log", "show", "diff", "status", "blame", "describe", "rev-parse", "ls-files", "shortlog", "grep"}
HYT_SOLA = {"canales", "estado", "encargos", "encargo", "puertas", "puerta", "pipelines", "plan", "lanzar", "reintentar",
            "vueltas", "leccion", "lecciones", "wiki"}
HYT_APROBAR = {"alta", "config", "pausar", "reanudar", "modelos", "fuentes", "video", "publicados", "correo"}
# de las órdenes con aprobación, las acciones que solo consultan: sola
HYT_CONSULTA = {"video": {"lista", "exportar"}, "publicados": {"lista"}, "modelos": {"ver"}}
HYT_NUNCA = {"secreto": "las claves las guarda la persona desde su terminal, nunca un agente"}


def bloquear(motivo: str) -> None:
    print(json.dumps({"decision": "block", "reason": f"hermes-youtube (la coordinadora): {motivo}. Para mover el sistema "
                      "usa la CLI hyt; decidir puertas es de la persona: explícale qué harías."},
                     ensure_ascii=False))
    sys.exit(2)


def ruta(p: str, base: str) -> str:
    p = os.path.expanduser(p)
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))


def dentro(p: str, d: str) -> bool:
    return p == d or p.startswith(d.rstrip(os.sep) + os.sep)


def es_hyt(seg: list, cwd: str) -> list | None:
    """Los argumentos de hyt si el segmento es la CLI del arnés (hyt, bash <arnés>/hyt, <arnés>/hyt)."""
    if seg[0] == "hyt":
        return seg[1:]
    if os.path.basename(seg[0]) == "hyt" and dentro(ruta(seg[0], cwd), ARNES):
        return seg[1:]
    if seg[0] in ("bash", "sh") and len(seg) > 1 and os.path.basename(seg[1]) == "hyt" and dentro(ruta(seg[1], cwd), ARNES):
        return seg[2:]
    return None


def orden_hyt(args: list) -> str | None:
    if not args:
        return "hyt sin orden"
    sub = args[0]
    if sub in ("-h", "--help"):
        return None
    if sub in HYT_NUNCA:
        return HYT_NUNCA[sub]
    if sub not in HYT_SOLA | HYT_APROBAR:
        return f"hyt {sub} no es una orden conocida"
    if sub in HYT_SOLA:
        if sub == "lanzar" and "--excepcion" in args:
            pos = [a for a in args[1:] if not a.startswith("--")]
            APROBAR.append(f"Lanzar «{pos[1] if len(pos) > 1 else '?'}» para {pos[0] if pos else '?'} "
                           "saltándose el tope semanal del canal")
        return None
    if sub == "modelos" and not args[1:2]:
        return None
    if args[1:2] and args[1] in HYT_CONSULTA.get(sub, ()):
        return None
    APROBAR.append(f"hyt {' '.join(args)[:300]}")
    return None


def segmento(seg: list, cwd: str) -> str | None:
    while seg and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]):
        seg = seg[1:]
    if not seg:
        return None
    h = es_hyt(seg, cwd)
    if h is not None:
        return orden_hyt(h)
    cmd, args = os.path.basename(seg[0]), seg[1:]
    for a in args:   # leer está bien, pero no los secretos ni el resto de Hermes
        if a.startswith("-"):
            continue
        r = ruta(a, cwd)
        if SECRETOS.search(r):
            return "los secretos y los aprobadores no se leen"
        if dentro(r, os.path.join(HOME, ".hermes")) and not (dentro(r, HYT) or any(dentro(r, x) for x in ARNES_RUTAS)):
            return "el resto de Hermes no se lee desde aquí"
    if cmd in LECTURA:
        return None
    if cmd == "find":
        return None if not any(a in ("-exec", "-execdir", "-delete", "-ok", "-fprint", "-fls") for a in args) else "find con acciones"
    if cmd == "sed":
        return None if "-n" in args and not any(a.startswith("-i") or a.startswith("--in-place") for a in args) else "sed que no es solo lectura (-n)"
    if cmd == "git":
        d = cwd
        while args[:1] == ["-C"] and len(args) >= 2:
            d = ruta(args[1], d); args = args[2:]
        sub = args[0] if args else ""
        if any(dentro(d, w) for w in ESCRIBE):
            return None if sub not in ("push", "remote") else "publicar la wiki lo decide una persona"
        return None if sub in GIT_LECTURA else f"git {sub} (solo lectura fuera de las wikis)"
    return f"la orden «{cmd}» no está permitida (lectura o hyt)"


def terminal(c: str, cwd: str) -> None:
    if re.search(r"\$\(|`|<\(|>\(", c):
        bloquear("sin sustituciones de órdenes ($( ), ``)")
    sin_null = re.sub(r"\d?>&\d|\d?>\s*/dev/null", "", c)
    if ">" in sin_null:
        bloquear("sin redirecciones a ficheros: para escribir en la wiki usa write_file")
    if re.search(r"hyt_[a-z]+\.py|firmar|decidir|etapa\.sh|guardia\.py", c):
        bloquear("los módulos del arnés no se llaman directamente: usa hyt")
    try:
        lex = shlex.shlex(sin_null, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        bloquear("orden que no se puede analizar (comillas sin cerrar)")
    seg, d = [], cwd
    for t in toks + [";"]:
        if t and set(t) <= set(";&|"):
            if seg:
                if os.path.basename(seg[0]) == "cd" and len(seg) > 1:
                    d = ruta(seg[1], d)
                m = segmento(seg, d)
                if m:
                    bloquear(m)
            seg = []
        else:
            seg.append(t)


def main() -> None:
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        bloquear("evento ilegible")
    herramienta = ev.get("tool_name") or ""
    entrada = ev.get("tool_input") or {}
    base = HYT
    if herramienta in ("execute_code", "delegate_task", "cronjob"):
        bloquear(f"sin {herramienta}")
    if herramienta == "search_files":
        p = ruta(str(entrada.get("path") or entrada.get("directory") or base), base)
        if SECRETOS.search(p):
            bloquear("los secretos no se buscan")
        sys.exit(0)
    if herramienta in ("write_file", "patch"):
        p = ruta(str(entrada.get("path") or entrada.get("file_path") or ""), base)
        if "/.git/" in p + "/" or not any(dentro(p, w) for w in ESCRIBE):
            bloquear(f"solo escribe en las wikis, no en {p}")
        sys.exit(0)
    if herramienta == "read_file":
        p = ruta(str(entrada.get("path") or entrada.get("file_path") or ""), base)
        if SECRETOS.search(p):
            bloquear("los secretos no se leen")
        sys.exit(0)
    if herramienta == "terminal":
        terminal(str(entrada.get("command") or ""), ruta(str(entrada.get("workdir") or entrada.get("cwd") or base), base))
        if APROBAR:   # Hermes la pasa a su aprobación humana; sin respuesta (o en un cron) se deniega
            print(json.dumps({"action": "approve", "message": "; ".join(APROBAR),
                              "rule_key": "hermes-youtube:" + re.sub(r"\W+", "-", APROBAR[0][:40])}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
