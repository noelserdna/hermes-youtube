"""La memoria de cada canal (su wiki llm-wiki) se escribe SOLA, sin modelo, en momentos fijos, y cada etapa lee lo que
le toca. Las páginas fijas viven en wiki/concepts/:

  canal.md         el canal: quién presenta, idioma, pilares, formatos y reglas   ← alta y cambios de configuración
  decisiones.md    cada puerta decidida: qué, quién, resultado                    ← al firmar una puerta
  correcciones.md  lo que la persona pidió rehacer o por qué rechazó              ← al firmar una puerta con texto
  voz.md           cómo habla quien presenta                                      ← al aprobar la puerta del perfil de voz

Las páginas derivadas (decisiones, correcciones) se REGENERAN desde los registros (puertas.jsonl): son idempotentes.
Una pipeline puede declarar «memoria»: {pagina, de, seccion?} para dejar una página al cerrarse (así llega voz.md).
Nada aquí frena al notario ni a una etapa: cualquier fallo se ignora.

  hyt_wiki.py sembrar <canal>   ·   hyt_wiki.py para <canal> <etapa>
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import time
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

PAGINAS = {   # nombre → (título, etiquetas)
    "canal": ("El canal: quién presenta, pilares y reglas", ["canal", "pilar", "formato"]),
    "decisiones": ("Decisiones en las puertas", ["decision"]),
    "correcciones": ("Correcciones pedidas por la persona", ["decision", "correccion"]),
    "voz": ("La voz de quien presenta", ["voz"]),
}
LEE_DEFECTO = ["canal", "correcciones"]
_CON_VOZ = ["canal", "voz", "correcciones"]
LEE = {"escaleta": _CON_VOZ, "escribir": _CON_VOZ, "voz": _CON_VOZ, "retencion": _CON_VOZ, "ajustar": _CON_VOZ}   # por id de etapa; el resto, LEE_DEFECTO
MAX_LEER = 6000


def _wiki(slug: str) -> Path:
    return C.carpeta(slug) / "wiki"


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


def _git(w: Path, mensaje: str) -> None:
    if not (w / ".git").exists():
        return
    try:
        subprocess.run(["git", "-C", str(w), "add", "-A"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(w), "-c", "user.name=hermes-youtube", "-c", "user.email=hermes-youtube@localhost",
                        "commit", "-q", "-m", mensaje], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def escribir(slug: str, nombre: str, cuerpo: str, fuentes: list | None = None, nota_log: str = "") -> bool:
    """(Re)escribe una página fija con su cabecera, la pone en index.md y apunta en log.md. Nunca lanza."""
    try:
        w = _wiki(slug)
        if not w.is_dir():
            return False
        titulo, tags = PAGINAS[nombre]
        f = w / "concepts" / f"{nombre}.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        creado = _hoy()
        if f.exists():
            m = re.search(r"^created: (\S+)", f.read_text(errors="replace"), re.M)
            creado = m.group(1) if m else creado
        nuevo = (f"---\ntitle: {titulo}\ncreated: {creado}\nupdated: {_hoy()}\ntype: concept\ntags: [{', '.join(tags)}]\n"
                 f"sources: [{', '.join(fuentes or ['hermes-youtube'])}]\nconfidence: high\n---\n\n# {titulo}\n\n"
                 f"_Página que escribe hermes-youtube sola; no la edites a mano (se regenera)._\n\n{cuerpo.strip()}\n")
        if f.exists() and f.read_text(errors="replace").split("\n---\n", 1)[-1] == nuevo.split("\n---\n", 1)[-1]:
            return True   # sin cambios
        f.write_text(nuevo)
        idx = w / "index.md"
        s = idx.read_text(errors="replace") if idx.exists() else f"# Wiki\n\n## Concepts\n"
        if f"[[{nombre}]]" not in s:
            linea = f"- [[{nombre}]] — {titulo} (la escribe hermes-youtube)"
            s = s.replace("## Concepts\n", f"## Concepts\n{linea}\n", 1) if "## Concepts\n" in s else s.rstrip() + f"\n\n## Concepts\n{linea}\n"
            idx.write_text(s)
        with open(w / "log.md", "a") as lg:
            lg.write(f"- {_hoy()} · {nota_log or 'actualizada'} → [[{nombre}]]\n")
        _git(w, f"hermes-youtube: {nombre} ({nota_log or 'actualizada'})")
        return True
    except Exception:   # noqa: BLE001 — la memoria nunca frena el sistema
        return False


def _jsonl(p: Path) -> list:
    try:
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


# ── páginas derivadas de los registros (idempotentes) ───────────────────────────────────────────────────────────────
def regenerar_decisiones(slug: str) -> None:
    d = C.carpeta(slug)
    filas = [r for r in _jsonl(d / "puertas.jsonl") if not r.get("evento")]   # los eventos (un dato verificado) no son decisiones
    dec = [f"- {str(r.get('ts'))[:10]} · {r.get('tipo')} · **{r.get('verbo')}** por {r.get('firma') or r.get('persona')}"
           f"{' (forzada: ' + r['forzado'] + ')' if r.get('forzado') else ''} → {str(r.get('resultado', ''))[:120]}"
           f" (encargo {r.get('encargo') or '—'}, puerta {r.get('puerta')})" for r in filas]
    escribir(slug, "decisiones", "\n".join(dec[-80:]) or "Aún no hay decisiones.", ["puertas.jsonl"], "decisión en una puerta")
    cor = [f"- {str(r.get('ts'))[:10]} · {r.get('tipo')} ({r.get('verbo')}, encargo {r.get('encargo') or '—'}): «{str(r.get('texto')).strip()[:500]}»"
           for r in filas if str(r.get("texto") or "").strip() and r.get("verbo") in ("cambios", "rechazo")]
    if cor:
        escribir(slug, "correcciones", "Lo que la persona pidió rehacer o por qué rechazó. **Tenlo en cuenta para no repetirlo.**\n\n"
                 + "\n".join(cor[-60:]), ["puertas.jsonl"], "corrección de la persona")


def regenerar_canal(slug: str) -> None:
    cfg = C.leer(slug)
    l = [f"- Canal: {cfg.get('nombre')} (nombre corto: {slug})",
         f"- Presenta: {cfg.get('presentador') or '—'}",
         f"- Idioma: {cfg.get('idioma')} · zona horaria: {cfg.get('zona_horaria')}"]
    if cfg.get("pilares"):
        l.append("- Pilares: " + "; ".join(f"{p.get('nombre')} ({p.get('id')}, {p.get('tipo', 'pilar')})" for p in cfg["pilares"]))
    if cfg.get("formatos"):
        l.append("- Formatos: " + "; ".join(str(f) for f in cfg["formatos"]))
    if cfg.get("reglas"):
        l.append("- Reglas: " + json.dumps(cfg["reglas"], ensure_ascii=False))
    for k, t in (("prohibidas", "Expresiones que no se usan"), ("cierres_prohibidos", "Cierres que no se usan"),
                 ("titulo_cliches", "Clichés de título vetados"), ("excluido", "Contenido excluido"),
                 ("sin_promesas", "Promesas que no se hacen")):
        if cfg.get(k):
            l.append(f"- {t}: " + "; ".join(C.texto_patron(x) for x in cfg[k]))
    if cfg.get("nombres_vetados"):   # los nombres no se copian a la memoria: solo cuántos hay
        l.append(f"- Nombres vetados: {len(cfg['nombres_vetados'])} (en la configuración del canal)")
    permite = cfg.get("permite") or {}
    if permite:
        l.append("- Permite: " + ", ".join(f"{k}: {'sí' if v else 'no'}" for k, v in permite.items()))
    pol = cfg.get("politicas") or {}
    if pol:
        l.append(f"- Operación: {json.dumps(pol, ensure_ascii=False)}")
    escribir(slug, "canal", "\n".join(l), ["canal.json"], "configuración del canal")


def de_salida(slug: str, eid: str, memoria: dict) -> None:
    """Fin de una pipeline que declara «memoria»: {pagina, de, seccion?, entera?}: copia esa sección de su salida
    (enlazada). Se recorta salvo que la pipeline la pida «entera» (la guía de voz se usa completa)."""
    try:
        f = C.carpeta(slug) / "encargos" / eid / memoria["de"]
        texto = f.read_text(errors="replace")
        sec = memoria.get("seccion")
        if sec:
            m = re.search(rf"^(#+)\s*{re.escape(sec)}.*?$\n(.*?)(?=^\1\s|\Z)", texto, re.M | re.S)
            texto = m.group(2) if m else texto
        texto = texto.strip() if memoria.get("entera") else texto.strip()[:MAX_LEER]
        cuerpo = f"Sale del encargo `{eid}` ({memoria['de']}). Ver el original para el detalle.\n\n{texto}"
        escribir(slug, memoria["pagina"], cuerpo, [f"encargo {eid}"], f"cierre de {eid}")
    except Exception:   # noqa: BLE001
        pass


def para_etapa(slug: str, etapa: str, lee: list | None = None) -> str:
    """Extractos de las páginas que le tocan a una etapa (≤ MAX_LEER). Las páginas-registro, por la cola."""
    w = _wiki(slug) / "concepts"
    partes = []
    paginas = lee or LEE.get(etapa) or LEE_DEFECTO
    for nombre in paginas:
        f = w / f"{nombre}.md"
        if not f.exists():
            continue
        s = f.read_text(errors="replace").split("\n---\n", 1)[-1].strip()
        s = re.sub(r"^_Página que escribe.*?_\n+", "", re.sub(r"^# .*\n+", "", s), flags=re.S)
        tope = MAX_LEER // max(1, len(paginas))
        partes.append(f"### {PAGINAS.get(nombre, (nombre,))[0]}\n" + (s if len(s) <= tope else "…\n" + s[-tope:]))
    return "\n\n".join(partes)[:MAX_LEER]


def ultimas(slug: str, n: int = 4) -> list:
    try:
        return [l.strip() for l in (_wiki(slug) / "log.md").read_text().splitlines() if l.startswith("- ")][-n:]
    except OSError:
        return []


def iniciar(slug: str) -> bool:
    """Deja la wiki del canal lista (idempotente): index, log, SCHEMA con las páginas fijas y su repositorio git."""
    w = _wiki(slug)
    (w / "concepts").mkdir(parents=True, exist_ok=True)
    if not (w / "index.md").exists():
        (w / "index.md").write_text("# Wiki\n\n## Concepts\n")
    if not (w / "log.md").exists():
        (w / "log.md").write_text("")
    try:   # el SCHEMA del canal conoce las páginas fijas
        nombre = C.leer(slug).get("nombre") or slug
        plantilla = (_cargar("hyt_pipelines").raiz() / "plantillas" / "wiki" / "SCHEMA.md").read_text().replace("{{CANAL}}", nombre)
        sch = w / "SCHEMA.md"
        if not sch.exists():
            sch.write_text(plantilla)
        elif "## Fixed pages" not in sch.read_text():
            sch.write_text(sch.read_text().rstrip() + "\n\n" + plantilla[plantilla.index("## Fixed pages"):])
    except (OSError, ValueError):
        pass
    if not (w / ".git").exists():
        try:
            subprocess.run(["git", "-C", str(w), "init", "-q"], capture_output=True, timeout=30)
            _git(w, "Wiki del canal")
        except (OSError, subprocess.SubprocessError):
            pass
    return (w / ".git").exists()


def sembrar(slug: str) -> list:
    """Primera siembra (idempotente): la wiki con su SCHEMA y su git, y las páginas canal, decisiones y correcciones."""
    C.leer(slug)
    iniciar(slug)
    regenerar_canal(slug)
    regenerar_decisiones(slug)
    return ["canal", "decisiones/correcciones"]


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["sembrar"] and len(a) == 2:
            print("Sembrado: " + ", ".join(sembrar(a[1])))
        elif a[:1] == ["para"] and len(a) == 3:
            print(para_etapa(a[1], a[2]))
        else:
            print(__doc__, file=sys.stderr)
            sys.exit(2)
    except B.Rechazo as x:
        print(str(x), file=sys.stderr)
        sys.exit(2)
