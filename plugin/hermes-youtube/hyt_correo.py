"""Correo de hermes-youtube: un solo buzón para todos los canales, y decisiones por CÓDIGO (nunca por un modelo).

Las personas de cada canal están en canal.json → personas ({clave: {nombre, correo, roles}}). El Worker de Cloudflare
(correo/) recibe en el buzón, comprueba que el correo es auténtico y no automático, y lo deja en una cola; el ciclo
(cada minuto, desde el bucle del plugin o con «hyt correo ciclo») lo recoge, envía lo pendiente y firma lo decidido.

  · Puertas: cada puerta abierta se envía a las personas del canal con su papel (sin papel, a las de marketing), con el
    contenido completo y botones mailto: que llevan un código de un solo uso por opción (APROBAR <código>, REHACER
    <código>: …, RECHAZAR <código>; ELEGIR, OTRA y NINGUNO en las de elegir). Decide el código: el remitente es una
    persona de ese canal con ese papel, el código es de una puerta abierta y el contenido no ha cambiado.
  · APROBAR se firma al momento. Lo demás deja una ventana para deshacer (DESHACER <código>).
  · Una respuesta sin código en el hilo de una revisión o de la voz, con una instrucción, vale como REHACER. Un «ok» o
    un «gracias» no deciden nada. En las puertas de datos y de elegir, un texto libre nunca decide.
  · Los datos no se verifican por correo: el correo los lista y manda al panel.
  · Peticiones (solo marketing): PROPUESTA, TEMA: <texto> (con PILAR: <id> opcional) y ESTADO. Sin modelo.
  · Quien no está en las personas de ningún canal recibe, una vez al día, un aviso de que su dirección no está
    autorizada; queda anotado para quien administra.

  hyt_correo.py ciclo      recoger, enviar puertas, firmar lo vencido, avisar de lo firmado y despachar
  hyt_correo.py resumen    un correo por persona con sus puertas abiertas, si alguna lleva más de 24 h
  hyt_correo.py prueba <canal>
"""
from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
TOPE_DIA = 20            # correos sin código (peticiones, ayudas) que se atienden por persona y día
RESUMEN_HORAS = 24       # el resumen diario solo sale si alguna puerta lleva más que esto esperando
PALABRAS = ("APROBAR", "REHACER", "RECHAZAR", "ELEGIR", "OTRA", "NINGUNO", "DESHACER")
# el código puede acabar en «-» o «_»: no vale \b (cortaría el código); se exige que no siga otro carácter de código
CODIGO = re.compile(r"\b(" + "|".join(PALABRAS) + r")\s+([A-Za-z0-9_-]{12,40})(?![A-Za-z0-9_-])\s*:?\s*(.*)", re.S)
ELEGIR = ("elegir-temas", "elegir-titulo")
REVISAR = ("revision", "revision-final", "voz")     # aquí una respuesta con una instrucción vale como «rehacer»
# textos de ayuda que van escritos en el correo que abre cada botón: si llegan tal cual, no son lo que dijo la persona
AYUDA_REHACER = "(escribe aquí qué cambiar; puedes señalar las frases por su número)"
AYUDA_TEMAS = "(escribe aquí los números, por ejemplo: 1, 4, 7)"
AYUDA_MOTIVO = "(si quieres, di por qué)"
AYUDA_TEMA = "(escribe aquí el tema)"
AYUDA_PILAR = "(opcional: el pilar)"
AYUDAS = (AYUDA_REHACER, AYUDA_TEMAS, AYUDA_MOTIVO, AYUDA_TEMA, AYUDA_PILAR)
# lo que no trae instrucción: cortesías y acuses de recibo (en plano, sin tildes)
CORTESIAS = set("""gracias muchas ok okay okey vale perfecto perfecta recibido recibida de acuerdo genial estupendo bien
muy si claro hecho entendido listo guay bueno buenas hola saludos un una el la lo por todo adios enterado enterada""".split())


# ── configuración y transporte ──────────────────────────────────────────────────────────────────────────────────────
def conf() -> dict:
    f = Path(os.environ.get("HYT_CORREO_CONF") or Path.home() / ".config" / "hermes-youtube" / "correo.env")
    d = {}
    if f.exists():
        for l in f.read_text().splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                d[k.strip()] = v.strip().strip('"')
    d.update({k: v for k, v in os.environ.items() if k.startswith("HYT_CORREO_")})
    return d


def activo() -> bool:
    c = conf()
    return bool(c.get("HYT_CORREO_URL") and c.get("HYT_CORREO_SECRETO") and c.get("HYT_CORREO_BUZON"))


