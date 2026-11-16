"""hyt: las acciones de la coordinadora (y de quien administra, desde su terminal) sobre hermes-youtube. Es la ÚNICA
vía de la coordinadora para mover el sistema: el guardia (guardia/guardia.py) bloquea todo lo demás y decide qué
acciones necesitan la aprobación de la persona.

No hay ninguna orden para decidir o firmar puertas: eso solo pasa en una puerta (decide una persona) y lo ejecuta el
notario. Tampoco hay ninguna para publicar: hermes-youtube no publica.

  Consultar (sola)
    hyt canales · hyt estado [canal] · hyt encargos <canal> [--todos] · hyt encargo <canal> <id>
    hyt puertas [canal] · hyt puerta <id> · hyt pipelines [--canal C] · hyt plan <pipeline> <canal>
    hyt modelos ver [--canal C] · hyt lecciones [--todas]
  Trabajar (sola, y lo cuenta)
    hyt lanzar <canal> <pipeline> [--param k=v]… [--brief TEXTO]
    hyt reintentar <canal> <encargo> <etapa>          (una vez por etapa; después, una persona)
    hyt vueltas                                       (lanza las vueltas que pidió la verificación)
    hyt leccion <canal> <etapa> "<regla general>" <encargo|puerta>…   (la confirma una persona)
    hyt wiki sembrar <canal>                          (la memoria del canal: páginas fijas, sin modelo)
  Cambiar el sistema (con la aprobación de la persona)
    hyt alta <slug> "<nombre>" "<presentador>"        (crea el canal desde la plantilla y siembra su memoria)
    hyt config <canal> <clave.con.puntos> <valor>
    hyt pausar <canal|todo> · hyt reanudar <canal|todo>
    hyt modelos perfil <calidad|equilibrado|rapido> · hyt modelos poner <etapa> <modelo|-> [--canal C]
    hyt lanzar … --excepcion                          (salta el tope semanal: lo pidió una persona)
  Solo desde tu terminal
    hyt secreto guardar <canal> <CLAVE>               (pide el valor sin mostrarlo)

  hyt fuentes cargar <canal> <carpeta|zip> --coleccion <nombre> --tipo <tipo>   ·   hyt fuentes lista <canal>

Irá aquí en un paso posterior: «hyt correo …» (puertas por correo).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
PL = _cargar("hyt_pipelines")
E = _cargar("hyt_encargos")
PU = _cargar("hyt_puertas")
M = _cargar("hyt_modelos")
Rechazo = B.Rechazo


def quien() -> str:
    """Quién pide la acción: la persona (si el medio la pasa) o el perfil de Hermes que la ejecuta."""
    return os.environ.get("HYT_QUIEN") or os.environ.get("HERMES_PROFILE") or os.environ.get("USER", "")


def alta(slug: str, nombre: str, presentador: str) -> str:
    """Da de alta el canal (lo aprobó la persona) y siembra su memoria. No lanza nada: lo siguiente es cargar sus
    fuentes y sacar el inventario y el perfil de voz."""
    cfg = C.alta(slug, nombre, presentador, quien())
    lineas = [f"📺 Alta hecha: {C.resumen(cfg)}"]
    try:
        _cargar("hyt_wiki").sembrar(slug)
        lineas.append("🧠 Memoria sembrada")
    except Exception as e:   # noqa: BLE001 — el canal ya existe; la memoria se puede sembrar después
        lineas.append(f"⚠️ La memoria no se pudo sembrar ({str(e)[:120]}): hyt wiki sembrar {slug}")
    lineas.append(f"Siguiente: completar la configuración (hyt config {slug} …: pilares, reglas, personas), cargar "
                  "las fuentes del canal y lanzar «inventario» y «perfil-voz».")
    return "\n".join(lineas)


def estado(slug: str | None = None) -> str:
    slugs = [slug] if slug else C.listar()
    if not slugs:
        return "Aún no hay ningún canal dado de alta."
    lineas = [B.disco_linea()] if not slug else [x for x in [B.disco_linea([d for d in B.disco() if d["aviso"]])] if x]
    global_pausa = (B.home() / "pausa").exists()
    if global_pausa:
        lineas.append("⏸ Todo en pausa")
    for s in slugs:
        cfg = C.leer(s)
        lineas.append(f"📺 {C.resumen(cfg)}")
        abiertos = E.listar(s, abiertos=True)
        for e in abiertos:
            hechas = _etapas_hechas(s, e["id"])
            donde = E.situacion_texto(e)
            lineas.append(f"  • {e['nombre']} ({e['id']}): {e.get('estado')} · {hechas}/{len(e['etapas'])} etapas"
                          + (f" · {donde}" if donde else ""))
        for p in PU.puertas(("abierta", "decidida", "error")):
            if p["canal"] == s:
                lineas.append(f"  🚪 {p['titulo']} [{p['estado']}] ({p['id']})" + (f" — {p['error']}" if p.get("error") else ""))
        if not abiertos:
            lineas.append("  (nada en marcha)")
    return "\n".join(lineas)


def _etapas_hechas(slug: str, eid: str) -> int:
    enc = E.leer(slug, eid)
    hechas = set()
    try:
        for l in (C.carpeta(slug) / "etapas.jsonl").read_text().splitlines():
            r = json.loads(l)
            if r.get("encargo") == eid and r.get("resultado") == "done":
                hechas.add(r["etapa"])
            elif r.get("encargo") == eid:
                hechas.discard(r["etapa"])
    except OSError:
        pass
    return len([s for s in enc["etapas"] if s["id"] in hechas])


def reintentar(slug: str, eid: str, etapa: str) -> dict:
    """Vuelve a lanzar una etapa parada (y las siguientes). Una vez por etapa y encargo; después lo decide una persona."""
    d = E.carpeta(slug, eid)
    previos = 0
    try:
        for l in (d / ".estado" / "historial.jsonl").read_text().splitlines():
            r = json.loads(l)
            previos += r.get("accion") == "reintentar" and r.get("desde") == etapa
    except OSError:
        pass
    if previos:
        raise Rechazo(f"La etapa {etapa} ya se reintentó una vez: que lo decida una persona (o pide rehacer en la puerta)")
    enc = E.leer(slug, eid)
    if enc.get("estado") not in ("parado", "en-curso"):
        raise Rechazo(f"El encargo está «{enc.get('estado')}»: no hay nada que reintentar")
    enc = E.rehacer_desde(slug, eid, etapa, "", quien(), accion="reintentar", cuenta_ronda=False)
    return enc


def pausar(objetivo: str, si: bool) -> str:
    if objetivo == "todo":
        f = B.home() / "pausa"
        if si:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(B.ahora() + "\n")
        else:
            f.unlink(missing_ok=True)
        return "Todo en pausa" if si else "Todo reanudado"
    C.config(objetivo, "politicas.pausado", si, quien())
    return f"{objetivo}: {'en pausa' if si else 'reanudado'}"


def guardar_secreto(slug: str, clave: str) -> str:
    """Solo desde una terminal: el valor se pide sin eco y nunca se imprime."""
    import getpass
    import re
    C.leer(slug)
    if not sys.stdin.isatty():
        raise Rechazo("Las claves se guardan desde tu terminal (nunca por el chat ni por correo): "
                      "hyt secreto guardar <canal> <CLAVE>")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,60}", clave):
        raise Rechazo("El nombre de la clave va en mayúsculas, p. ej. CLAUDE_CODE_OAUTH_TOKEN")
    valor = getpass.getpass(f"Valor de {clave} (no se ve al escribir): ").strip()
    if not valor:
        raise Rechazo("Vacío: no se guarda nada")
    f = C.carpeta(slug) / "secretos.env"
    lineas = [l for l in (f.read_text().splitlines() if f.exists() else []) if not l.startswith(f"{clave}=")]
    f.write_text("\n".join(lineas + [f"{clave}={valor}"]) + "\n")
    os.chmod(f, 0o600)
    return f"🔑 {clave} guardada para {slug} (no se muestra)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt", description="Acciones de hermes-youtube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("canales")
    sub.add_parser("estado").add_argument("canal", nargs="?")
    x = sub.add_parser("encargos"); x.add_argument("canal"); x.add_argument("--todos", action="store_true")
    x = sub.add_parser("encargo"); x.add_argument("canal"); x.add_argument("id")
    sub.add_parser("puertas").add_argument("canal", nargs="?")
    sub.add_parser("puerta").add_argument("id")
    sub.add_parser("pipelines").add_argument("--canal")
    x = sub.add_parser("plan"); x.add_argument("pipeline"); x.add_argument("canal")
    x = sub.add_parser("lanzar"); x.add_argument("canal"); x.add_argument("pipeline")
    x.add_argument("--param", action="append", default=[]); x.add_argument("--brief", default="")
    x.add_argument("--excepcion", action="store_true")
    x = sub.add_parser("reintentar"); x.add_argument("canal"); x.add_argument("encargo"); x.add_argument("etapa")
    sub.add_parser("vueltas")
    x = sub.add_parser("leccion"); x.add_argument("canal"); x.add_argument("etapa"); x.add_argument("regla")
    x.add_argument("evidencia", nargs="+")
    sub.add_parser("lecciones").add_argument("--todas", action="store_true")
    x = sub.add_parser("alta"); x.add_argument("slug"); x.add_argument("nombre"); x.add_argument("presentador")
    x = sub.add_parser("config"); x.add_argument("canal"); x.add_argument("clave"); x.add_argument("valor")
    sub.add_parser("pausar").add_argument("objetivo")
    sub.add_parser("reanudar").add_argument("objetivo")
    x = sub.add_parser("modelos"); x.add_argument("args", nargs="*"); x.add_argument("--canal")
    x = sub.add_parser("secreto"); x.add_argument("accion", choices=("guardar",)); x.add_argument("canal"); x.add_argument("clave")
    x = sub.add_parser("wiki"); x.add_argument("accion", choices=("sembrar",)); x.add_argument("canal")
    x = sub.add_parser("fuentes"); x.add_argument("accion", choices=("cargar", "lista")); x.add_argument("canal")
    x.add_argument("origen", nargs="?", default=""); x.add_argument("--coleccion", default=""); x.add_argument("--tipo", default="directo")
    # «correo» (puertas por correo) se añadirá aquí en un paso posterior
    a = ap.parse_args(argv)
    try:
        if a.cmd == "canales":
            print("\n".join(C.resumen(C.leer(s)) for s in C.listar()) or "Aún no hay ningún canal dado de alta.")
        elif a.cmd == "estado":
            print(estado(a.canal))
        elif a.cmd == "encargos":
            for e in E.listar(a.canal, abiertos=not a.todos):
                print(f"{e['id']:44} {e.get('estado', ''):11} {e.get('nombre', '')} · {e.get('creado', '')[:10]}")
        elif a.cmd == "encargo":
            print(json.dumps(E.leer(a.canal, a.id), ensure_ascii=False, indent=2))
        elif a.cmd == "puertas":
            for p in PU.puertas(("abierta", "decidida", "error")):
                if not a.canal or p["canal"] == a.canal:
                    print(f"{p['id']}  {p['estado']:9} {p['titulo']}")
        elif a.cmd == "puerta":
            p = PU.leer(a.id)
            print(f"{p['titulo']}\n\n{p['texto']}".strip())
        elif a.cmd == "pipelines":
            for pid, p in PL.listar(a.canal).items():
                print(f"{pid:22} {p.get('nombre', '')}: {p.get('descripcion', '')}")
        elif a.cmd == "plan":
            r = PL.plan(a.pipeline, a.canal)
            mods = M.efectivos(a.canal)
            for s in r["etapas"]:
                ej = (C.leer(a.canal).get("ejecutores") or {}).get(s["id"]) or s.get("ejecutor", "hermes")
                quien_hace = "Claude Code" if ej == "claude" else s["perfil"]
                print(f"▶ {s.get('titulo') or s['id']} ({quien_hace}, {mods.get(s['id'], (M.LIGERO, ''))[0]})")
            for s in r["saltadas"]:
                print(f"· {s.get('titulo') or s['id']}: se salta, falta {', '.join(s['falta'])}")
            cadena = PL.puertas_de(r["pipeline"])
            for i, puerta in enumerate(cadena):
                final = PL.al_aprobar_de(r["pipeline"]) if i == len(cadena) - 1 else "nada"
                print(f"🚪 {puerta['tipo']}" + (f" ({puerta['papel']})" if puerta.get("papel") else "")
                      + (" · se salta si no hay datos pendientes" if puerta.get("si_vacio") else "")
                      + (f" → {final}" if final != "nada" else ""))
        elif a.cmd == "lanzar":
            params = dict(kv.split("=", 1) for kv in a.param if "=" in kv)
            if len(params) != len(a.param):
                raise Rechazo("Cada --param va como clave=valor")
            e = E.lanzar(a.canal, a.pipeline, params, a.brief, a.excepcion, quien())
            if e.get("duplicado"):
                print(f"⏭ {e['nombre']} ya está en marcha para {a.canal} ({e['id']}): no lanzo otro.")
                return 0
            print(f"🚀 {e['nombre']} en marcha para {a.canal} ({e['id']}): {len(e['etapas'])} etapas"
                  + (f"; se saltan {', '.join(s['id'] for s in e['saltadas'])}" if e["saltadas"] else ""))
        elif a.cmd == "reintentar":
            reintentar(a.canal, a.encargo, a.etapa)
            print(f"🔁 {a.etapa} vuelve a la cola ({a.encargo})")
        elif a.cmd == "vueltas":
            for slug, eid, desde in E.vueltas_pendientes():
                print(f"↩ {slug}/{eid}: vuelve a {desde} (la verificación pidió cambios)")
        elif a.cmd == "leccion":
            l = _cargar("hyt_lecciones").proponer(a.canal, a.etapa, a.regla, a.evidencia, quien())
            print(f"💡 Lección propuesta ({l['id']}): le llega a la persona para que la confirme.")
        elif a.cmd == "lecciones":
            for l in _cargar("hyt_lecciones").todas():
                if a.todas or l["estado"] in ("propuesta", "confirmada", "revisar"):
                    print(f"{l['id']}  {l['estado']:10} {l['etapa']:16} {l['regla']}")
        elif a.cmd == "alta":
            print(alta(a.slug, a.nombre, a.presentador))
        elif a.cmd == "config":
            print(C.resumen(C.config(a.canal, a.clave, a.valor, quien())))
        elif a.cmd in ("pausar", "reanudar"):
            print(pausar(a.objetivo, a.cmd == "pausar"))
        elif a.cmd == "modelos":
            x = a.args or ["ver"]
            if x[0] == "ver":
                nombres = dict(M.ETAPAS_MODELO)
                for e, (m, o) in M.efectivos(a.canal).items():
                    print(f"{nombres.get(e, e):32} {m:12} ({o})")
            elif x[0] == "perfil" and len(x) == 2:
                M.poner_perfil(x[1]); print(M.NOMBRE_PERFIL[x[1]])
            elif x[0] == "poner" and len(x) == 3:
                M.poner(x[1], x[2], a.canal, quien()); print("ok")
            else:
                raise Rechazo("uso: hyt modelos ver | perfil <p> | poner <etapa> <modelo|-> [--canal C]")
        elif a.cmd == "secreto":
            print(guardar_secreto(a.canal, a.clave))
        elif a.cmd == "fuentes":
            F = _cargar("hyt_fuentes")
            if a.accion == "cargar":
                r = F.cargar(a.canal, a.origen, a.coleccion, a.tipo, quien=quien())
                print(f"📚 {r['cargadas']} fuentes cargadas en «{a.coleccion}» ({r['palabras']} palabras)"
                      + (f" · ritmo medido: {r['ppm_medido']} palabras por minuto" if r["ppm_medido"] else ""))
                print("\n".join(f"⚠️ {x}" for x in r["avisos"]), end="\n" if r["avisos"] else "")
            else:
                return F.main(["lista", a.canal])
        elif a.cmd == "wiki":
            print("🧠 Memoria sembrada: " + ", ".join(_cargar("hyt_wiki").sembrar(a.canal)))
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
