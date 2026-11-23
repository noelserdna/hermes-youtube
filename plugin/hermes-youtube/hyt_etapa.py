"""Ejecuta UNA etapa de un encargo (lo llama etapa.sh desde la tarjeta del kanban). Como etapa.sh de hermes-sdd:
elige ejecutor y modelo, monta el encargo para el agente, lo lanza, comprueba que dejó su salida, lo apunta y, si es la
última etapa, abre la puerta de la pipeline.

  hyt_etapa.py <slug> <encargo> <etapa>

Última línea de stdout: JSON {outcome: done|failed|scheduled|busy, reason, resumen, puerta, run, cost_usd, minutes}.
La estación solo traduce `outcome` a una acción del kanban.
"""
from __future__ import annotations

import importlib.util
import json
import os
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
PL = _cargar("hyt_pipelines")
E = _cargar("hyt_encargos")
M = _cargar("hyt_modelos")


def _vinetas(titulo: str, elementos: list) -> list:
    return ["", f"## {titulo}", *[f"- {x}" for x in elementos]] if elementos else []


def contexto(slug: str, etapa: str | None = None) -> str:
    """Lo que todo agente sabe del canal (el plugin lo pone también en el prompt de los perfiles): contexto-canal.md."""
    cfg = C.leer(slug)
    d = C.carpeta(slug)
    arnes = PL.raiz()
    pilares = cfg.get("pilares") or []
    l = [f"# Canal: {cfg['nombre']}", "",
         f"- Nombre corto (para las herramientas: --canal): {slug}",
         f"- Nombre: {cfg['nombre']}",
         f"- Presenta: {cfg.get('presentador') or '—'}",
         f"- Idioma: {cfg['idioma']} · zona: {cfg.get('zona_horaria', '')}",
         "- Pilares: " + ("; ".join(f"{p.get('nombre')} ({p.get('id')}, {p.get('tipo', 'pilar')})" for p in pilares) or "sin definir"),
         "- Formatos: " + ("; ".join(str(f) for f in cfg.get("formatos") or []) or "sin definir"),
         f"- Capacidades: {', '.join(sorted(C.capacidades(cfg))) or 'ninguna'}"]
    l += _vinetas("Reglas del canal (obligatorias; las comprueba el código)",
                  [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in (cfg.get("reglas") or {}).items()])
    for clave, titulo in (("prohibidas", "Expresiones prohibidas"), ("cierres_prohibidos", "Cierres prohibidos"),
                          ("titulo_cliches", "Clichés de título vetados"),
                          ("excluido", "Contenido excluido (no entra en ningún resultado)"),
                          ("sin_promesas", "Promesas que no se hacen")):
        l += _vinetas(titulo, [C.texto_patron(x) for x in cfg.get(clave) or []])
    if cfg.get("nombres_vetados"):   # no se enumeran: el código los comprueba y ningún resultado debe traerlos
        l += ["", f"Nombres vetados: {len(cfg['nombres_vetados'])} (no se listan aquí; no nombres a ninguna persona "
                  "que no sea quien presenta salvo que el material lo permita expresamente)."]
    l += _vinetas("Lo que el canal permite", [f"{k}: {'sí' if v else 'no'}" for k, v in (cfg.get("permite") or {}).items()])
    l += ["", "## Dónde está cada cosa",
          f"- Memoria del canal (wiki): {d / 'wiki'} (empieza por index.md; enlaza, no copies)",
          f"- Fuentes del canal (material propio, solo lectura): {d / 'fuentes'}",
          f"- Inventario de piezas: {d / 'inventario.json'}",
          f"- Referencias de oficio del plugin: {arnes / 'referencias'}"]
    if etapa == "investigar":   # la única etapa que sale fuera: YouTube con la herramienta del plugin, la web con la suya
        l += [f"- YouTube (buscar, transcripción, existe): python3 {Path(__file__).resolve().parent / 'hyt_youtube.py'} --help"]
    if etapa:
        try:
            mem = _cargar("hyt_wiki").para_etapa(slug, etapa, _lee(slug, etapa))
        except Exception:   # noqa: BLE001
            mem = ""
        if mem:
            l += ["", "## Memoria que te toca (de la wiki del canal; la escribe el sistema)", mem]
    lecciones = _lecciones(slug, etapa)
    if lecciones:
        l += ["", "## Lecciones de otros canales (confirmadas por una persona)", *[f"- {x}" for x in lecciones]]
    return "\n".join(l) + "\n"


