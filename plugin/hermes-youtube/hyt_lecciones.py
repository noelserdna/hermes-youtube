"""Lecciones entre canales (copiado y adaptado de hermes-sdd, hsdd_lecciones.py).

Cuando algo de un canal enseña una regla que habría evitado un fallo, la coordinadora (o una persona) la propone con
evidencia de ese canal. Llega a Telegram con ✅ Confirmar / 🗑 Descartar. Solo las confirmadas entran en el contexto de
las etapas de **otros** canales (como mucho 5) y en la wiki global; cada uso se anota. Tras usarse en 3 canales pasa a
«revisar» (♻️ Mantener / ⌛ Caducar): no hay forma honrada de medir sola si una lección cambió el resultado, así que lo
decide una persona.

  HERMES_YT_HOME/lecciones.json   [{id, regla, etapa, origen, evidencia, estado, propuesta, usos: [canal…]}]

CLI:
  hyt_lecciones.py proponer <canal> <etapa> "<regla>" <evidencia>…   (evidencia: id de encargo o de puerta g…)
  hyt_lecciones.py listar [--todas]
  hyt_lecciones.py decidir <id> confirmar|descartar|mantener|caducar <persona>
"""
from __future__ import annotations

import importlib.util
import json
import re
import secrets
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
Rechazo = B.Rechazo
MAX_POR_ETAPA = 5
USOS_PARA_REVISAR = 3


def _f() -> Path:
    return B.home() / "lecciones.json"


def todas() -> list:
    return B.leer(_f(), []) or []


def _guardar(ls: list) -> None:
    B.escribir(_f(), ls)


def _evidencia_valida(slug: str, ev: str) -> bool:
    d = C.carpeta(slug)
    if re.fullmatch(r"g[0-9a-f]{8,40}", ev):
        try:
            return any(json.loads(l).get("puerta") == ev for l in (d / "puertas.jsonl").read_text().splitlines())
        except OSError:
            return False
    return bool(re.fullmatch(r"[a-z0-9-]{3,80}", ev)) and (d / "encargos" / ev / "encargo.json").exists()


def proponer(slug: str, etapa: str, regla: str, evidencia: list, quien: str = "") -> dict:
    cfg = C.leer(slug)
    regla = " ".join(regla.split())
    if not 20 <= len(regla) <= 300:
        raise Rechazo("La regla va en una o dos frases (20-300 caracteres)")
    nombres = {s: C.leer(s) for s in C.listar()}
    for s, c in nombres.items():   # general: sin el nombre de ningún canal ni de quien lo presenta
        for marca in {s, c.get("nombre", ""), c.get("presentador", "")}:
            if marca and len(marca) > 2 and re.search(rf"\b{re.escape(marca.lower())}\b", regla.lower()):
                raise Rechazo(f"La regla tiene que ser general: quita «{marca}»")
    if re.search(r"\bg[0-9a-f]{8,}\b|\bt_[0-9a-f]+\b|https?://", regla):
        raise Rechazo("La regla no lleva ids ni enlaces: eso va en la evidencia")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", etapa):
        raise Rechazo("Etapa no válida")
    evidencia = [e for e in evidencia if e]
    if not evidencia or not all(_evidencia_valida(slug, e) for e in evidencia):
        raise Rechazo(f"La evidencia tiene que ser un encargo o una puerta de {cfg['nombre']} que exista")
    with B.cerrojo("lecciones"):
        ls = todas()
        if any(l["regla"].lower() == regla.lower() and l["estado"] in ("propuesta", "confirmada") for l in ls):
            raise Rechazo("Esa lección ya existe")
        l = {"id": f"l{secrets.token_hex(3)}", "regla": regla, "etapa": etapa, "origen": slug, "evidencia": evidencia,
             "estado": "propuesta", "propuesta": B.ahora(), "quien": quien, "usos": []}
        ls.append(l)
        _guardar(ls)
    return l


def decidir(lid: str, accion: str, persona: str) -> dict:
    estados = {"confirmar": ("propuesta", "confirmada"), "descartar": ("propuesta", "descartada"),
               "mantener": ("revisar", "confirmada"), "caducar": ("revisar", "caducada")}
    if accion not in estados:
        raise Rechazo(f"Acción no válida: {accion}")
    with B.cerrojo("lecciones"):
        ls = todas()
        l = next((x for x in ls if x["id"] == lid), None)
        if not l:
            raise Rechazo("No conozco esa lección")
        desde, hasta = estados[accion]
        if l["estado"] != desde:
            raise Rechazo(f"La lección está «{l['estado']}»")
        l.update(estado=hasta, decidida=B.ahora(), por=persona)
        if accion == "mantener":
            l["usos"], l["mantenida"] = [], B.ahora()
        _guardar(ls)
    if hasta == "confirmada":
        _a_la_wiki(l)
    return l


def _a_la_wiki(l: dict) -> None:
    """Las confirmadas quedan también en la wiki global (página de lecciones), sin datos del canal de origen."""
    w = B.home() / "wiki"   # la wiki global; si aún no existe, al menos la página
    p = w / "concepts" / "lecciones.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("---\ntitle: Lecciones entre canales\ntype: concept\ntags: [leccion]\nconfidence: medium\n---\n\n"
                     "# Lecciones entre canales\n\nConfirmadas por una persona. Ver [[index]].\n\n")
    texto = p.read_text()
    if l["regla"] not in texto:
        p.write_text(texto + f"- **{l['etapa']}** · {l['regla']} ({l['id']}, {l.get('decidida', '')[:10]})\n")


def para_canal(slug: str, etapa: str | None = None, anotar: bool = True) -> list:
    """Hasta 5 lecciones confirmadas de OTROS canales (de la etapa, si se da). Anota el uso; a los 3 canales → revisar."""
    with B.cerrojo("lecciones"):
        ls = todas()
        elegidas = [l for l in ls if l["estado"] == "confirmada" and l["origen"] != slug
                    and (etapa is None or l["etapa"] == etapa)][:MAX_POR_ETAPA]
        if anotar and elegidas:
            for l in elegidas:
                if slug not in l["usos"]:
                    l["usos"].append(slug)
                if len(l["usos"]) >= USOS_PARA_REVISAR:
                    l["estado"] = "revisar"
            _guardar(ls)
    return [l["regla"] for l in elegidas]


def pendientes() -> list:
    """Las que esperan a una persona (propuestas y para revisar) y aún no se han avisado."""
    return [l for l in todas() if l["estado"] in ("propuesta", "revisar")]


def main(argv=None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    try:
        if a[:1] == ["proponer"] and len(a) >= 5:
            l = proponer(a[1], a[2], a[3], a[4:])
            print(f"Lección propuesta ({l['id']}): llegará a Telegram para que una persona la confirme.")
        elif a[:1] == ["listar"]:
            for l in todas():
                if "--todas" in a or l["estado"] in ("propuesta", "confirmada", "revisar"):
                    print(f"{l['id']}  {l['estado']:10} {l['etapa']:16} {l['regla']}")
        elif a[:1] == ["decidir"] and len(a) == 4:
            print(decidir(a[1], a[2], a[3])["estado"])
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
