"""Puertas de hermes-youtube: el núcleo común a todos los medios (Telegram, correo, panel y local) y el
notario. Copiado y adaptado de hermes-sdd (hsdd_nucleo.py, firmar.sh).

  «El ejecutor nunca firma; el notario nunca decide; el orquestador nunca interpreta.»

Vocabulario: aquí «canal» es SIEMPRE el canal de YouTube (su nombre corto); por dónde llega la decisión de una persona
(telegram, local, dashboard, email) es el «medio». En aprobadores.json:
  {"ana": {"nombre": "Ana", "medios": {"telegram": "111", "local": "ana"}, "canales": ["*"]}}

Una puerta se abre al acabar la última etapa de una pipeline que la declara (o suelta, con su tipo y su texto).
Vive SOLO en HERMES_YT_HOME/puertas/<id>.json, fuera del alcance de las etapas. Un medio enseña la puerta y traduce
el gesto de una persona en decidir(); queda una ventana para deshacer; después el notario (firmar) comprueba quién
decidió y ejecuta lo aprobado: lanzar otra pipeline o un script del canal, rehacer desde una etapa con lo que se
pidió, o descartar el encargo.

Siempre decide una persona. Con un aviso grave de la revisión mecánica no se puede aprobar: solo rehacer o rechazar;
la salida de emergencia es «decidir-local --forzar <motivo>», que queda escrita.

Cadena de puertas: una pipeline puede declarar varias (`puertas`), cada una con el papel que la decide. Al acabar la
última etapa se abre la primera; aprobar una que no es la última abre la siguiente; aprobar la última ejecuta
`al_aprobar` y escribe la memoria. «Rehacer» en cualquiera rehace desde la etapa `rehacer` y, al acabar, la cadena
vuelve a empezar por la primera. «Rechazar» en cualquiera descarta el encargo.

Papeles: una puerta con `papel` solo la decide una persona que lo tenga en ese canal (canal.json → personas, con la
misma clave que en aprobadores.json). Quien administra (canales ["*"] y sin entrada en las personas del canal) puede
decidir cualquiera, pero SOLO por el medio local: es la salida de emergencia.

Puerta de datos: cada dato de datos.json se verifica uno a uno (verificar_dato: verificado, corregido o eliminado) y
no se aprueba mientras quede alguno pendiente. Si al aprobar hay datos corregidos o eliminados, se ajusta el guion
(sin contar ronda) y la cadena vuelve a la primera puerta.

CLI:
  hyt_puertas.py listar [--todas]
  hyt_puertas.py ver <puerta>
  hyt_puertas.py abrir <canal> <encargo>
  hyt_puertas.py decidir-local <puerta> <verbo> [texto] [--forzar MOTIVO]   (medio local: decide y firma al momento)
  hyt_puertas.py dato-local <puerta> <dato> verificado|corregido|eliminado [valor]   (medio local: un dato de la puerta de datos)
  hyt_puertas.py deshacer <puerta> <persona>
  hyt_puertas.py firmar <puerta>  ·  vencidas               (lo hace el gateway al acabar la ventana)
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import re
import secrets
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
Rechazo = B.Rechazo

APRUEBA = ("acepto", "algunas")   # los verbos que ejecutan lo aprobado (con un aviso grave, bloqueados)
DESHACER_DEFECTO_S = 180
EMOJI = {"alta": "🧭", "elegir-temas": "💡", "elegir-titulo": "🏷", "revision": "📝", "datos": "🔎",
         "revision-final": "🎬", "voz": "🎙", "decision": "📊", "elegir-version": "⚖️"}
_APROBAR = {"verbo": "acepto", "etiqueta": "✅ Aprobar"}
_REHACER = {"verbo": "cambios", "etiqueta": "✏️ Rehacer", "texto": True}
_RECHAZAR = {"verbo": "rechazo", "etiqueta": "🗑 Rechazar", "texto": True}
_REVISAR = [_APROBAR, _REHACER, _RECHAZAR]
# «algunas»: la persona elige entre lo propuesto y lo escribe (qué temas, qué pareja de título y miniatura)
_ELEGIR = [{"verbo": "algunas", "etiqueta": "✅ Elegir", "texto": True},
           {"verbo": "cambios", "etiqueta": "🔁 Otra propuesta"},
           {"verbo": "rechazo", "etiqueta": "🗑 Ninguno", "texto": True}]
OPCIONES = {
    "alta": [_APROBAR, _RECHAZAR],
    "elegir-temas": _ELEGIR,
    "elegir-titulo": _ELEGIR,
    "revision": _REVISAR,
    "revision-final": _REVISAR,
    "voz": _REVISAR,
    "datos": [{"verbo": "acepto", "etiqueta": "✅ Datos verificados"}, _RECHAZAR],
    "decision": _REVISAR,
    # dos versiones del mismo guion (gemelos): la persona elige cuál sigue; la otra se archiva
    "elegir-version": [{"verbo": "algunas", "etiqueta": "✅ Elegir versión", "texto": True, "valores": ["A", "B"]},
                       {"verbo": "rechazo", "etiqueta": "🗑 Ninguna", "texto": True}],
}
LETRAS = "ABCDEFGH"


ESTADOS_DATO = ("verificado", "corregido", "eliminado")


def _datos_f(puerta: dict) -> Path | None:
    if puerta.get("tipo") != "datos" or not puerta.get("encargo"):
        return None
    return E.carpeta(puerta["canal"], puerta["encargo"]) / "datos.json"


def datos_de(puerta: dict) -> list:
    """Los datos que se verifican en una puerta de datos (datos.json del encargo): [{id, dato, estado, valor…}]."""
    f = _datos_f(puerta)
    datos = (B.leer(f, {}) or {}).get("datos") if f else None
    return [x for x in datos if isinstance(x, dict)] if isinstance(datos, list) else []


def datos_pendientes(puerta: dict) -> int:
    return sum(1 for x in datos_de(puerta) if x.get("estado", "pendiente") == "pendiente")


def graves(puerta: dict) -> int:
    """Avisos graves: los de la revisión mecánica (hyt_revision) guardados en la puerta y, en una puerta de datos, que
    aún quede algún dato por verificar (se recalcula cada vez)."""
    try:
        n = int((puerta.get("revision") or {}).get("graves") or 0)
    except (TypeError, ValueError):
        n = 0
    return n + (1 if datos_pendientes(puerta) else 0)


def opciones_vigentes(puerta: dict) -> list:
    """Las opciones que se ofrecen: sin la de aprobar si hay un aviso grave."""
    ops = puerta.get("opciones") or []
    return [o for o in ops if o.get("verbo") not in APRUEBA] if graves(puerta) else ops


# ── utilidades ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _dir() -> Path:
    return B.home() / "puertas"


def indice(gid: str) -> Path:
    if not re.fullmatch(r"g[0-9a-f]{8,40}", gid or ""):
        raise Rechazo("id de puerta no válido")
    return _dir() / f"{gid}.json"


def leer(gid: str) -> dict:
    p = B.leer(indice(gid))
    if not p:
        raise Rechazo("No conozco esta puerta")
    return p


def puertas(estados=("abierta", "decidida")) -> list:
    d = _dir()
    out = [B.leer(f) for f in sorted(d.glob("g*.json"))] if d.is_dir() else []
    return [p for p in out if p and p.get("estado") in estados]


def _segundos(clave: str, defecto: int) -> int:
    if os.environ.get("HERMES_YT_DESHACER_S"):
        return int(os.environ["HERMES_YT_DESHACER_S"])
    try:
        v = int((B.leer(B.home() / "yt.json", {}) or {}).get(clave) or defecto)
    except (TypeError, ValueError):
        v = defecto
    return min(max(v, 0), 86400)


def deshacer_s() -> int:
    return _segundos("deshacer_s", DESHACER_DEFECTO_S)


def _personas_canal(slug: str) -> dict:
    try:
        return C.leer(slug).get("personas") or {}
    except Rechazo:
        return {}


def persona_de(medio: str, ident, slug: str = "") -> tuple:
    """Persona cuya identidad en `medio` es `ident` → (clave, datos) o (None, None). Sale de aprobadores.json; por el
    medio `email`, además, de las personas del canal (canal.json → personas) cuyo correo es `ident`: su clave en
    `personas` es su identidad aunque no esté en aprobadores.json. Con `slug` se mira ese canal; sin él, todos."""
    if not str(ident):
        return None, None
    for clave, p in (B.leer(B.home() / "aprobadores.json", {}) or {}).items():
        if str((p.get("medios") or {}).get(medio, "")) == str(ident):
            return clave, p
    if medio == "email":
        for s in ([slug] if slug else C.listar()):
            for clave, p in _personas_canal(s).items():
                if isinstance(p, dict) and str(p.get("correo") or "").strip().lower() == str(ident).strip().lower():
                    return clave, p
    return None, None


def puede_decidir(persona: str, slug: str, papel: str = "", medio: str = "") -> bool:
    """¿Puede `persona` decidir en este canal una puerta que pide `papel`, por este `medio`? Sin papel basta con estar
    autorizada en el canal. Con papel, tiene que tenerlo en canal.json → personas; quien administra (canales ["*"] y
    sin entrada en las personas del canal) puede, pero solo por el medio local.

    Por `email` decide la persona del canal que tiene correo y el papel de la puerta (sin papel, el de marketing),
    esté o no en aprobadores.json."""
    en_canal = _personas_canal(slug).get(persona)
    roles = (en_canal or {}).get("roles") or [] if isinstance(en_canal, dict) else []
    if medio == "email" and isinstance(en_canal, dict) and en_canal.get("correo"):
        return (papel or "marketing") in roles
    p = (B.leer(B.home() / "aprobadores.json", {}) or {}).get(persona) or {}
    canales = p.get("canales", ["*"])
    if not p or not ("*" in canales or slug in canales):
        return False
    if not papel:
        return True
    if en_canal is not None:
        return papel in roles
    return "*" in canales and medio == "local"


def _autoriza(puerta: dict, persona: str, medio: str, ident) -> None:
    """Rechazo si `persona` (con esa identidad en ese medio) no puede decidir esta puerta."""
    slug, papel = puerta["canal"], puerta.get("papel", "")
    if not persona or persona_de(medio, ident, slug)[0] != persona:
        raise Rechazo("No estás autorizado para decidir esta puerta")
    if not puede_decidir(persona, slug, papel, medio):
        conocida = puede_decidir(persona, slug, "", medio) or persona in _personas_canal(slug)
        raise Rechazo(_no_autorizado(papel if conocida else ""))


def _no_autorizado(papel: str) -> str:
    return (f"Esta puerta la decide quien tiene el papel «{papel}» en el canal" if papel
            else "No estás autorizado para decidir esta puerta")


# ── abrir ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _resumen_de(d: Path, nombre: str, maximo: int = 1800) -> str:
    f = d / nombre
    if not f.exists():
        return ""
    t = f.read_text(errors="replace").strip()
    if f.suffix == ".json":
        try:
            t = json.dumps(json.loads(t), ensure_ascii=False, indent=1)
        except ValueError:
            pass
    return t if len(t) <= maximo else t[:maximo].rsplit("\n", 1)[0] + "\n…"


def _revision(slug: str, eid: str | None, tipo: str) -> dict:
    """Revisión mecánica (hyt_revision.py, sin IA). Si falla, sin avisos: nunca impide abrir la puerta."""
    try:
        return _cargar("hyt_revision").revisar(slug, eid, tipo)
    except Exception:
        return {"avisos": [], "graves": 0}


def abrir(slug: str, eid: str | None = None, tipo: str | None = None, titulo: str = "", texto: str = "",
          al_aprobar: str = "nada", tras: str = "") -> dict:
    """Abre la puerta de un encargo (la que le toca de su cadena: `puerta_indice`) o una suelta (tipo + título +
    texto). `tras`: la puerta que se acaba de aprobar y da paso a esta (aún consta como pendiente)."""
    cfg = C.leer(slug)
    enc, declarada, cadena, pos = None, {}, [], 0
    if eid:
        enc = E.leer(slug, eid)
        p = PL.cargar(enc["pipeline"], slug)
        cadena = PL.puertas_de(enc)
        if not cadena:
            raise Rechazo(f"La pipeline {enc['pipeline']} no tiene puerta")
        pos = min(max(int(enc.get("puerta_indice") or 0), 0), len(cadena) - 1)
        declarada = cadena[pos]
        tipo = declarada.get("tipo")
        if any(x.get("encargo") == eid and x["id"] != tras for x in puertas()):
            raise Rechazo(f"El encargo {eid} ya tiene una puerta pendiente")
        d = E.carpeta(slug, eid)
        salidas = [s.get("salida") for s in p["etapas"] if s["id"] in [x["id"] for x in enc["etapas"]] and s.get("salida")]
        principal = salidas[-1] if salidas else ""
        resumen = _resumen_de(d, principal)
        detalles = [f"{k}: {v}" for k, v in (enc.get("params") or {}).items()]
        if len(cadena) > 1 or enc.get("rondas"):
            detalles.insert(0, " · ".join(([f"Puerta {pos + 1} de {len(cadena)}"] if len(cadena) > 1 else [])
                                          + ([f"ronda {enc['rondas']} de {E.rondas_max(slug)}"] if enc.get("rondas") else [])))
        titulo = titulo or f"{EMOJI.get(tipo, '🚪')} {p['nombre']} · {cfg['nombre']}"
        texto = texto or ("\n".join(detalles) + ("\n\n" if detalles else "") + resumen +
                          f"\n\n📁 {d}" + (f"\n📄 {', '.join(s for s in salidas if (d / s).exists())}" if salidas else ""))
    if tipo not in OPCIONES:
        raise Rechazo(f"Tipo de puerta desconocido: {tipo}")
    rev = _revision(slug, eid, tipo)
    if rev.get("avisos"):
        lineas = [f"{'⛔' if a.get('grave') else '⚠️'} {a['texto']}" for a in rev["avisos"]]
        texto = f"🧭 Revisión: {len(rev['avisos'])} aviso(s)\n" + "\n".join(lineas) + "\n\n" + texto
    gid = f"g{int(time.time()):x}{secrets.token_hex(3)}"
    puerta = {"id": gid, "tipo": tipo, "canal": slug, "encargo": eid, "pipeline": enc and enc["pipeline"],
              "titulo": titulo, "texto": texto, "opciones": OPCIONES[tipo],
              "papel": declarada.get("papel", ""),   # quién decide; vacío = cualquiera autorizado en el canal
              "indice": pos, "total": len(cadena) or 1, "ronda": int((enc or {}).get("rondas") or 0),
              "al_aprobar": PL.al_aprobar_de(enc) if enc else al_aprobar,
              "rehacer": (PL.rehacer_de(enc) or enc["etapas"][-1]["id"]) if enc else None,
              "revision": rev, "creada": B.ahora(), "estado": "abierta"}
    with B.cerrojo("puertas"):
        B.escribir(indice(gid), puerta)
    if enc:
        enc["puerta_id"] = gid
        enc["puerta_indice"] = pos
        enc["estado"] = "en-puerta"
        E.guardar(slug, enc)
    return puerta


def _se_salta(slug: str, eid: str, declarada: dict) -> bool:
    """`si_vacio: saltar` en una puerta de datos: no hay datos.json o no queda ningún dato pendiente."""
    if declarada.get("si_vacio") != "saltar" or declarada.get("tipo") != "datos":
        return False
    return datos_pendientes({"tipo": "datos", "canal": slug, "encargo": eid}) == 0


def abrir_siguiente(slug: str, eid: str, desde: int = 0, tras: str = "") -> dict | None:
    """Abre la primera puerta de la cadena del encargo a partir de `desde` que no se salte. None si no queda ninguna
    (la cadena ha terminado)."""
    enc = E.leer(slug, eid)
    cadena = PL.puertas_de(enc)
    for i in range(max(desde, 0), len(cadena)):
        if _se_salta(slug, eid, cadena[i]):
            continue
        enc["puerta_indice"] = i
        E.guardar(slug, enc)
        return abrir(slug, eid, tras=tras)
    return None


# ── decidir y deshacer ─────────────────────────────────────────────────────────────────────────────────────────────
def _registrar(puerta: dict, verbo: str, texto: str, actor: dict, prueba: dict, ventana_s: int) -> dict:
    puerta.update(estado="decidida", firmar_en=time.time() + ventana_s,
                  decision={"verbo": verbo, "texto": texto, "actor": actor, "prueba": prueba, "at": B.ahora()})
    B.escribir(indice(puerta["id"]), puerta)
    return puerta


def decidir(gid: str, verbo: str, texto: str, persona: str, medio: str, ident, prueba: dict | None = None) -> dict:
    """Registra la decisión de `persona` (identificada por el medio) y abre la ventana para deshacer. Con un aviso
    grave de la revisión no se aprueba (salvo `forzar`, solo desde el medio local, con su motivo por escrito)."""
    forzar = (prueba or {}).get("forzado", "")
    with B.cerrojo("puertas"):
        puerta = leer(gid)
        if puerta.get("estado") != "abierta":
            raise Rechazo("Esta puerta ya está resuelta")
        _autoriza(puerta, persona, medio, ident)
        opcion = next((o for o in puerta["opciones"] if o["verbo"] == verbo), None)
        if not opcion:
            raise Rechazo("Opción no válida")
        if verbo in APRUEBA and datos_pendientes(puerta):   # esto no se fuerza: los datos se verifican uno a uno
            raise Rechazo(f"Quedan {datos_pendientes(puerta)} dato(s) por verificar: verifícalos antes de aprobar")
        if verbo in APRUEBA and graves(puerta) and not (forzar and medio == "local"):
            raise Rechazo("Tiene un aviso grave de la revisión (🧭 ⛔): solo se puede rehacer o rechazar")
        texto = (texto or "").strip()
        if verbo in APRUEBA and str(puerta.get("al_aprobar") or "").startswith("temas:") and puerta.get("encargo"):
            _temas_elegidos(puerta["canal"], puerta["encargo"], texto)   # rechaza aquí lo que no se puede cumplir
        if verbo in APRUEBA and puerta.get("tipo") == "elegir-version":
            _version_elegida(puerta, texto)   # una letra que no existe se corrige en el acto
        if opcion.get("texto") and not texto:
            raise Rechazo(f"«{opcion['etiqueta']}» necesita un texto: " +
                          ("lo que eliges" if verbo == "algunas" else "el motivo o lo que hay que cambiar"))
        ventana = _segundos("deshacer_email_s", 1800) if medio == "email" else deshacer_s()   # el correo se lee más tarde
        return _registrar(puerta, verbo, texto, {"persona": persona, "medio": medio, "id": str(ident)},
                          prueba or {}, ventana)


def verificar_dato(gid: str, dato_id, estado: str, valor: str, persona: str, medio: str, ident) -> dict:
    """Una persona con el papel de la puerta de datos deja un dato como verificado, corregido (con su `valor` bueno) o
    eliminado. Actualiza datos.json del encargo y lo anota en puertas.jsonl (evento «dato»). Devuelve el dato."""
    with B.cerrojo("puertas"):
        puerta = leer(gid)
        if puerta.get("tipo") != "datos" or not puerta.get("encargo"):
            raise Rechazo("Esta puerta no es de verificación de datos")
        if puerta.get("estado") != "abierta":
            raise Rechazo("Esta puerta ya está resuelta")
        _autoriza(puerta, persona, medio, ident)
        if estado not in ESTADOS_DATO:
            raise Rechazo(f"Un dato queda como: {', '.join(ESTADOS_DATO)}")
        valor = (valor or "").strip()
        if estado == "corregido" and not valor:
            raise Rechazo("Para corregir un dato hace falta el valor correcto")
        f = _datos_f(puerta)
        contenido = B.leer(f, {}) or {}
        dato = next((x for x in contenido.get("datos") or [] if isinstance(x, dict) and str(x.get("id")) == str(dato_id)), None)
        if not dato:
            raise Rechazo(f"No conozco el dato {dato_id} de este encargo")
        dato.update(estado=estado, valor=valor if estado == "corregido" else "", verificado_por=persona, verificado_en=B.ahora())
        B.escribir(f, contenido)
        B.anotar(C.carpeta(puerta["canal"]) / "puertas.jsonl", {
            "ts": B.ahora(), "evento": "dato", "puerta": gid, "tipo": "datos", "encargo": puerta["encargo"],
            "dato": dato.get("id"), "estado": estado, "valor": dato["valor"], "persona": persona, "medio": medio})
        return dato


def deshacer(gid: str, persona: str) -> dict:
    """Quien decidió; solo antes de la firma."""
    with B.cerrojo("puertas"):
        puerta = leer(gid)
        dec = puerta.get("decision") or {}
        if puerta.get("estado") != "decidida" or not persona or (dec.get("actor") or {}).get("persona") != persona:
            raise Rechazo("Ya no se puede deshacer")
        puerta["estado"] = "abierta"
        puerta.pop("decision", None)
        puerta.pop("firmar_en", None)
        B.escribir(indice(gid), puerta)
        return puerta


def marcar(gid: str, **campos) -> dict:
    """Campos de presentación de un medio (mensaje de Telegram…)."""
    with B.cerrojo("puertas"):
        puerta = leer(gid)
        for k, v in campos.items():
            if k in ("estado", "decision", "firmar_en", "opciones", "canal", "encargo", "revision", "papel", "al_aprobar",
                     "indice", "total", "rehacer"):
                raise Rechazo(f"«{k}» no lo marca un medio")
            if v is None:
                puerta.pop(k, None)
            else:
                puerta[k] = v
        B.escribir(indice(gid), puerta)
        return puerta


# ── notario ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _valida_actor(puerta: dict) -> str:
    """Comprueba de nuevo quién decidió. Devuelve el texto de firma («Ana (telegram)»)."""
    dec = puerta.get("decision") or {}
    actor = dec.get("actor") or {}
    clave, datos = persona_de(actor.get("medio", ""), actor.get("id", ""), puerta["canal"])
    if not clave or clave != actor.get("persona") \
            or not puede_decidir(clave, puerta["canal"], puerta.get("papel", ""), actor.get("medio", "")):
        raise Rechazo("Quien decidió no está autorizado en ese canal o por ese medio")
    return f"{(datos or {}).get('nombre') or clave} ({actor.get('medio')})"


def _datos_por_ajustar(puerta: dict, enc: dict) -> list:
    """Datos que una persona corrigió o eliminó y que aún no se han llevado al guion (claves id:estado:valor)."""
    hechos = set(enc.get("datos_ajustados") or [])
    claves = [f"{x.get('id')}:{x.get('estado')}:{x.get('valor', '')}" for x in datos_de(puerta)
              if x.get("estado") in ("corregido", "eliminado")]
    return [c for c in claves if c not in hechos]


def _aprobar(puerta: dict, firma: str, texto: str) -> str:
    """Aprobar (o elegir): ajusta el guion si se corrigieron datos, pasa a la puerta siguiente de la cadena o, si era
    la última, escribe la memoria, ejecuta `al_aprobar` y cierra el encargo."""
    slug, eid = puerta["canal"], puerta.get("encargo")
    if not eid:   # una puerta suelta: no hay cadena ni encargo que cerrar
        accion = puerta.get("al_aprobar") or "nada"
        return _script(slug, None, accion[len("script:"):], firma) if accion.startswith("script:") else "aprobado"
    if puerta.get("tipo") == "elegir-version":
        return _elegir_version(puerta, firma, texto)
    enc = E.leer(slug, eid)
    if puerta["decision"]["verbo"] == "algunas":   # la elección viaja con el encargo: la pipeline siguiente la hereda
        (E.carpeta(slug, eid) / "eleccion.md").write_text(f"# Elección de {firma}\n\n{texto}\n")
        enc["eleccion"] = texto
        E.guardar(slug, enc)
    if puerta["tipo"] == "datos":
        por_ajustar = _datos_por_ajustar(puerta, enc)
        if por_ajustar:   # no es una ronda: la persona no pidió rehacer, corrigió datos
            desde = puerta.get("rehacer") or enc["etapas"][-1]["id"]
            enc["datos_ajustados"] = sorted(set(enc.get("datos_ajustados") or []) | set(por_ajustar))
            E.guardar(slug, enc)
            E.rehacer_desde(slug, eid, desde, "datos corregidos por una persona", firma, accion="ajuste-datos",
                            cuenta_ronda=False)
            return f"datos corregidos ({len(por_ajustar)}): se ajusta desde {desde} y vuelve a la primera puerta"
    siguiente = abrir_siguiente(slug, eid, int(puerta.get("indice") or 0) + 1, tras=puerta["id"])
    if siguiente:
        return (f"aprobado: pasa a la puerta {siguiente['tipo']}"
                + (f" ({siguiente['papel']})" if siguiente.get("papel") else "") + f" [{siguiente['id']}]")
    enc = E.leer(slug, eid)
    mem = PL.cargar(enc["pipeline"], slug).get("memoria")
    if isinstance(mem, dict):   # su página de la wiki se escribe ahora, ya aprobada por una persona
        _cargar("hyt_wiki").de_salida(slug, eid, mem)
    accion = puerta.get("al_aprobar") or "nada"
    if accion.startswith("pipeline:"):
        resultado = lanzar_gemelos(slug, eid, accion.split(":", 1)[1], f"notario: puerta {puerta['id']} ({firma})")
    elif accion.startswith("temas:"):
        resultado = _lanzar_temas(slug, eid, accion.split(":", 1)[1], texto, puerta, firma)
    elif accion.startswith("script:"):
        resultado = _script(slug, eid, accion[len("script:"):], firma)
    else:
        resultado = "aprobado"
    enc = E.leer(slug, eid)
    enc["estado"] = "cerrado"
    enc.pop("puerta_id", None)
    E.guardar(slug, enc)
    try:   # un guion aprobado del todo: el canal aprende de él (ejemplo de voz, apertura usada, piezas gastadas)
        _cargar("hyt_videos").al_aprobar(slug, eid)
    except Exception:   # noqa: BLE001 — aprender es un extra: no puede tumbar una aprobación ya firmada
        pass
    return resultado


def lanzar_gemelos(slug: str, eid: str, pids: str, quien: str) -> str:
    """«a» lanza una pipeline; «a+b» lanza las dos como gemelos: dos versiones del mismo trabajo, con la misma elección,
    que acaban en una sola puerta para elegir una (versión A, B…, en el orden escrito)."""
    lista = [x.strip() for x in pids.split("+") if x.strip()]
    nuevos = []
    for pid in lista:
        nuevos.append(E.lanzar(slug, pid, {}, quien=quien, origen=eid))
    if len(nuevos) > 1:
        ids = [n["id"] for n in nuevos]
        for i, n in enumerate(nuevos):
            e = E.leer(slug, n["id"])
            e["gemelos"] = ids
            e["version_letra"] = LETRAS[i]
            e["version"] = PL.cargar(e["pipeline"], slug).get("version") or e["pipeline"]
            E.guardar(slug, e)
        return f"lanzadas {len(ids)} versiones: " + ", ".join(f"{LETRAS[i]} {x}" for i, x in enumerate(ids))
    return f"lanzado {nuevos[0]['id']}"


def _temas_elegidos(slug: str, eid: str, texto: str) -> list:
    """Los temas que la persona eligió de una propuesta, por su número («1, 4, 7» o «todos»). Los suplentes siguen la
    numeración de los propuestos. Se comprueba al decidir, no al firmar: un número que no existe se corrige en el acto."""
    datos = _cargar("hyt_pasos")._json(E.carpeta(slug, eid) / "temas.json", None) or {}
    temas = {int(t["n"]): t for t in datos.get("temas") or [] if str(t.get("n", "")).isdigit()}
    todos = {**temas, **{len(temas) + i: t for i, t in enumerate(datos.get("suplentes") or [], 1)}}
    if not todos:
        raise Rechazo("Esta propuesta no tiene temas entre los que elegir")
    elegidos = sorted(temas) if re.search(r"\btod[oa]s\b", texto or "", re.I) else \
        sorted({int(n) for n in re.findall(r"\d+", texto or "")})
    malos = [n for n in elegidos if n not in todos]
    if not elegidos or malos:
        raise Rechazo("Di qué temas eliges por su número (por ejemplo «1, 4, 7») o «todos»"
                      + (f"; no existen: {', '.join(map(str, malos))}" if malos else ""))
    return [todos[n] for n in elegidos]


def _lanzar_temas(slug: str, eid: str, pid: str, texto: str, puerta: dict, firma: str) -> str:
    """al_aprobar «temas:<pipeline>»: cada tema elegido arranca su propio encargo, con su resumen y sus piezas."""
    lanzados = []
    for t in _temas_elegidos(slug, eid, texto):
        brief = (f"{t.get('resumen', '')}\n\nPiezas del inventario que lo sostienen: {', '.join(t.get('piezas') or [])}\n"
                 f"Origen: {', '.join(t.get('origen') or [])}\n"
                 + (f"Formato: {t['formato']}\n" if t.get("formato") else "") + (f"Serie: {t['serie']}\n" if t.get("serie") else ""))
        nuevo = E.lanzar(slug, pid, {"tema": t["titulo"], "pilar": t.get("pilar", "")}, brief=brief,
                         quien=f"notario: puerta {puerta['id']} ({firma})")
        lanzados.append(nuevo["id"])
        B.anotar(C.carpeta(slug) / "temas.jsonl", {"ts": B.ahora(), "encargo": eid, "titulo": t["titulo"],
                                                   "pilar": t.get("pilar", ""), "estado": "elegida", "sigue_en": nuevo["id"]})
    return f"{len(lanzados)} tema(s) en marcha: " + ", ".join(lanzados)


# ── gemelos: dos versiones del mismo guion ─────────────────────────────────────────────────────────────────────────
def _descartar(slug: str, eid: str, motivo: str) -> None:
    enc = E.leer(slug, eid)
    enc["estado"] = "descartado"
    enc["descartado_motivo"] = motivo
    enc.pop("puerta_id", None)
    E.guardar(slug, enc)


def _version_elegida(puerta: dict, texto: str) -> dict:
    """El gemelo que eligió la persona: por su letra («A», «la B», «versión b») o por su versión («investigada»)."""
    gem = puerta.get("gemelos") or []
    t = (texto or "").strip().lower()
    for g in gem:
        if re.search(rf"(^|[^a-z]){g['letra'].lower()}([^a-z]|$)", t) or g.get("version", "@") in t:
            return g
    raise Rechazo("Di qué versión eliges: " + " o ".join(f"«{g['letra']}» ({g.get('version', '')})" for g in gem))


def _elegir_version(puerta: dict, firma: str, texto: str) -> str:
    slug = puerta["canal"]
    elegido = _version_elegida(puerta, texto)
    for g in puerta.get("gemelos") or []:
        if g["encargo"] != elegido["encargo"]:
            _descartar(slug, g["encargo"], f"se eligió la versión {elegido['letra']} ({elegido.get('version', '')})")
    enc = E.leer(slug, elegido["encargo"])
    enc["gemelos_resuelto"] = elegido["letra"]
    enc.pop("puerta_id", None)
    E.guardar(slug, enc)
    siguiente = abrir_siguiente(slug, elegido["encargo"], 0, tras=puerta["id"])
    return (f"elegida la versión {elegido['letra']} ({elegido.get('version', '')})"
            + (f": pasa a la puerta {siguiente['tipo']} [{siguiente['id']}]" if siguiente else ""))


def abrir_inicial(slug: str, eid: str) -> dict | None:
    """Al acabar un guion: su primera puerta. Si tiene gemelos y aún no se ha elegido, espera a que acaben todos y
    entonces abre UNA puerta «elegir-version» con todos; si un gemelo falló o se descartó, sigue solo; si llega
    cuando ya se siguió con otro, se archiva."""
    enc = E.leer(slug, eid)
    ids = enc.get("gemelos") or []
    if not ids or enc.get("gemelos_resuelto"):
        return abrir_siguiente(slug, eid, 0)
    otros = [E.leer(slug, x) for x in ids if x != eid]
    if any(o.get("gemelos_resuelto") for o in otros):
        _descartar(slug, eid, "acabó cuando ya se había seguido con la otra versión")
        return None
    vivos = [o for o in otros if o.get("estado") not in ("descartado", "parado")]
    if not vivos:   # el otro falló o se descartó: este sigue solo
        enc["gemelos_resuelto"] = enc.get("version_letra") or "solo"
        E.guardar(slug, enc)
        return abrir_siguiente(slug, eid, 0)
    enc["estado"] = "esperando-gemelo"
    E.guardar(slug, enc)
    if any(o.get("estado") != "esperando-gemelo" for o in vivos):
        return None   # el último en acabar abre la puerta
    return abrir_eleccion(slug, [E.leer(slug, x) for x in ids if E.leer(slug, x).get("estado") == "esperando-gemelo"])


def gemelo_fallo(slug: str, eid: str) -> dict | None:
    """Un gemelo se ha parado: si el otro ya acabó y lo esperaba, sigue solo."""
    enc = E.leer(slug, eid)
    for x in enc.get("gemelos") or []:
        if x != eid:
            o = E.leer(slug, x)
            if o.get("estado") == "esperando-gemelo" and not o.get("gemelos_resuelto"):
                o["gemelos_resuelto"] = o.get("version_letra") or "solo"
                E.guardar(slug, o)
                return abrir_siguiente(slug, x, 0)
    return None


def abrir_eleccion(slug: str, encs: list) -> dict:
    encs = sorted(encs, key=lambda e: e.get("version_letra") or "Z")
    a = encs[0]
    cfg = C.leer(slug)
    cadena = PL.puertas_de(a)
    papel = (cadena[0].get("papel") if cadena else "") or "marketing"
    gemelos = [{"letra": e.get("version_letra") or LETRAS[i], "version": e.get("version") or e["pipeline"],
                "encargo": e["id"], "pipeline": e["pipeline"]} for i, e in enumerate(encs)]
    lineas = []
    for g in gemelos:
        m = _cargar("hyt_pasos")._json(E.carpeta(slug, g["encargo"]) / "paquete.json", {}) or {}
        lineas.append(f"Versión {g['letra']} ({g['version']}): {m.get('palabras', '?')} palabras, "
                      f"{m.get('minutos', '?')} min, nota {m.get('nota', '?')}")
    gid = f"g{int(time.time()):x}{secrets.token_hex(3)}"
    puerta = {"id": gid, "tipo": "elegir-version", "canal": slug, "encargo": a["id"], "pipeline": a["pipeline"],
              "titulo": f"{EMOJI['elegir-version']} Elegir versión del guion · {cfg['nombre']}",
              "texto": "\n".join(lineas), "opciones": OPCIONES["elegir-version"], "papel": papel,
              "gemelos": gemelos, "indice": -1, "total": len(cadena) or 1, "ronda": 0, "al_aprobar": "nada",
              "rehacer": None, "revision": {}, "creada": B.ahora(), "estado": "abierta"}
    with B.cerrojo("puertas"):
        B.escribir(indice(gid), puerta)
    for e in encs:
        e = E.leer(slug, e["id"])
        e["puerta_id"] = gid
        e["estado"] = "en-puerta"
        E.guardar(slug, e)
    return puerta


def _aplicar(puerta: dict, firma: str) -> str:
    """Ejecuta lo decidido. Devuelve una línea con el resultado."""
    dec = puerta["decision"]
    verbo, texto = dec["verbo"], dec.get("texto", "")
    slug, eid = puerta["canal"], puerta.get("encargo")
    if verbo in APRUEBA:
        return _aprobar(puerta, firma, texto)
    if verbo == "cambios":
        if not eid:
            raise Rechazo("Esta puerta no tiene un encargo que rehacer")
        enc = E.leer(slug, eid)
        desde = puerta.get("rehacer") or enc["etapas"][-1]["id"]
        enc = E.rehacer_desde(slug, eid, desde, texto, firma)
        if enc.get("estado") == "descartado":
            return f"descartado: {enc.get('descartado_motivo')}"
        return f"se rehace desde {desde}" + (f" (ronda {enc['rondas']} de {E.rondas_max(slug)})" if len(PL.puertas_de(enc)) > 1 else "")
    if verbo == "rechazo" and puerta.get("tipo") == "elegir-version":
        for g in puerta.get("gemelos") or []:
            _descartar(slug, g["encargo"], f"ninguna versión elegida: {texto}")
        return "descartadas las dos versiones"
    if verbo == "rechazo":
        if eid:
            enc = E.leer(slug, eid)
            enc["estado"] = "descartado"
            enc["descartado_motivo"] = texto
            enc.pop("puerta_id", None)
            E.guardar(slug, enc)
        return "descartado"
    raise Rechazo(f"Verbo desconocido: {verbo}")


def _script(slug: str, eid: str | None, orden: str, firma: str) -> str:
    """al_aprobar «script:<fichero> [args]»: un script de extensiones/ del canal, desacoplado, con su log."""
    import subprocess
    partes = orden.replace("{encargo}", eid or "").replace("{carpeta}", str(E.carpeta(slug, eid)) if eid else "").split()
    ext = (C.carpeta(slug) / "extensiones").resolve()
    ruta = (ext / partes[0]).resolve()
    if not str(ruta).startswith(str(ext) + os.sep) or not ruta.is_file():
        raise Rechazo(f"No encuentro el script {partes[0]} en las extensiones del canal")
    log = C.carpeta(slug) / "logs" / f"script-{eid or 'puerta'}-{partes[0]}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HYT_FIRMA": firma, "HYT_ENCARGO": eid or "", "HERMES_YT_HOME": str(B.home())}
    subprocess.Popen(B.desacoplar(["bash", str(ruta), *partes[1:]]), start_new_session=True, cwd=str(C.carpeta(slug)), env=env,
                     stdout=open(log, "w"), stderr=subprocess.STDOUT)
    return f"lanzado {partes[0]} (registro en logs/{log.name})"


def firmar(gid: str, ahora: float | None = None) -> dict:
    """El notario: valida, ejecuta lo decidido y lo registra. Idempotente: una puerta firmada no se vuelve a firmar."""
    with B.cerrojo("notario"):
        puerta = leer(gid)
        if puerta.get("estado") == "firmada":
            return puerta
        if puerta.get("estado") != "decidida":
            raise Rechazo("Esta puerta no está decidida")
        if (ahora or time.time()) < float(puerta.get("firmar_en") or 0):
            raise Rechazo("Aún está abierta la ventana para deshacer")
        try:
            firma = _valida_actor(puerta)
            resultado = _aplicar(puerta, firma)
        except Rechazo as e:
            with B.cerrojo("puertas"):
                p = leer(gid)
                p.update(estado="error", error=str(e), error_at=B.ahora())
                B.escribir(indice(gid), p)
            raise
        with B.cerrojo("puertas"):
            p = leer(gid)
            p.update(estado="firmada", firmada=B.ahora(), firma=firma, resultado=resultado)
            B.escribir(indice(gid), p)
        dec = p["decision"]
        B.anotar(C.carpeta(p["canal"]) / "puertas.jsonl", {
            "ts": p["firmada"], "puerta": gid, "tipo": p["tipo"], "encargo": p.get("encargo"), "verbo": dec["verbo"],
            "texto": dec.get("texto", ""), "persona": dec["actor"].get("persona"), "medio": dec["actor"].get("medio"),
            "firma": firma, "resultado": resultado, "forzado": (dec.get("prueba") or {}).get("forzado", ""),
            "segundos_hasta_decidir": _segundos_entre(p.get("creada"), dec.get("at"))})
        try:   # la memoria del canal: decisiones y correcciones (sin modelo; nunca frena al notario)
            _cargar("hyt_wiki").regenerar_decisiones(p["canal"])
        except Exception:   # noqa: BLE001
            pass
        return p


def _segundos_entre(a, b) -> int:
    from datetime import datetime
    try:
        f = "%Y-%m-%dT%H:%M:%SZ"
        return int((datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds())
    except Exception:
        return 0


def vencidas() -> list:
    """Firma las puertas decididas cuya ventana para deshacer ya pasó. Devuelve [(id, ok, mensaje)]."""
    out = []
    for p in puertas(("decidida",)):
        if time.time() >= float(p.get("firmar_en") or 0):
            try:
                r = firmar(p["id"])
                out.append((p["id"], True, r.get("resultado", "")))
            except Rechazo as e:
                out.append((p["id"], False, str(e)))
    return out


def firmar_ya(gid: str) -> dict:
    """Firma una puerta recién decidida sin esperar a la ventana para deshacer (medio local; aprobar por correo)."""
    with B.cerrojo("puertas"):
        p = leer(gid)
        p["firmar_en"] = 0
        B.escribir(indice(gid), p)
    return firmar(gid)


def decidir_local(gid: str, verbo: str, texto: str = "", forzar: str = "") -> dict:
    """Medio local (plan B sin Telegram): la persona en esta máquina decide y se firma al momento. `forzar` (un motivo)
    permite aprobar una puerta con aviso grave; queda en puertas.jsonl."""
    usuario = getpass.getuser()
    clave, _ = persona_de("local", usuario)
    if not clave:
        raise Rechazo(f"El usuario {usuario} no está en aprobadores.json (medios.local)")
    if forzar and not forzar.strip():
        raise Rechazo("--forzar necesita un motivo")
    decidir(gid, verbo, texto, clave, "local", usuario, {"forzado": forzar.strip()} if forzar else None)
    return firmar_ya(gid)


def dato_local(gid: str, dato_id, estado: str, valor: str = "") -> dict:
    """Medio local: la persona en esta máquina verifica un dato de una puerta de datos."""
    usuario = getpass.getuser()
    clave, _ = persona_de("local", usuario)
    if not clave:
        raise Rechazo(f"El usuario {usuario} no está en aprobadores.json (medios.local)")
    return verificar_dato(gid, dato_id, estado, valor, clave, "local", usuario)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt_puertas.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("listar"); l.add_argument("--todas", action="store_true")
    sub.add_parser("ver").add_argument("puerta")
    a = sub.add_parser("abrir"); a.add_argument("canal"); a.add_argument("encargo")
    dl = sub.add_parser("decidir-local"); dl.add_argument("puerta"); dl.add_argument("verbo"); dl.add_argument("texto", nargs="?", default="")
    dl.add_argument("--forzar", default="")
    dt = sub.add_parser("dato-local"); dt.add_argument("puerta"); dt.add_argument("dato"); dt.add_argument("estado")
    dt.add_argument("valor", nargs="?", default="")
    dh = sub.add_parser("deshacer"); dh.add_argument("puerta"); dh.add_argument("persona")
    sub.add_parser("firmar").add_argument("puerta")
    sub.add_parser("vencidas")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "listar":
            for p in puertas(("abierta", "decidida", "error", "firmada") if x.todas else ("abierta", "decidida", "error")):
                print(f"{p['id']}  {p['estado']:9} {p['canal']:16} {p['titulo']}")
        elif x.cmd == "ver":
            print(json.dumps(leer(x.puerta), ensure_ascii=False, indent=2))
        elif x.cmd == "abrir":
            print(abrir(x.canal, x.encargo)["id"])
        elif x.cmd == "decidir-local":
            p = decidir_local(x.puerta, x.verbo, x.texto, x.forzar)
            print(f"Firmada por {p['firma']}: {p['resultado']}")
        elif x.cmd == "dato-local":
            d = dato_local(x.puerta, x.dato, x.estado, x.valor)
            p = leer(x.puerta)
            print(f"Dato {d.get('id')}: {d['estado']}" + (f" → {d['valor']}" if d.get("valor") else "")
                  + f" · quedan {datos_pendientes(p)} por verificar")
        elif x.cmd == "deshacer":
            deshacer(x.puerta, x.persona); print("deshecha")
        elif x.cmd == "firmar":
            p = firmar(x.puerta); print(f"Firmada por {p['firma']}: {p['resultado']}")
        elif x.cmd == "vencidas":
            for gid, ok, msg in vencidas():
                print(f"{gid} {'ok' if ok else 'ERROR'} {msg}")
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