def _lee(slug: str, etapa: str) -> list | None:
    """Páginas de memoria que declara la etapa («lee»), si las declara en alguna pipeline del canal."""
    try:
        for p in PL.listar(slug).values():
            for s in p.get("etapas") or []:
                if s.get("id") == etapa and s.get("lee"):
                    return s["lee"]
    except Exception:   # noqa: BLE001
        pass
    return None


def _lecciones(slug: str, etapa: str | None) -> list:
    """Lecciones confirmadas de otros canales: las de la etapa (y se anota el uso) o, sin etapa, todas sin anotar."""
    try:
        return _cargar("hyt_lecciones").para_canal(slug, etapa, anotar=etapa is not None)
    except Exception:
        return []


PROMPT = """Harness mode (hermes-youtube). You are doing ONE stage of a pipeline for a YouTube channel.
Stage: {etapa} — {titulo}
Skill to follow: {skill}{ruta_skill}
Working folder: {dir} (write only here; read brief.md and contexto-canal.md first)
Earlier stages left: {previas}
Write your result to: {salida}
If {salida} already exists it is from an earlier attempt: write it again, complete.
Write for people in the channel's language ({idioma}).
Use ONLY the channel's own material (its sources, its inventory, its wiki and what earlier stages left): do not invent
figures, cases, names or anecdotes. Whatever is not in that material goes to the list of facts to verify.
Do NOT publish or upload anything, do NOT contact anyone (no messages, no e-mail) and do NOT change the channel's
configuration, its sources or its wiki: a person decides at a gate after this pipeline. If something blocks you, write
why in {salida} and stop.
End your reply with ONE short line summarising the result."""

# Pasos de código alrededor de una etapa (hyt_pasos.py): lo que no se deja a un modelo.
#   «prepara»: antes. Deja en el encargo lo que la etapa necesita. Puede devolver {"saltar": motivo}: la etapa no corre.
#   «tras»: después. Comprueba y transforma la salida. Puede devolver {"fallo": motivo}: la etapa cuenta como fallida.
def _pasos():
    return _cargar("hyt_pasos")


def preparar(slug: str, d: Path, nombre: str, enc: dict | None = None) -> dict:
    if os.environ.get("HYT_SIN_PASOS"):   # las pruebas del núcleo corren las etapas sin los pasos de código
        return {}
    f = _pasos().PREPARA.get(nombre)
    return (f(slug, d, enc or {}) or {}) if f else {}


def tras(slug: str, d: Path, nombre: str, enc: dict | None = None) -> dict:
    if os.environ.get("HYT_SIN_PASOS"):
        return {}
    f = _pasos().TRAS.get(nombre)
    return (f(slug, d, enc or {}) or {}) if f else {}