def _http(metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    c = conf()
    url = c["HYT_CORREO_URL"].rstrip("/")
    if url.startswith("file://"):   # doble para las pruebas: una carpeta con pendientes.json y enviados.jsonl
        d = Path(url[7:])
        if ruta == "/pendientes":
            return {"correos": json.loads((d / "pendientes.json").read_text()) if (d / "pendientes.json").exists() else []}
        if ruta == "/hecho":
            ps = json.loads((d / "pendientes.json").read_text()) if (d / "pendientes.json").exists() else []
            (d / "pendientes.json").write_text(json.dumps([p for p in ps if p["id"] not in cuerpo["ids"]]))
            return {"ok": True}
        if ruta == "/enviar":
            with open(d / "enviados.jsonl", "a") as f:
                f.write(json.dumps(cuerpo, ensure_ascii=False) + "\n")
            return {"ok": True, "messageId": f"<{secrets.token_hex(4)}@falso>"}
    req = urllib.request.Request(url + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, method=metodo,
                                 headers={"Authorization": f"Bearer {c['HYT_CORREO_SECRETO']}", "Content-Type": "application/json",
                                          "User-Agent": "hermes-youtube/0.1"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:   # noqa: BLE001
            return {"ok": False, "error": f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "error": str(e)[:200]}


def _dir() -> Path:
    d = B.home() / "correo"
    (d / "salida").mkdir(parents=True, exist_ok=True)
    return d


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


def _epoch(ts: str) -> float:
    try:
        return time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except ValueError:
        return time.time()


# ── quién es quién ──────────────────────────────────────────────────────────────────────────────────────────────────
def personas(slug: str) -> dict:
    try:
        return {k: p for k, p in (C.leer(slug).get("personas") or {}).items() if isinstance(p, dict)}
    except Rechazo:
        return {}


def _correo(p: dict) -> str:
    return str(p.get("correo") or "").strip().lower()


def destinatarios(slug: str, papel: str = "") -> list:
    """[(clave, correo)] de las personas del canal con ese papel (sin papel, el de marketing) que tienen correo."""
    papel = papel or "marketing"
    return [(k, _correo(p)) for k, p in personas(slug).items() if _correo(p) and papel in (p.get("roles") or [])]


def de_quien(correo: str) -> list:
    """[(canal, clave, persona)] de todos los canales en los que esa dirección es de una persona."""
    correo = str(correo or "").strip().lower()
    return [(s, k, p) for s in C.listar() for k, p in personas(s).items() if correo and _correo(p) == correo]


def _puede(puerta: dict, clave: str) -> bool:
    return _cargar("hyt_puertas").puede_decidir(clave, puerta["canal"], puerta.get("papel", ""), "email")


# ── salida ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def encolar(slug: str, a: str, asunto: str, texto: str, html_: str = "", en_respuesta_a: str = "", tipo: str = "aviso",
            puerta: str = "") -> Path | None:
    """Deja un correo en la cola de salida. `puerta`: la puerta de la que habla (para reconocer las respuestas en su hilo)."""
    if not a:
        return None
    m = {"canal": slug, "tipo": tipo, "to": a, "subject": asunto[:300], "text": texto, "html": html_ or _html(asunto, texto),
         "in_reply_to": en_respuesta_a, "puerta": puerta, "creado": B.ahora()}
    f = _dir() / "salida" / f"{int(time.time() * 1000)}-{secrets.token_hex(3)}.json"
    B.escribir(f, m)
    return f


def despachar() -> int:
    n = 0
    for f in sorted((_dir() / "salida").glob("*.json")):
        m = B.leer(f) or {}
        r = _http("POST", "/enviar", {k: m.get(k) for k in ("to", "subject", "text", "html", "in_reply_to")})
        if r.get("ok"):
            B.anotar(_dir() / "enviados.jsonl", {"ts": B.ahora(), "canal": m.get("canal"), "tipo": m.get("tipo"), "to": m.get("to"),
                                                 "asunto": m.get("subject"), "puerta": m.get("puerta") or "",
                                                 "message_id": r.get("messageId")})
            f.unlink()
            n += 1
        else:
            m["intentos"] = int(m.get("intentos") or 0) + 1
            m["error"] = str(r.get("error"))[:200]
            B.escribir(f, m)
    return n


def _mailto(asunto: str, cuerpo: str) -> str:
    q = urllib.parse.urlencode({"subject": asunto, "body": cuerpo}, quote_via=urllib.parse.quote)
    return f"mailto:{conf().get('HYT_CORREO_BUZON', '')}?{q}"


def _boton(palabra: str, codigo: str, etiqueta: str, extra: str = "", color: str = "#126a8a") -> str:
    """Un botón que abre un correo ya escrito: «PALABRA código» en el asunto y en el cuerpo (con `extra` detrás)."""
    cabeza = f"{palabra} {codigo}".strip()
    return (f'<a href="{html.escape(_mailto(cabeza, cabeza + extra))}" style="display:inline-block;padding:12px 18px;margin:4px 6px 4px 0;'
            f'border-radius:8px;background:{color};color:#fff;text-decoration:none;font-weight:600;font-size:16px">'
            f'{html.escape(etiqueta)}</a>')


PIE = ("Cada botón abre un correo ya escrito: solo tienes que enviarlo. Un «sí» escrito a mano no decide nada. "
       "Te escribe hermes-youtube, un sistema de agentes: ninguno de ellos aprueba ni publica nada.")


def _envolver(titulo: str, cuerpo_html: str, botones: list | None = None, ayuda: str = "") -> str:
    return ("<div style='font-family:system-ui,-apple-system,sans-serif;max-width:640px;font-size:16px;line-height:1.5;color:#1a1a1a'>"
            f"<h2 style='font-size:19px;margin:0 0 12px'>{html.escape(titulo)}</h2>{cuerpo_html}"
            + (f"<p style='margin:18px 0 6px'>{''.join(botones)}</p>" if botones else "")
            + (f"<p style='font-size:14px;color:#444'>{html.escape(ayuda)}</p>" if ayuda else "")
            + f"<p style='color:#666;font-size:12px;margin-top:18px'>{html.escape(PIE)}</p></div>")


def _html(titulo: str, cuerpo: str, botones: list | None = None, ayuda: str = "") -> str:
    """Un correo sencillo: el texto tal cual (respetando sus saltos de línea) y, si los hay, sus botones."""
    pre = f"<div style='white-space:pre-wrap'>{html.escape(cuerpo)}</div>"
    return _envolver(titulo, pre, botones, ayuda)


class Doc:
    """El contenido de un correo, una vez: sale como texto y como HTML legible en un móvil."""

    def __init__(self):
        self.t, self.h = [], []

    def titulo(self, t: str):
        self.t += ["", t.upper(), ""]
        self.h.append(f"<h3 style='font-size:16px;margin:20px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px'>{html.escape(t)}</h3>")

    def parrafo(self, t: str, fuerte: bool = False):
        if str(t).strip():
            self.t.append(str(t))
            estilo = "margin:6px 0;font-weight:600" if fuerte else "margin:6px 0"
            self.h.append(f"<p style='{estilo};white-space:pre-wrap'>{html.escape(str(t))}</p>")

    def lista(self, items: list, numerada_desde: int | None = None):
        items = [str(x) for x in items if str(x).strip()]
        if not items:
            return
        for i, x in enumerate(items):
            self.t.append((f"{numerada_desde + i}. " if numerada_desde is not None else "- ") + x)
        etiqueta = f"ol start='{numerada_desde}'" if numerada_desde is not None else "ul"
        self.h.append(f"<{etiqueta} style='margin:6px 0;padding-left:24px'>"
                      + "".join(f"<li style='margin:6px 0;white-space:pre-wrap'>{html.escape(x)}</li>" for x in items)
                      + f"</{etiqueta.split()[0]}>")

    def pre(self, t: str):
        if str(t).strip():
            self.t += [str(t).rstrip(), ""]
            self.h.append("<div style='white-space:pre-wrap;background:#f6f6f4;border-radius:8px;padding:12px;margin:8px 0;"
                          f"font-size:15px'>{html.escape(str(t).rstrip())}</div>")

    def texto(self) -> str:
        return "\n".join(self.t).strip()

    def html(self) -> str:
        return "".join(self.h)


# ── el contenido de cada puerta ─────────────────────────────────────────────────────────────────────────────────────
def _carpeta(p: dict) -> Path | None:
    if not p.get("encargo"):
        return None
    return _cargar("hyt_encargos").carpeta(p["canal"], p["encargo"])


def _json(f: Path):
    return B.leer(f, None) if f and f.exists() else None


def _lee(f: Path) -> str:
    try:
        return f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _miniatura(doc: Doc, m: dict | None, con_foto: bool = False) -> None:
    if not isinstance(m, dict):
        doc.parrafo("Sin idea de miniatura elegida.")
        return
    pres, comp = m.get("presentador") or {}, m.get("composicion") or {}
    lineas = [f"Qué se ve: {m.get('que_se_ve', '')}" if m.get("que_se_ve") else "",
              f"Texto: «{m.get('texto', '')}»" if m.get("texto") else "",
              f"Expresión: {pres.get('expresion', '')}" + (f" · mirada: {pres['mirada']}" if pres.get("mirada") else "") if pres.get("expresion") else "",
              f"Composición: {comp.get('tipo', '')}" if comp.get("tipo") else "",
              f"Reparto con el título: {m.get('reparto', '')}" if m.get("reparto") else "",
              f"Nota de quien la eligió: {m.get('nota_de_la_persona', '')}" if m.get("nota_de_la_persona") else "",
              f"Foto que hay que pedir: {pres.get('foto_a_pedir', '')}" if con_foto and pres.get("foto_a_pedir") else ""]
    doc.lista(lineas)


def _datos_lineas(datos: list, solo_pendientes: bool = False) -> list:
    out = []
    for x in datos or []:
        if not isinstance(x, dict) or (solo_pendientes and x.get("estado", "pendiente") != "pendiente"):
            continue
        estado = x.get("estado", "pendiente") + (f" → {x['valor']}" if x.get("valor") else "")
        out.append(f"{x.get('dato', '')} [{estado}]" + (f"\nFrase: {x['frase']}" if x.get("frase") else "")
                   + (f"\nFuente: {x['fuente']}" if x.get("fuente") else ""))
    return out


def _cambios(d: Path) -> dict | None:
    """Qué frases han cambiado respecto a la última versión que vio una persona. Cada vez que se monta el paquete se
    guarda el guion tal como se presenta; los retoques internos de antes de la primera revisión no son «cambios»."""
    vistos = sorted((d / ".estado").glob("guion-presentado-*.md"), key=lambda f: int(re.sub(r"\D", "", f.stem) or 0)) \
        if (d / ".estado").is_dir() else []
    if len(vistos) < 2:
        return None
    c = _cargar("hyt_texto").cambios(_lee(vistos[-2]), _lee(vistos[-1]))
    return c if c["nuevas"] or c["quitadas"] else None


def _c_revision(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    paq = (_json(d / "paquete.json") if d else None) or {}
    if not d or not paq:
        doc.pre(p.get("texto", ""))
        return
    if int(p.get("ronda") or 0) or (d / ".estado").is_dir():
        c = _cambios(d)
        if c:
            doc.titulo(f"Lo que ha cambiado desde la versión anterior ({c['pct']} % de las frases)")
            doc.lista([f"Frase {n}: {f}" for n, f in c["nuevas"][:40]]
                      + [f"Quitada: {f}" for f in c["quitadas"][:40] if not any(f == x for _, x in c["nuevas"])])
    doc.titulo("Título")
    doc.parrafo(paq.get("titulo") or "(sin título elegido)", fuerte=True)
    if paq.get("promesa"):
        doc.parrafo(f"Promesa: {paq['promesa']}")
    doc.titulo("Miniatura")
    _miniatura(doc, paq.get("miniatura"))
    g = paq.get("guion") or {}
    doc.titulo("Guion" + (f" ({g.get('palabras')} palabras, unos {g.get('minutos')} min)" if g.get("palabras") else ""))
    numerado = _lee(d / "guion-numerado.md") or _lee(d / "guion.md")
    doc.parrafo("Cada frase lleva su número: para pedir un cambio puedes decir «frase 14: yo diría…».")
    doc.pre(numerado)
    doc.titulo("Descripción")
    doc.pre(_lee(d / "descripcion.md") or "(sin descripción)")
    rev = paq.get("revision") or {}
    doc.titulo(f"Revisión por código: nota {rev.get('nota', '—')}")
    doc.lista([("⛔ " if a.get("grave") else "⚠️ ") + str(a.get("texto", "")) for a in rev.get("avisos") or []] or ["Sin avisos."])
    ed = paq.get("editor") or {}
    if ed.get("notas") or ed.get("veredicto"):
        doc.titulo("Notas del editor" + (f" ({ed['veredicto']})" if ed.get("veredicto") else ""))
        doc.lista([str(n) for n in ed.get("notas") or []])
    datos = (_json(d / "datos.json") or {}).get("datos") or paq.get("datos") or []
    if datos:
        doc.titulo(f"Datos ({len(datos)})")
        doc.lista(_datos_lineas(datos))


def _c_temas(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    t = (_json(d / "temas.json") if d else None) or {}
    temas = [x for x in t.get("temas") or [] if isinstance(x, dict)]
    if not temas:
        doc.pre(p.get("texto", ""))
        return

    def linea(x: dict) -> str:
        return (f"[{x.get('pilar', '')}] {x.get('titulo', '')}" + (f"\n{x['resumen']}" if x.get("resumen") else "")
                + (f"\nNota: {x['nota']}" if x.get("nota") not in (None, "") else "")
                + (f" · «{x['frase']}»" if x.get("frase") else "")
                + (f"\nParecido a: {x['parecido_a']}" if x.get("parecido_a") else ""))
    doc.titulo(f"Temas propuestos ({len(temas)})")
    doc.lista([linea(x) for x in temas], numerada_desde=1)
    supl = [x for x in t.get("suplentes") or [] if isinstance(x, dict)]
    if supl:
        doc.titulo("Suplentes")
        doc.lista([linea(x) for x in supl], numerada_desde=len(temas) + 1)
    if t.get("avisos"):
        doc.titulo("Avisos")
        doc.lista([str(a) for a in t["avisos"]])


def _c_titulo(p: dict, doc: Doc) -> dict:
    d = _carpeta(p)
    op = (_json(d / "opciones.json") if d else None) or {}
    tits = [x for x in op.get("titulos") or [] if isinstance(x, dict)]
    if not tits:
        doc.pre(p.get("texto", ""))
        return {}
    rec = op.get("recomendacion") or {}
    brief = op.get("brief") or {}
    if brief.get("promesa"):
        doc.parrafo(f"Promesa del vídeo: {brief['promesa']}")
    if rec.get("titulo") or rec.get("miniatura"):
        doc.parrafo(f"Recomendación: título {rec.get('titulo', '—')} con la miniatura {rec.get('miniatura', '—')}"
                    + (f" (alternativa: título {rec['titulo_alternativo']})" if rec.get("titulo_alternativo") else ""), fuerte=True)
    doc.titulo("Títulos")
    doc.lista([f"{x.get('texto', '')}\n{x.get('caracteres', len(str(x.get('texto', ''))))} caracteres · en el móvil: «{x.get('movil', '')}»"
               + ("\n" + "; ".join(str(a) for a in x["avisos"]) if x.get("avisos") else "") for x in tits],
              numerada_desde=int(tits[0].get("n") or 1))
    minis = [x for x in op.get("miniaturas") or [] if isinstance(x, dict)]
    doc.titulo("Ideas de miniatura")
    for m in minis:
        doc.parrafo(f"Miniatura {m.get('n', '?')}" + (f": {m['concepto']}" if m.get("concepto") else ""), fuerte=True)
        _miniatura(doc, m)
    return rec


def _c_voz(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    doc.pre((_lee(d / "perfil-voz.md") if d else "") or p.get("texto", ""))


def _c_datos(p: dict, doc: Doc) -> None:
    PU = _cargar("hyt_puertas")
    pendientes = _datos_lineas(PU.datos_de(p), solo_pendientes=True)
    url = str((B.leer(B.home() / "yt.json", {}) or {}).get("panel_url") or "").strip()
    doc.parrafo(f"Hay {len(pendientes)} dato(s) por verificar, uno a uno: verificado, corregido o eliminado.", fuerte=True)
    doc.parrafo("Los datos no se verifican por correo: se hace " + (f"en el panel: {url}" if url else "en la pestaña YouTube del panel")
                + ". Cuando no quede ninguno pendiente, allí mismo se da la puerta por verificada.")
    doc.titulo("Datos pendientes")
    doc.lista(pendientes or ["Ninguno."])


def palabra(tipo: str, verbo: str) -> str:
    elegir = tipo in ELEGIR
    return {"acepto": "APROBAR", "algunas": "ELEGIR", "cambios": "OTRA" if elegir else "REHACER",
            "rechazo": "NINGUNO" if elegir else "RECHAZAR", "deshacer": "DESHACER"}.get(verbo, "RECHAZAR")


def _botones(p: dict, cod: dict, rec: dict | None = None) -> tuple:
    """(botones HTML, líneas de texto, ayuda) de una puerta, según su tipo y sus opciones vigentes."""
    PU = _cargar("hyt_puertas")
    tipo = p["tipo"]
    if tipo == "datos":
        return [], [], ""
    botones, lineas = [], []
    for o in PU.opciones_vigentes(p):
        v, pal = o["verbo"], palabra(tipo, o["verbo"])
        extra = ""
        if v == "cambios" and tipo not in ELEGIR:
            extra = f": {AYUDA_REHACER}"
        elif v == "rechazo":
            extra = f": {AYUDA_MOTIVO}"
        elif v == "algunas" and tipo == "elegir-temas":
            extra = f": {AYUDA_TEMAS}"
        elif v == "algunas" and tipo == "elegir-titulo":
            extra = f"\ntitulo: {(rec or {}).get('titulo') or 1}\nminiatura: {(rec or {}).get('miniatura') or 1}"
        color = {"acepto": "#1d7a46", "algunas": "#1d7a46", "rechazo": "#8a2c12"}.get(v, "#126a8a")
        botones.append(_boton(pal, cod[v], o["etiqueta"], extra, color))
        lineas.append(f"  {pal} {cod[v]}" + (": …" if extra.startswith(":") else ""))
    ayuda = {"elegir-temas": "Para elegir, escribe los números, por ejemplo: 1, 4, 7 (los suplentes siguen la numeración). «todos» elige todos los propuestos.",
             "elegir-titulo": "El botón de elegir ya lleva la pareja recomendada: basta con enviarlo. Puedes cambiar los números, escribir un "
                              "título propio («titulo: …»), añadir «nota: …» para la miniatura y «destino: …» para el vídeo al que lleva el cierre.",
             }.get(tipo, "Para pedir cambios, responde a este correo diciendo qué cambiar (o usa «Rehacer»). Un «ok» o un «gracias» no deciden nada."
                   if tipo in REVISAR else "")
    return botones, lineas, ayuda


def _hash(p: dict) -> str:
    """Huella de lo que se decide: si cambia entre el envío y la respuesta, los códigos dejan de valer."""
    base = p.get("texto", "")
    d = _carpeta(p)
    for nombre in ("guion.md", "opciones.json", "temas.json", "perfil-voz.md") if d else ():
        if (d / nombre).exists():
            base += _lee(d / nombre)
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _cuando(slug: str) -> str:
    try:   # en la hora del canal, no la del servidor (UTC)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(C.leer(slug).get("zona_horaria") or "Europe/Madrid")).strftime("%d-%m %H:%M")
    except Exception:   # noqa: BLE001
        return time.strftime("%d-%m %H:%M", time.localtime())


def componer(p: dict, cod: dict | None = None) -> dict:
    """El correo de una puerta: {asunto, texto, html}. Sin `cod`, sin botones (para enseñarlo o probarlo)."""
    PU = _cargar("hyt_puertas")
    doc, rec = Doc(), {}
    cab = " · ".join(x for x in (f"Puerta {int(p.get('indice') or 0) + 1} de {p.get('total')}" if int(p.get("total") or 1) > 1 else "",
                                 f"decide: {p['papel']}" if p.get("papel") else "",
                                 f"ronda {p['ronda']}" if p.get("ronda") else "") if x)
    if cab:
        doc.parrafo(cab)
    if p["tipo"] in ("revision", "revision-final"):
        _c_revision(p, doc)
    elif p["tipo"] == "elegir-temas":
        _c_temas(p, doc)
    elif p["tipo"] == "elegir-titulo":
        rec = _c_titulo(p, doc)
    elif p["tipo"] == "voz":
        _c_voz(p, doc)
    elif p["tipo"] == "datos":
        _c_datos(p, doc)
    else:
        doc.pre(p.get("texto", ""))
    if PU.graves(p) and p["tipo"] != "datos":
        doc.parrafo("⛔ Tiene un aviso grave: no se puede aprobar; solo rehacer o rechazar.", fuerte=True)
    botones, lineas, ayuda = _botones(p, cod, rec) if cod else ([], [], "")
    texto = f"{p['titulo']}\n\n{doc.texto()}"
    if lineas:
        texto += "\n\nPara decidir, responde con UNA de estas líneas (o usa los botones):\n" + "\n".join(lineas) + (f"\n\n{ayuda}" if ayuda else "")
    # asunto único por puerta: con el mismo asunto el correo junta la puerta nueva con las viejas y se pulsa un botón que ya no vale
    return {"asunto": f"🚪 {p['titulo']} · {_cuando(p['canal'])}", "texto": texto,
            "html": _envolver(p["titulo"], doc.html(), botones, ayuda)}


def enviar_puerta(p: dict) -> dict:
    """Envía una puerta abierta a quien tiene su papel, con un código por opción. Devuelve lo que se guarda en la puerta."""
    PU = _cargar("hyt_puertas")
    a = destinatarios(p["canal"], p.get("papel", ""))
    if not a:
        return {"enviado": B.ahora(), "a": [], "codigos": {}, "hash": _hash(p)}
    cod = {} if p["tipo"] == "datos" else {o["verbo"]: secrets.token_urlsafe(12) for o in PU.opciones_vigentes(p)}
    if cod:
        cod["deshacer"] = secrets.token_urlsafe(12)
    m = componer(p, cod)
    for _, correo in a:
        encolar(p["canal"], correo, m["asunto"], m["texto"], m["html"], tipo="puerta", puerta=p["id"])
    return {"codigos": cod, "hash": _hash(p), "enviado": B.ahora(), "a": [c for _, c in a]}


def _recordar_botones(p: dict, a: str, ref: str, motivo: str) -> None:
    """Contesta en el hilo sin decidir nada: por qué no ha valido y, otra vez, los botones de la puerta."""
    cod = (p.get("correo") or {}).get("codigos") or {}
    rec = ((_json(_carpeta(p) / "opciones.json") or {}).get("recomendacion") or {}) if p["tipo"] == "elegir-titulo" and _carpeta(p) else {}
    botones, lineas, ayuda = _botones(p, cod, rec) if cod else ([], [], "")
    if p["tipo"] == "datos":
        doc = Doc()
        _c_datos(p, doc)
        motivo += "\n\n" + doc.texto()
    texto = motivo + ("\n\nPara decidir:\n" + "\n".join(lineas) if lineas else "") + (f"\n\n{ayuda}" if ayuda else "")
    encolar(p["canal"], a, f"No he hecho nada todavía: {p['titulo']}", texto,
            _html(f"No he hecho nada todavía: {p['titulo']}", motivo, botones, ayuda), en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])


# ── entrada ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _sin_cita(texto: str) -> str:
    """Lo que escribió la persona: sin la cita del correo anterior ni la firma."""
    out = []
    for l in texto.splitlines():
        if l.startswith(">") or re.match(r"^(El|On) .{5,160}(escribió|wrote):\s*$", l) or l.strip() in ("--", "-- ") \
                or re.match(r"^-{2,}\s*(Mensaje original|Original Message)", l, re.I):
            break
        out.append(l)
    return "\n".join(out).strip()


def _sin_ayudas(texto: str) -> str:
    for a in AYUDAS:
        texto = texto.replace(a, "")
    return texto.strip()


def con_instruccion(texto: str) -> bool:
    """¿Dice qué cambiar? Un acuse («gracias», «ok», «perfecto», 👍…) o menos de 4 palabras con significado, no."""
    T = _cargar("hyt_texto")
    con_sentido = [w for w in T.contenido(texto) if w not in CORTESIAS]
    return len(con_sentido) >= 4


def _del_hilo(in_reply_to: str) -> dict | None:
    """El envío nuestro al que se responde (enviados.jsonl guarda el Message-ID de cada uno, con su canal y su puerta)."""
    ref = str(in_reply_to or "").strip().strip("<>").lower()
    if not ref:
        return None
    try:
        for l in reversed((_dir() / "enviados.jsonl").read_text().splitlines()):
            if ref in l.lower():
                r = json.loads(l)
                if str(r.get("message_id") or "").strip().strip("<>").lower() == ref:
                    return r
    except (OSError, ValueError):
        pass
    return None


def _sin_codigo_hoy(de: str) -> int:
    try:
        return sum(1 for l in (_dir() / "recibidos.jsonl").read_text().splitlines()
                   if _hoy() in l[:40] and f'"de": "{de}"' in l and '"sin_codigo": true' in l)
    except OSError:
        return 0


def _desconocido(m: dict, de: str) -> str:
    """Remitente que no es persona de ningún canal: se le dice una vez al día, y queda anotado para quien administra."""
    f = _dir() / "desconocidos.json"
    vistos = B.leer(f, {}) or {}
    if vistos.get(de) == _hoy():
        return "descartado: remitente desconocido (ya avisado hoy)"
    vistos = {k: v for k, v in vistos.items() if v == _hoy()}
    vistos[de] = _hoy()
    B.escribir(f, vistos)
    encolar("", de, "Tu dirección no está autorizada",
            "Este buzón es de un sistema que solo atiende a las personas dadas de alta en un canal. Tu dirección no está "
            "entre ellas, así que no he hecho nada con tu mensaje. Si crees que es un error, habla con quien administra el canal.",
            en_respuesta_a=m.get("message_id") or "", tipo="no-autorizado")
    B.anotar(B.home() / "acciones.jsonl", {"ts": B.ahora(), "tipo": "correo-no-autorizado", "de": de,
                                          "asunto": str(m.get("asunto", ""))[:120]})
    return "descartado: remitente desconocido (avisado)"


def _puerta_del_codigo(codigo: str, estados=("abierta", "decidida")) -> tuple:
    PU = _cargar("hyt_puertas")
    for p in PU.puertas(estados):
        for v, c in ((p.get("correo") or {}).get("codigos") or {}).items():
            if secrets.compare_digest(str(c), codigo):
                return p, v
    return None, None


def _decidir(p: dict, verbo: str, texto: str, clave: str, de: str, ref: str) -> str:
    """Decide por correo y contesta: si se firma al momento (aprobar, o sin ventana), un solo correo con el resultado;
    si no, la confirmación con su botón para deshacer."""
    PU = _cargar("hyt_puertas")
    slug, cod = p["canal"], (p.get("correo") or {}).get("codigos") or {}
    opcion = next((o for o in p["opciones"] if o["verbo"] == verbo), None) or {}
    try:
        dec = PU.decidir(p["id"], verbo, texto, clave, "email", de, {"message_id": ref})
    except Rechazo as e:
        _recordar_botones(p, de, ref, f"No se pudo: {e}")
        return f"rechazada: {e}"
    etiqueta = opcion.get("etiqueta", verbo)
    if verbo == "acepto" or float(dec.get("firmar_en") or 0) <= time.time():
        try:
            f = PU.firmar_ya(p["id"])
        except Rechazo as e:
            encolar(slug, de, f"⚠️ No se pudo completar: {p['titulo']}", f"Recibido «{etiqueta}», pero no se pudo completar: {e}",
                    en_respuesta_a=ref, tipo="resultado", puerta=p["id"])
            return f"decidida {p['id']} ({verbo}); error al firmar: {e}"
        PU.marcar(p["id"], correo_resultado=B.ahora())
        encolar(slug, de, f"✅ Hecho: {p['titulo']}", f"Recibido «{etiqueta}» y hecho: {f.get('resultado')}.",
                en_respuesta_a=ref, tipo="resultado", puerta=p["id"])
        return f"firmada {p['id']} ({verbo})"
    hora = time.strftime("%H:%M", time.localtime(float(dec["firmar_en"])))
    t = (f"Recibido: «{etiqueta}»" + (f"\n\n{texto}" if texto else "") + f"\n\nSe ejecuta a las {hora} si no lo deshaces."
         + (f"\n\nPara deshacerlo: DESHACER {cod['deshacer']}" if cod.get("deshacer") else ""))
    botones = [_boton("DESHACER", cod["deshacer"], "↩ Deshacer")] if cod.get("deshacer") else []
    encolar(slug, de, f"🕒 Recibido: {p['titulo']}", t, _html(f"Recibido: {p['titulo']}", t, botones), en_respuesta_a=ref,
            tipo="confirmacion", puerta=p["id"])
    return f"decidida {p['id']} ({verbo})"


def _con_codigo(m: dict, de: str, suyos: list, hallado, texto: str) -> str:
    PU = _cargar("hyt_puertas")
    ref = m.get("message_id") or ""
    codigo = hallado.group(2)
    resto = _sin_cita(hallado.group(3) or "")
    resto = _sin_ayudas(re.sub(r"\b(" + "|".join(PALABRAS) + r")\s+" + re.escape(codigo) + r"\s*:?", " ", resto)).strip()
    p, verbo = _puerta_del_codigo(codigo)
    if not p:
        return _codigo_viejo(de, suyos, codigo, ref)
    clave = next((k for s, k, _ in suyos if s == p["canal"]), None)
    m["_canal"] = p["canal"]
    if not clave:
        return "descartado: el código no es de una puerta de un canal suyo"
    slug = p["canal"]
    if verbo == "deshacer":
        try:
            PU.deshacer(p["id"], clave)
            PU.marcar(p["id"], correo=None)   # se reenvía con códigos nuevos
            encolar(slug, de, f"↩ Deshecho: {p['titulo']}", "Vuelve a estar pendiente: te reenvío la puerta.", en_respuesta_a=ref,
                    tipo="confirmacion", puerta=p["id"])
            return f"deshecha {p['id']}"
        except Rechazo as e:
            encolar(slug, de, f"No se pudo deshacer: {p['titulo']}", str(e), en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
            return f"no deshecha: {e}"
    if p["estado"] != "abierta":
        encolar(slug, de, f"Ya estaba decidida: {p['titulo']}", "Esa puerta ya no está pendiente: no he hecho nada.",
                en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
        return "ya decidida"
    if (p.get("correo") or {}).get("hash") != _hash(p):
        PU.marcar(p["id"], correo=None)
        encolar(slug, de, f"Ha cambiado: {p['titulo']}", "Lo que se decide ha cambiado desde que te escribí: te mando la versión nueva. "
                "No he hecho nada con tu respuesta.", en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
        return "contenido cambiado: se reenvía"
    opcion = next((o for o in p["opciones"] if o["verbo"] == verbo), None) or {}
    if opcion.get("texto") and not resto:
        if verbo == "rechazo":
            resto = "Rechazado por correo, sin motivo"
        else:
            _recordar_botones(p, de, ref, "Falta decir cuáles eliges." if verbo == "algunas" else
                              "Falta decir qué hay que cambiar: escríbelo detrás del código.")
            return f"{verbo} sin texto: se pide"
    return _decidir(p, verbo, resto, clave, de, ref)


def _codigo_viejo(de: str, suyos: list, codigo: str, ref: str) -> str:
    """Un código que no es de ninguna puerta pendiente: se le dice a la persona por qué no ha valido."""
    PU = _cargar("hyt_puertas")
    vieja, _ = _puerta_del_codigo(codigo, ("firmada", "error", "reemplazada", "caducada"))
    canales = {s for s, _, _ in suyos}
    if vieja and vieja["canal"] in canales:
        misma = next((p for p in PU.puertas(("abierta",)) if p.get("encargo") and p.get("encargo") == vieja.get("encargo")
                      and (p.get("correo") or {}).get("enviado")), None)
        t = (f"Ese botón es de un correo anterior de «{vieja['titulo']}» y ya no vale: no he hecho nada."
             + ("\n\nHay una versión vigente: usa los botones de su correo, el más reciente." if misma else " Esa puerta ya está cerrada."))
    else:
        vieja = None
        t = "No reconozco ese código: no he hecho nada. Usa los botones del correo más reciente."
    encolar(next(iter(canales), ""), de, "Ese botón ya no vale", t, en_respuesta_a=ref, tipo="confirmacion")
    return "código viejo: avisado" if vieja else "descartado: código desconocido (avisado)"


def _en_hilo(m: dict, de: str, suyos: list, p: dict, texto: str) -> str:
    """Respuesta sin código en el hilo de una puerta."""
    ref = m.get("message_id") or ""
    clave = next((k for s, k, _ in suyos if s == p["canal"]), None)
    m["_canal"] = p["canal"]
    if not clave:
        return "descartado: el hilo es de un canal que no es suyo"
    if p["estado"] != "abierta":
        encolar(p["canal"], de, f"Ya estaba decidida: {p['titulo']}", "Esa puerta ya no está pendiente: no he hecho nada con tu respuesta.",
                en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
        return "hilo de una puerta ya decidida"
    if p["tipo"] not in REVISAR:
        _recordar_botones(p, de, ref, "Aquí un texto libre no decide nada: " + ("los datos se verifican en el panel." if p["tipo"] == "datos"
                                                                              else "usa uno de los botones."))
        return "texto libre en una puerta que no lo admite: botones"
    if not _puede(p, clave):
        _recordar_botones({**p, "correo": {}}, de, ref, f"Esta puerta la decide quien tiene el papel «{p.get('papel') or 'marketing'}».")
        return "texto libre de quien no decide esta puerta"
    if not con_instruccion(texto):
        _recordar_botones(p, de, ref, "Tu respuesta no dice qué hay que cambiar, así que no he decidido nada.")
        return "respuesta sin instrucción: botones"
    if not any(o["verbo"] == "cambios" for o in p["opciones"]):
        _recordar_botones(p, de, ref, "Esta puerta no admite rehacer.")
        return "la puerta no admite rehacer"
    return _decidir(p, "cambios", texto[:4000], clave, de, ref)


# ── peticiones: tres órdenes cerradas, sin modelo ───────────────────────────────────────────────────────────────────
def _primera_linea(t: str) -> str:
    return next((l.strip() for l in str(t).splitlines() if l.strip()), "")


def _campo(texto: str, nombre: str) -> str:
    m = re.search(rf"^\s*{nombre}\s*:\s*(.+)$", texto, re.M)
    return _sin_ayudas(m.group(1)).strip() if m else ""


def intencion(asunto: str, texto: str) -> dict | None:
    """{orden: propuesta|estado|tema, tema?, pilar?, canal?} por la primera palabra (en mayúsculas) del asunto o del
    cuerpo. PROPUESTA y ESTADO van solas en su línea, para que una frase que empiece así no lance nada."""
    asunto = re.sub(r"^\s*((re|rv|fw|fwd)\s*:\s*)+", "", str(asunto or ""), flags=re.I).strip()
    todo = f"{asunto}\n{texto}"
    for fuente in (asunto, _primera_linea(texto)):
        if re.fullmatch(r"(PROPUESTA|ESTADO)\.?", fuente):
            return {"orden": fuente.strip(".").lower(), "canal": _campo(todo, "CANAL")}
        if re.match(r"TEMA\s*:", fuente):
            tema = next((t for t in (_campo(texto, "TEMA"), _campo(asunto, "TEMA")) if t), "")
            return {"orden": "tema", "tema": tema, "pilar": _campo(todo, "PILAR"), "canal": _campo(todo, "CANAL")}
    return None


def _ayuda_peticiones(slug: str, a: str, ref: str, motivo: str = "") -> None:
    lineas = ["Puedes pedirme tres cosas, con una palabra al principio del correo:",
              "  PROPUESTA — preparo una propuesta de temas",
              "  TEMA: <el tema> (y, si quieres, PILAR: <id>) — preparo título y miniatura para un tema tuyo",
              "  ESTADO — te digo cómo va cada vídeo",
              "Cualquier otra cosa no la entiendo: no hay nadie leyendo este buzón."]
    extra = f"\nCANAL: {slug}" if slug else ""
    botones = [_boton("PROPUESTA", "", "💡 Pedir una propuesta", extra),
               f'<a href="{html.escape(_mailto("TEMA: ", f"TEMA: {AYUDA_TEMA}{chr(10)}PILAR: {AYUDA_PILAR}{extra}"))}" style="display:inline-block;'
               'padding:12px 18px;margin:4px 6px 4px 0;border-radius:8px;background:#126a8a;color:#fff;text-decoration:none;'
               'font-weight:600;font-size:16px">✍️ Tema propio</a>',
               _boton("ESTADO", "", "📋 Ver el estado", extra)]
    t = (motivo + "\n\n" if motivo else "") + "\n".join(lineas)
    encolar(slug, a, "Cómo pedirme algo", t, _html("Cómo pedirme algo", t, botones), en_respuesta_a=ref, tipo="ayuda")


def estado_texto(slug: str) -> str:
    """La lista de vídeos del canal, para un correo."""
    V = _cargar("hyt_videos")
    lineas = []
    for v in V.lista(slug):
        puerta = v.get("puerta") or {}
        lineas.append(f"• {v.get('titulo', '')}" + (f" [{v['pilar']}]" if v.get("pilar") else "") + f" — {v.get('estado', '')}"
                      + (f" · ronda {v['ronda']} de {v.get('rondas_max', '?')}" if v.get("ronda") else "")
                      + (f" · espera: {puerta.get('papel') or 'una decisión'}" if puerta else "")
                      + (f" · ⚠️ {v['incidencia']}" if v.get("incidencia") else ""))
    return "\n".join(lineas) or "Todavía no hay ningún vídeo en marcha."


def _peticion(m: dict, de: str, suyos: list, texto: str) -> str:
    E = _cargar("hyt_encargos")
    ref = m.get("message_id") or ""
    marketing = [(s, k) for s, k, p in suyos if "marketing" in (p.get("roles") or [])]
    if not marketing:
        s = suyos[0][0]
        m["_canal"] = s
        encolar(s, de, "No he hecho nada con tu mensaje", "Este buzón solo entiende las respuestas a sus correos (con sus botones). "
                "Pedir trabajo nuevo es cosa de quien lleva marketing en el canal.", en_respuesta_a=ref, tipo="ayuda")
        return "ayuda: no es de marketing"
    orden = intencion(m.get("asunto", ""), texto)
    pedido = (orden or {}).get("canal", "")
    elegido = next(((s, k) for s, k in marketing if s == pedido), None) or (marketing[0] if len(marketing) == 1 else None)
    if not elegido:
        nombres = ", ".join(s for s, _ in marketing)
        _ayuda_peticiones("", de, ref, f"Llevas varios canales ({nombres}): añade una línea «CANAL: <nombre corto>» para saber de cuál hablas.")
        return "ayuda: falta decir el canal"
    slug, clave = elegido
    m["_canal"] = slug
    varios = slug if len(marketing) > 1 else ""
    if not orden:
        _ayuda_peticiones(varios, de, ref)
        return "ayuda: no es una orden"
    quien = f"{clave} (correo)"
    try:
        if orden["orden"] == "estado":
            t = estado_texto(slug)
            encolar(slug, de, f"📋 Estado de {C.leer(slug).get('nombre') or slug}", t, en_respuesta_a=ref, tipo="respuesta")
            return "petición: estado"
        if orden["orden"] == "propuesta":
            e = E.lanzar(slug, "propuesta", {}, quien=quien)
            ya = " (ya había una en marcha: no lanzo otra)" if e.get("duplicado") else ""
            encolar(slug, de, "💡 Propuesta de temas en marcha", f"Estoy preparando una propuesta de temas{ya}. Cuando esté, te llegará "
                    "un correo para elegir.", en_respuesta_a=ref, tipo="respuesta")
            return f"petición: propuesta {e['id']}"
        if not orden.get("tema"):
            _ayuda_peticiones(varios, de, ref, "Falta el tema: escríbelo detrás de «TEMA:».")
            return "ayuda: tema vacío"
        pilares = [x.get("id") for x in C.leer(slug).get("pilares") or [] if isinstance(x, dict)]
        pilar = orden.get("pilar", "")
        if pilar and pilares and pilar not in pilares:
            _ayuda_peticiones(varios, de, ref, f"No conozco el pilar «{pilar}». Los de este canal: {', '.join(pilares)}.")
            return "ayuda: pilar desconocido"
        e = E.lanzar(slug, "titulo-miniatura", {"tema": orden["tema"][:200], "pilar": pilar or "sin-pilar"},
                     brief=f"Tema propio, pedido por correo por {clave}.", quien=quien)
        ya = " (ya estaba en marcha: no lanzo otro)" if e.get("duplicado") else ""
        encolar(slug, de, f"✍️ En marcha: {orden['tema'][:80]}", f"Estoy preparando título y miniatura para «{orden['tema']}»{ya}. "
                "Cuando estén, te llegará un correo para elegir.", en_respuesta_a=ref, tipo="respuesta")
        return f"petición: tema {e['id']}"
    except Rechazo as x:
        encolar(slug, de, "No he podido hacerlo", str(x), en_respuesta_a=ref, tipo="respuesta")
        return f"petición rechazada: {str(x)[:120]}"


def procesar(m: dict) -> str:
    """Un correo recibido (ya auténtico y no automático). Devuelve lo que se hizo (para el registro)."""
    PU = _cargar("hyt_puertas")
    de = str(m.get("de") or "").strip().lower()
    suyos = de_quien(de)
    if not suyos:
        return _desconocido(m, de)
    texto = _sin_cita(str(m.get("texto") or ""))
    hallado = CODIGO.search(texto) or CODIGO.search(str(m.get("asunto") or ""))
    if hallado:
        return _con_codigo(m, de, suyos, hallado, texto)
    m["_sin_codigo"] = True
    if _sin_codigo_hoy(de) >= TOPE_DIA:
        return "descartado: tope diario de correos sin código"
    hilo = _del_hilo(m.get("in_reply_to"))
    if hilo and hilo.get("puerta"):
        try:
            return _en_hilo(m, de, suyos, PU.leer(hilo["puerta"]), _sin_ayudas(texto))
        except Rechazo:
            pass
    if not texto and not str(m.get("asunto") or "").strip():
        return "vacío"
    return _peticion(m, de, suyos, texto)


def recoger() -> int:
    r = _http("GET", "/pendientes")
    hechos = []
    for m in r.get("correos") or []:
        try:
            res = procesar(m)
        except Exception as e:   # noqa: BLE001 — un correo raro no para el resto
            res = f"error: {str(e)[:150]}"
        B.anotar(_dir() / "recibidos.jsonl", {"ts": B.ahora(), "de": str(m.get("de") or "").strip().lower(), "id": m.get("id"),
                                              "canal": m.get("_canal") or "", "sin_codigo": bool(m.get("_sin_codigo")),
                                              "asunto": str(m.get("asunto", ""))[:120], "resultado": res})
        hechos.append(m["id"])
    if hechos:
        _http("POST", "/hecho", {"ids": hechos})
    if r.get("descartados_hoy"):
        B.escribir(_dir() / "descartados-hoy.json", r["descartados_hoy"])
    return len(hechos)


# ── puertas: enviar las abiertas, firmar lo vencido, contar lo firmado ──────────────────────────────────────────────
def enviar_puertas() -> int:
    PU = _cargar("hyt_puertas")
    n = 0
    for p in PU.puertas(("abierta",)):
        if p.get("correo"):
            continue
        try:
            PU.marcar(p["id"], correo=enviar_puerta(p))
            n += 1
        except Exception as e:   # noqa: BLE001 — una puerta que no se puede componer no para las demás
            PU.marcar(p["id"], correo={"enviado": B.ahora(), "a": [], "codigos": {}, "error": str(e)[:200]})
    return n


def firmar_vencidas() -> int:
    """Firma lo decidido por correo cuya ventana para deshacer ya pasó (lo de Telegram y el panel lo firma su bucle)."""
    PU = _cargar("hyt_puertas")
    n = 0
    for p in PU.puertas(("decidida",)):
        if ((p.get("decision") or {}).get("actor") or {}).get("medio") == "email" and time.time() >= float(p.get("firmar_en") or 0):
            try:
                PU.firmar(p["id"])
                n += 1
            except Rechazo:
                pass   # queda en «error», a la vista
    return n


def _paquete_aprobado(p: dict, enc: dict) -> None:
    """El guion aprobado, a quien presenta y a marketing: título, miniatura (con la foto que hay que pedir), descripción
    y el guion limpio en el cuerpo."""
    E = _cargar("hyt_encargos")
    slug, eid = p["canal"], p["encargo"]
    d = E.carpeta(slug, eid)
    paq = _json(d / "paquete.json") or {}
    try:
        guion = _cargar("hyt_videos").exportar(slug, eid, "guion")
    except Exception:   # noqa: BLE001 — sin la exportación, el fichero limpio que dejó el paquete
        guion = _lee(d / "guion-limpio.txt") or _lee(d / "guion.md")
    doc = Doc()
    doc.parrafo(f"Aprobado por {p.get('firma', '')}. Ya se puede grabar.")
    doc.titulo("Título")
    doc.parrafo(paq.get("titulo", ""), fuerte=True)
    doc.titulo("Miniatura")
    _miniatura(doc, paq.get("miniatura"), con_foto=True)
    doc.titulo("Descripción")
    doc.pre(_lee(d / "descripcion.md"))
    doc.titulo("Guion")
    doc.pre(guion)
    asunto = f"🎬 Aprobado, listo para grabar: {paq.get('titulo') or enc.get('nombre', '')}"
    a = {c for papel in ("presentador", "marketing") for _, c in destinatarios(slug, papel)}
    for correo in sorted(a):
        encolar(slug, correo, asunto, doc.texto(), _envolver(asunto, doc.html()), tipo="aprobado", puerta=p["id"])


def tras_firma(p: dict) -> None:
    """Lo que hay que contar por correo de una puerta ya firmada (una sola vez): el resultado a quien decidió por
    correo, el rechazo de quien presenta y el descarte por rondas a marketing, y el paquete aprobado a quien graba."""
    PU, E = _cargar("hyt_puertas"), _cargar("hyt_encargos")
    slug, dec = p["canal"], p.get("decision") or {}
    actor, verbo, resultado = dec.get("actor") or {}, dec.get("verbo"), str(p.get("resultado") or "")
    if time.time() - _epoch(p.get("firmada") or "") > 86400:
        return   # lo firmado hace más de un día (antes de activar el correo) no se cuenta ahora
    if actor.get("medio") == "email" and actor.get("id") and not p.get("correo_resultado"):   # si no se le dijo ya al firmar
        encolar(slug, str(actor["id"]), f"✅ Hecho: {p['titulo']}", f"{p.get('firma')}: {resultado}.", tipo="resultado", puerta=p["id"])
    marketing = [c for _, c in destinatarios(slug, "marketing") if c != str(actor.get("id") or "")]
    if verbo == "rechazo" and p.get("papel") == "presentador":
        for c in marketing:
            encolar(slug, c, f"🗑 Rechazado por quien presenta: {p['titulo']}",
                    f"{p.get('firma')} ha rechazado este vídeo.\n\nMotivo: {dec.get('texto') or 'sin motivo'}", tipo="aviso", puerta=p["id"])
    elif resultado.startswith("descartado: superó"):
        for c in marketing:
            encolar(slug, c, f"🗑 Descartado por rondas: {p['titulo']}",
                    f"Se pidió rehacer una vez más de las que admite el canal y el vídeo queda descartado ({resultado}).\n\n"
                    f"Lo último que se pidió ({p.get('firma')}): {dec.get('texto') or '—'}", tipo="aviso", puerta=p["id"])
    if verbo == "acepto" and p.get("encargo"):
        try:
            enc = E.leer(slug, p["encargo"])
        except Rechazo:
            return
        if enc.get("estado") == "cerrado" and (E.carpeta(slug, p["encargo"]) / "paquete.json").exists():
            _paquete_aprobado(p, enc)


def avisar_firmadas() -> int:
    PU = _cargar("hyt_puertas")
    n = 0
    for p in PU.puertas(("firmada",)):
        if p.get("correo_avisos"):
            continue
        try:
            tras_firma(p)
        except Exception:   # noqa: BLE001 — un aviso que falla no para el ciclo ni se reintenta sin fin
            pass
        PU.marcar(p["id"], correo_avisos=B.ahora())
        n += 1
    return n


def resumen() -> int:
    """Un correo por persona con sus puertas abiertas y su antigüedad, si alguna lleva más de 24 h. Una vez al día."""
    PU = _cargar("hyt_puertas")
    por_persona: dict = {}
    for p in PU.puertas(("abierta",)):
        for _, correo in destinatarios(p["canal"], p.get("papel", "")):
            por_persona.setdefault(correo, []).append(p)
    f = _dir() / "resumen.json"
    hechos = B.leer(f, {}) or {}
    n = 0
    for correo, ps in sorted(por_persona.items()):
        horas = {p["id"]: (time.time() - _epoch(p.get("creada") or "")) / 3600 for p in ps}
        if max(horas.values()) < RESUMEN_HORAS or hechos.get(correo) == _hoy():
            continue
        ps.sort(key=lambda p: -horas[p["id"]])

        def edad(h: float) -> str:
            return f"{int(h)} h" if h < 48 else f"{int(h // 24)} días"
        lineas = [f"• {p['titulo']} — espera desde hace {edad(horas[p['id']])}"
                  + (f" · {PU.datos_pendientes(p)} dato(s) por verificar, en el panel" if p["tipo"] == "datos" else "") for p in ps]
        t = (f"Tienes {len(ps)} decisión(es) pendiente(s):\n\n" + "\n".join(lineas)
             + "\n\nCada una tiene su propio correo, con sus botones: búscalo por su título. Los datos se verifican en el panel.")
        encolar(ps[0]["canal"], correo, f"⏳ Te esperan {len(ps)} decisión(es)", t, tipo="resumen")
        hechos[correo] = _hoy()
        n += 1
    B.escribir(f, {k: v for k, v in hechos.items() if v == _hoy()})
    return n


def ciclo() -> tuple:
    """(recogidos, enviados). Recoge, envía las puertas abiertas, firma lo vencido, cuenta lo firmado y despacha."""
    if not activo():
        return 0, 0
    n = recoger()
    enviar_puertas()
    firmar_vencidas()
    avisar_firmadas()
    enviar_puertas()   # las que haya abierto una firma (la siguiente de la cadena)
    return n, despachar()


def prueba(slug: str) -> int:
    a = destinatarios(slug, "marketing")
    for _, correo in a:
        encolar(slug, correo, "🧪 Prueba del correo de hermes-youtube", "Si te llega, el envío funciona. Responde con ESTADO y te "
                "contestaré con la lista de vídeos del canal.", tipo="prueba")
    return len(a)


def main(argv=None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    try:
        if a[:1] == ["ciclo"]:
            print("recogidos %d · enviados %d" % ciclo())
        elif a[:1] == ["resumen"]:
            n = resumen()
            print(f"{n} resumen(es) encolado(s) · enviados {despachar() if activo() else 0}")
        elif a[:1] == ["prueba"] and len(a) == 2:
            C.leer(a[1])
            n = prueba(a[1])
            print(f"encolado para {n} persona(s) de marketing: sale en el próximo ciclo" if n else
                  "Nadie con el papel «marketing» tiene correo en ese canal (canal.json → personas)")
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Rechazo as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