def ejecutar(slug: str, eid: str, etapa: str) -> dict:
    enc = E.leer(slug, eid)
    d = E.carpeta(slug, eid)
    cfg = C.leer(slug)
    if (cfg.get("politicas") or {}).get("pausado") or (B.home() / "pausa").exists():
        return {"outcome": "scheduled", "reason": "en pausa", "reset_at": int(time.time()) + 3600}
    cuota = B.leer(B.home() / "cuota.json", {}) or {}
    if float(cuota.get("reset_at") or 0) > time.time():
        return {"outcome": "scheduled", "reason": "cuota de Claude agotada", "reset_at": cuota["reset_at"]}
    p = PL.cargar(enc["pipeline"], slug)
    s = next((x for x in p["etapas"] if x["id"] == etapa), None)
    if not s or etapa not in [x["id"] for x in enc["etapas"]]:
        return {"outcome": "failed", "reason": f"la etapa {etapa} no es de este encargo"}
    orden = [x["id"] for x in enc["etapas"]]
    salidas = {x["id"]: x.get("salida") for x in p["etapas"]}
    previas = [f"{salidas[i]} ({i})" for i in orden[:orden.index(etapa)] if salidas.get(i) and (d / salidas[i]).exists()]
    previas += [f"{h} (from {enc['origen']})" for h in enc.get("heredados") or [] if (d / h).exists()]
    salida = s.get("salida") or f"{etapa}.md"
    (d / "contexto-canal.md").write_text(contexto(slug, etapa))
    for nombre in s.get("prepara") or []:
        try:
            r0 = preparar(slug, d, nombre, enc)
        except B.Rechazo as e:
            return {"outcome": "failed", "reason": f"no se pudo preparar la etapa ({nombre}): {e}", "salida": salida}
        if r0.get("saltar"):
            return {"outcome": "done", "resumen": f"etapa saltada: {r0['saltar']}", "saltada": True, "salida": salida,
                    "ejecutor": "codigo", "modelo": ""}
    ejecutor = (cfg.get("ejecutores") or {}).get(etapa) or s.get("ejecutor", "hermes")
    arnes = PL.raiz()
    propia = C.carpeta(slug) / "extensiones" / "skills" / s["skill"] / "SKILL.md"   # las del canal mandan
    skill_md = propia if propia.exists() else arnes / "skills" / s["skill"] / "SKILL.md"
    if ejecutor == "claude" and not skill_md.exists():
        return {"outcome": "failed", "reason": f"no encuentro la skill {s['skill']} (ni en el canal ni en el plugin)"}
    titulo = next(x["titulo"] for x in enc["etapas"] if x["id"] == etapa)
    prompt = PROMPT.format(etapa=etapa, titulo=titulo, skill=s["skill"], dir=d, salida=salida, idioma=cfg["idioma"],
                           previas=", ".join(previas) or "nothing (first stage)",
                           ruta_skill=f" (read {skill_md})" if ejecutor == "claude" else "")
    feedback = d / ".estado" / f"feedback-{etapa}.txt"
    if feedback.exists():
        prompt += "\n\nWhat the person asked to change last time (apply it):\n" + feedback.read_text()[:4000]
    fb_verif = d / ".estado" / f"feedback-verificacion-{etapa}.txt"
    if fb_verif.exists():
        prompt += ("\n\nThe check of your previous version asked for changes. Apply EVERY mandatory change below "
                   "(and keep what was right):\n" + fb_verif.read_text()[:4000])
    modelo = M.para(etapa, ejecutor, slug, s["perfil"])
    antes = (d / salida).stat().st_mtime if (d / salida).exists() else 0
    env = {**os.environ, "HERMES_YT_HOME": str(B.home())}
    if ejecutor == "claude":   # Claude Code con la sesión de la cuenta (si el sistema la guarda en los secretos)
        sec = C.secretos(slug)
        if sec.get("CLAUDE_CODE_OAUTH_TOKEN"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = sec["CLAUDE_CODE_OAUTH_TOKEN"]
    ejecutores = Path(os.environ.get("HYT_EJECUTORES") or arnes / "executors")   # las pruebas ponen los suyos
    if not (ejecutores / f"{ejecutor}.sh").exists():
        return {"outcome": "failed", "reason": f"no existe el ejecutor «{ejecutor}»"}
    cmd = ["bash", str(ejecutores / f"{ejecutor}.sh"), str(d), f"{etapa}", prompt, modelo, s["perfil"], s["skill"]]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    try:
        res = json.loads((r.stdout.strip().splitlines() or ["{}"])[-1])
    except ValueError:
        res = {"outcome": "failed", "reason": f"el ejecutor no devolvió JSON: {r.stdout[-200:]} {r.stderr[-200:]}"}
    if res.get("outcome") == "done":
        rehecha = any((d / ".estado" / x).exists() for x in (f"feedback-{etapa}.txt", f"feedback-verificacion-{etapa}.txt"))
        sin_tocar = (d / salida).exists() and (d / salida).stat().st_mtime <= antes
        if not (d / salida).exists() or (d / salida).stat().st_size == 0 or (sin_tocar and not rehecha):
            res = {**res, "outcome": "failed", "reason": f"la etapa terminó sin dejar {salida}"}
        else:
            if sin_tocar:   # al rehacer, puede que lo pedido ya estuviera: lo confirman las etapas siguientes
                res = {**res, "resumen": (res.get("resumen") or "") + f" (sin cambios en {salida}: lo pedido ya estaba)"}
            for nombre in s.get("tras") or []:
                try:
                    r1 = tras(slug, d, nombre, enc)
                except B.Rechazo as e:
                    r1 = {"fallo": str(e)}
                if r1.get("fallo"):
                    res = {**res, "outcome": "failed", "reason": r1["fallo"]}
                    break
                if r1.get("resumen"):
                    res = {**res, "resumen": r1["resumen"]}
    return {**res, "salida": salida, "ejecutor": ejecutor, "modelo": modelo}


def fin(slug: str, eid: str, etapa: str, res: dict, t0: float) -> dict:
    enc = E.leer(slug, eid)
    ultima = enc["etapas"][-1]["id"] == etapa
    res.setdefault("resumen", "")
    s = next((x for x in PL.cargar(enc["pipeline"], slug)["etapas"] if x["id"] == etapa), {})
    clave_vueltas = "vueltas_verificacion" if etapa == "verificar" else f"vueltas_{etapa}"   # una vuelta por etapa
    if res.get("outcome") == "done" and s.get("si_cambios") and int(enc.get(clave_vueltas) or 0) == 0:
        d = E.carpeta(slug, eid)
        f = d / (s.get("salida") or f"{etapa}.md")
        if _cargar("hyt_revision")._veredicto(f) == "CAMBIOS":
            # una sola vuelta automática: el texto vuelve a la etapa indicada con los cambios pedidos, sin pasar por
            # la persona; las tarjetas siguientes no deben arrancar (la tarjeta se da por fallida y la rehace el bucle)
            (d / f"{f.stem}-1{f.suffix}").write_text(f.read_text(errors="replace"))
            enc.update(estado="en-vuelta", **{clave_vueltas: 1},
                       vuelta_pendiente={"desde": s["si_cambios"], "texto": f.read_text(errors="replace")[:4000]})
            E.guardar(slug, enc)
            res = {**res, "outcome": "failed", "reason": f"la verificación pidió cambios: vuelve a {s['si_cambios']} (una vez)",
                   "vuelta": s["si_cambios"]}
            B.anotar(C.carpeta(slug) / "etapas.jsonl", {
                "ts": B.ahora(), "encargo": eid, "pipeline": enc["pipeline"], "etapa": etapa,
                "tarjeta": (enc.get("tarjetas") or {}).get(etapa, ""), "resultado": "cambios", "motivo": res["reason"],
                "ejecutor": res.get("ejecutor", ""), "modelo": res.get("modelo", ""),
                "minutos": round((time.time() - t0) / 60, 1), "coste_usd": res.get("cost_usd", 0), "puerta": ""})
            return res
    con_puerta = bool(PL.puertas_de(enc))
    if res.get("outcome") == "done" and ultima and not con_puerta \
            and isinstance(PL.cargar(enc["pipeline"], slug).get("memoria"), dict):
        # sin puerta, la memoria se escribe al acabar; con puerta, la escribe el notario cuando una persona aprueba
        _cargar("hyt_wiki").de_salida(slug, eid, PL.cargar(enc["pipeline"], slug)["memoria"])
    if res.get("outcome") == "done" and ultima:
        # toda pipeline que declara puerta se para en ella: aquí decide una persona aunque aprobar no lance nada más
        enc["estado"] = "en-puerta" if con_puerta else "hecho"
        if not con_puerta:
            enc["informe"] = True   # acabó sin puerta: su resultado se enseña en el estado
        E.guardar(slug, enc)
        if con_puerta:
            try:   # la cadena de puertas empieza (o vuelve a empezar) por la primera que no se salte
                g = _cargar("hyt_puertas").abrir_inicial(slug, eid)   # con gemelos, espera al otro
                if g:
                    res["puerta"] = g["id"]
                elif E.leer(slug, eid).get("estado") in ("esperando-gemelo", "descartado"):
                    res["resumen"] = (res.get("resumen") or "") + f" · {E.leer(slug, eid)['estado']}"
                else:
                    res["puerta_error"] = "la cadena de puertas no deja ninguna que abrir"
            except Exception as x:   # la etapa hizo su trabajo: el fallo al abrir la puerta queda a la vista
                res["puerta_error"] = str(x)[:300]
    elif res.get("outcome") == "failed":
        enc["estado"] = "parado"
        E.guardar(slug, enc)
        if enc.get("gemelos"):
            try:   # si el gemelo ya acabó y lo esperaba, sigue solo
                _cargar("hyt_puertas").gemelo_fallo(slug, eid)
            except Exception:   # noqa: BLE001
                pass
    B.anotar(C.carpeta(slug) / "etapas.jsonl", {
        "ts": B.ahora(), "encargo": eid, "pipeline": enc["pipeline"], "etapa": etapa,
        "tarjeta": (enc.get("tarjetas") or {}).get(etapa, ""), "resultado": res.get("outcome"),
        "motivo": res.get("reason", ""), "ejecutor": res.get("ejecutor", ""), "modelo": res.get("modelo", ""),
        "minutos": round((time.time() - t0) / 60, 1), "coste_usd": res.get("cost_usd", 0),
        "puerta": res.get("puerta", "")})
    return res


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 3:
        print(json.dumps({"outcome": "failed", "reason": "uso: hyt_etapa.py <slug> <encargo> <etapa>"}))
        return 0
    t0 = time.time()
    try:
        res = ejecutar(*argv)
    except B.Rechazo as e:
        res = {"outcome": "failed", "reason": str(e)}
    try:
        res = fin(*argv, res, t0)
    except B.Rechazo as e:
        res = {**res, "outcome": "failed", "reason": str(e)}
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
