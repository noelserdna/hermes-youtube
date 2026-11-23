"""Correo de hermes-youtube: un solo buzón para todos los canales, y decisiones por CÓDIGO (nunca por un modelo).

Las personas de cada canal están en canal.json → personas ({clave: {nombre, correo, roles}}). El Worker de Cloudflare
(correo/), o un buzón normal por IMAP y SMTP (hyt_buzon.py), recibe en el buzón, comprueba que el correo es auténtico
y no automático, y lo deja en una cola; el ciclo (cada minuto, desde el bucle del plugin o con «hyt correo ciclo») lo
recoge, envía lo pendiente y firma lo decidido.

  · Puertas: cada puerta abierta se envía a las personas del canal con su papel (sin papel, a las de marketing), con el
    contenido completo y botones mailto: que llevan un código de un solo uso por opción (APROBAR <código>, REHACER
    <código>: …, RECHAZAR <código>; ELEGIR, OTRA y NINGUNO en las de elegir). Decide el código: el remitente es una
    persona de ese canal con ese papel, el código es de una puerta abierta y el contenido no ha cambiado. Si una
    opción admite varios valores (elegir-version: «algunas» con A o B), sale un botón y un código por valor
    (clave «algunas:A»): el código ya dice qué se elige.
  · Todos los correos usan una plantilla (cabecera de color por tipo, fichas, vista previa como en YouTube, guion por
    bloques, botones por color), con tablas y estilos en línea, sin imágenes ni <style>, y por debajo de 95 KB.
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
    if c.get("HYT_CORREO_IMAP"):   # buzón normal por IMAP y SMTP (hyt_buzon) en lugar del Worker
        return all(c.get(k) for k in ("HYT_CORREO_BUZON", "HYT_CORREO_SMTP", "HYT_CORREO_USUARIO", "HYT_CORREO_CLAVE"))
    return bool(c.get("HYT_CORREO_URL") and c.get("HYT_CORREO_SECRETO") and c.get("HYT_CORREO_BUZON"))


def _http(metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    c = conf()
    if c.get("HYT_CORREO_IMAP"):
        return _cargar("hyt_buzon").llamar(c, metodo, ruta, cuerpo, _dir())
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
    m = {"canal": slug, "tipo": tipo, "to": a, "subject": asunto[:300], "text": texto, "html": html_ or _html(asunto, texto, tipo=tipo, canal=slug),
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


# ── aspecto: una plantilla para todos los correos ───────────────────────────────────────────────────────────────────
# Tablas y estilos en línea (Gmail quita <style> y no carga CSS externo), sin imágenes, y contrastes fuertes: si el
# cliente invierte los colores a oscuro, el texto oscuro sobre fondo claro (y el blanco sobre fondo de color) se sigue
# leyendo. Gmail corta un correo a partir de 102 KB: por encima de TOPE_HTML se recortan los guiones.
TOPE_HTML = 95_000
LETRA = "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif"   # sin comillas: va dentro de style='…'
TINTA, TINTA2 = "#1c1f24", "#3a3f47"           # texto y texto secundario (nunca gris claro)
FONDO, PAPEL, CARTA, LINEA = "#e9e4da", "#fbf8f2", "#ffffff", "#cfc6b6"
VERDE, AMBAR, ROJO, AZUL, PIZARRA = "#166534", "#a1450a", "#b91c1c", "#1d4ed8", "#334155"
SUAVE = {"mal": ("#fde4e4", "#e7a0a0", "#7a1010"), "ojo": ("#fdf0d5", "#e6c27a", "#5c3906"),
         "bien": ("#dff3e4", "#94cfa4", "#0f4d24"), "": ("#f3efe7", LINEA, TINTA)}   # (fondo, borde, texto)
# tipo: (nombre, color de cabecera, color de la franja)
TIPOS = {"revision": ("Revisión del guion", "#1e3a8a", "#3b82f6"),
         "revision-final": ("Revisión final", "#4c1d95", "#8b5cf6"),
         "datos": ("Datos por verificar", "#134e4a", "#14b8a6"),
         "elegir-temas": ("Elegir temas", "#7c2d12", "#f97316"),
         "elegir-titulo": ("Elegir título y miniatura", "#7c2d12", "#f59e0b"),
         "elegir-version": ("Elegir versión", "#701a75", "#d946ef"),
         "voz": ("Perfil de voz", "#164e63", "#06b6d4"),
         "alta": ("Alta", "#1e293b", "#64748b"), "decision": ("Decisión", "#1e3a8a", "#3b82f6"),
         "aprobado": ("Listo para grabar", "#14532d", "#22c55e"), "resultado": ("Hecho", "#14532d", "#22c55e"),
         "confirmacion": ("Recibido", "#1e293b", "#64748b"), "aviso": ("Aviso", "#7f1d1d", "#ef4444"),
         "resumen": ("Pendientes", "#78350f", "#f59e0b"), "respuesta": ("Respuesta", "#1e3a8a", "#3b82f6"),
         "ayuda": ("Ayuda", "#1e3a8a", "#3b82f6"), "prueba": ("Prueba", "#1e293b", "#64748b"),
         "no-autorizado": ("Aviso", "#1e293b", "#64748b")}
COLOR_PALABRA = {"APROBAR": VERDE, "ELEGIR": VERDE, "REHACER": AMBAR, "OTRA": AMBAR, "RECHAZAR": ROJO, "NINGUNO": ROJO,
                 "DESHACER": PIZARRA}
E_ = html.escape


def _tabla(contenido: str, estilo: str = "", ancho: str = "100%") -> str:
    return (f"<table role='presentation' width='{ancho}' cellpadding='0' cellspacing='0' border='0' "
            f"style='border-collapse:separate;{estilo}'>{contenido}</table>")


def _chip(t: str, fondo: str = "#ffffff", color: str = TINTA, borde: str = "") -> str:
    return (f"<span style='display:inline-block;margin:0 6px 6px 0;padding:3px 10px;border-radius:999px;background:{fondo};"
            f"color:{color};font-size:13px;font-weight:700;line-height:1.5;{'border:1px solid ' + borde if borde else ''}'>{E_(str(t))}</span>")


def _enlace(url: str, texto: str = "") -> str:
    return (f"<a href='{E_(url, quote=True)}' style='color:{AZUL};font-weight:600;text-decoration:underline;word-break:break-word'>"
            f"{E_(texto or url)}</a>")


def _externo(x: dict) -> bool:
    """Un dato que viene de fuera del material del canal (lo trajo la investigación): con motivo «externo» o fuente web."""
    return _es_url(x.get("fuente")) or str(x.get("fuente") or "").startswith("web/") or \
        (x.get("motivo") == "externo" and not str(x.get("fuente") or "").startswith(("charlas/", "docs/")))


def _es_url(x) -> bool:
    return isinstance(x, str) and bool(re.match(r"https?://\S+$", x.strip()))


def _dominio(url: str) -> str:
    return re.sub(r"^www\.", "", urllib.parse.urlsplit(url).netloc) or url


def _boton(palabra: str, codigo: str, etiqueta: str, extra: str = "", color: str = "", ayuda: str = "") -> str:
    """Un botón grande que abre un correo ya escrito: «PALABRA código» en el asunto y en el cuerpo (con `extra` detrás).
    Su color sale del verbo (aprobar y elegir, verde; rehacer, ámbar; rechazar, rojo); `ayuda`, una línea debajo."""
    cabeza = f"{palabra} {codigo}".strip()
    color = color or COLOR_PALABRA.get(palabra, AZUL)
    return _tabla(f"<tr><td style='border-radius:12px;background:{color}' bgcolor='{color}'>"
                  f"<a href=\"{E_(_mailto(cabeza, cabeza + extra))}\" style='display:block;padding:15px 18px;border-radius:12px;"
                  f"color:#ffffff;text-decoration:none;text-align:center;font-family:{LETRA};font-size:18px;font-weight:800;"
                  f"line-height:1.25'>{E_(etiqueta)}</a></td></tr>"
                  + (f"<tr><td style='padding:6px 4px 0;font-size:14px;line-height:1.4;color:{TINTA2}'>{E_(ayuda)}</td></tr>" if ayuda else ""),
                  "margin:0 0 14px")


def _boton_web(url: str, etiqueta: str, color: str = AZUL) -> str:
    """Un botón que abre una página (el panel): no decide nada."""
    return _tabla(f"<tr><td style='border-radius:12px;background:{color}' bgcolor='{color}'><a href='{E_(url, quote=True)}' "
                  f"style='display:block;padding:14px 18px;border-radius:12px;color:#ffffff;text-decoration:none;text-align:center;"
                  f"font-size:17px;font-weight:800'>{E_(etiqueta)}</a></td></tr>", "margin:8px 0 14px")


PIE = ("Cada botón abre un correo ya escrito: solo tienes que enviarlo. Un «sí» escrito a mano no decide nada. "
       "Te escribe hermes-youtube, un sistema de agentes: ninguno de ellos aprueba ni publica nada.")


def _nombre_canal(slug: str) -> str:
    try:
        return str(C.leer(slug).get("nombre") or slug) if slug else ""
    except Exception:   # noqa: BLE001
        return slug


def _envolver(titulo: str, cuerpo_html: str, botones: list | None = None, ayuda: str = "", tipo: str = "aviso",
              canal: str = "", chips: list | None = None, cola_html: str = "") -> str:
    """La plantilla común: cabecera de color (canal, tipo, título y chips), franja del tipo, cuerpo, botones y pie.
    `cola_html` va después de los botones (lo largo, para que decidir no quede al final de todo)."""
    nombre, oscuro, franja = TIPOS.get(tipo, TIPOS["aviso"])
    arriba = " · ".join(x for x in (_nombre_canal(canal), nombre) if x)
    cab = (f"<tr><td bgcolor='{oscuro}' style='background:{oscuro};padding:20px 22px 14px;color:#ffffff'>"
           f"<div style='font-size:13px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#ffffff'>{E_(arriba)}</div>"
           f"<div style='font-size:23px;font-weight:800;line-height:1.25;margin:6px 0 10px;color:#ffffff'>{E_(titulo)}</div>"
           + "".join(_chip(c, "#ffffff", oscuro) for c in chips or [] if c) + "</td></tr>"
           f"<tr><td bgcolor='{franja}' style='background:{franja};height:6px;line-height:6px;font-size:0'>&nbsp;</td></tr>")
    decidir = ""
    if botones:
        decidir = (f"<tr><td style='padding:6px 20px 4px'>"
                   f"<div style='font-size:18px;font-weight:800;color:{TINTA};margin:10px 0 12px'>Decide</div>{''.join(botones)}"
                   + (f"<div style='font-size:14px;line-height:1.45;color:{TINTA2};margin:2px 0 8px'>{E_(ayuda)}</div>" if ayuda else "")
                   + "</td></tr>")
    elif ayuda:
        decidir = f"<tr><td style='padding:0 20px 8px;font-size:14px;color:{TINTA2}'>{E_(ayuda)}</td></tr>"
    cuerpo = (f"<tr><td style='padding:16px 20px 6px;color:{TINTA};font-size:16px;line-height:1.5'>{cuerpo_html}</td></tr>"
              + decidir
              + (f"<tr><td style='padding:6px 20px 6px;color:{TINTA};font-size:16px;line-height:1.5'>{cola_html}</td></tr>" if cola_html else "")
              + f"<tr><td style='padding:14px 20px 20px;border-top:1px solid {LINEA};font-size:13px;line-height:1.45;color:{TINTA2}'>"
              f"{E_(PIE)}</td></tr>")
    caja = (f"<table role='presentation' align='center' width='100%' cellpadding='0' cellspacing='0' border='0' "
            f"style='max-width:640px;margin:0 auto;border-collapse:separate;background:{PAPEL};border:1px solid {LINEA};"
            f"border-radius:16px;overflow:hidden' bgcolor='{PAPEL}'>{cab}{cuerpo}</table>")
    return (f"<div style='background:{FONDO};padding:14px 6px;font-family:{LETRA};color:{TINTA};-webkit-text-size-adjust:100%'>"
            f"{caja}</div>")


def _parrafos(texto: str) -> str:
    """Texto suelto en HTML: un párrafo por hueco, los «• …» como lista y los saltos de línea respetados."""
    out = []
    for trozo in re.split(r"\n\s*\n", str(texto).strip()):
        lineas = trozo.splitlines()
        if lineas and all(l.lstrip().startswith(("•", "- ")) for l in lineas):
            out += [f"<div style='margin:0 0 8px;padding:10px 12px;border-radius:10px;background:{CARTA};border:1px solid {LINEA}'>"
                    f"{E_(l.lstrip('•- ').strip())}</div>" for l in lineas]
        elif trozo.strip():
            out.append(f"<p style='margin:0 0 12px;white-space:pre-wrap'>{E_(trozo)}</p>")
    return "".join(out)


def _html(titulo: str, cuerpo: str, botones: list | None = None, ayuda: str = "", tipo: str = "aviso", canal: str = "") -> str:
    """Un correo sencillo con la plantilla común: el texto (respetando sus saltos de línea) y, si los hay, sus botones."""
    return _envolver(titulo, _parrafos(cuerpo), botones, ayuda, tipo, canal)


class Doc:
    """El contenido de un correo, una vez: sale como texto (legible tal cual) y como HTML visual para el móvil.
    `limite`: cuántos bloques de cada guion se enseñan en el HTML (None, todos); el texto va siempre completo."""

    def __init__(self, limite: int | None = None):
        self.t, self.h = [], []
        self.limite = limite
        self.recortado = False

    def crudo(self, h: str, t=None):
        """HTML hecho a mano y, aparte, su texto (una cadena o una lista de líneas)."""
        if h:
            self.h.append(h)
        if t:
            self.t += [t] if isinstance(t, str) else list(t)

    def titulo(self, t: str, icono: str = ""):
        self.t += ["", t.upper(), ""]
        self.h.append(f"<div style='font-size:18px;font-weight:800;color:{TINTA};margin:26px 0 10px;padding-bottom:6px;"
                      f"border-bottom:2px solid {LINEA}'>{E_(icono + ' ' if icono else '')}{E_(t)}</div>")

    def parrafo(self, t: str, fuerte: bool = False):
        if str(t).strip():
            self.t.append(str(t))
            estilo = "margin:6px 0;font-weight:700" if fuerte else "margin:6px 0"
            self.h.append(f"<p style='{estilo};white-space:pre-wrap'>{E_(str(t))}</p>")

    def lista(self, items: list, numerada_desde: int | None = None):
        items = [str(x) for x in items if str(x).strip()]
        if not items:
            return
        for i, x in enumerate(items):
            self.t.append((f"{numerada_desde + i}. " if numerada_desde is not None else "- ") + x)
        self.h.append("".join(
            f"<div style='margin:0 0 8px;padding:10px 12px;border-radius:10px;background:{CARTA};border:1px solid {LINEA};"
            f"white-space:pre-wrap'>" + (f"<b style='color:{TINTA}'>{numerada_desde + i}.</b> " if numerada_desde is not None else "")
            + f"{E_(x)}</div>" for i, x in enumerate(items)))

    def pre(self, t: str):
        if str(t).strip():
            self.t += [str(t).rstrip(), ""]
            self.h.append(f"<div style='white-space:pre-wrap;background:{CARTA};border:1px solid {LINEA};border-radius:10px;"
                          f"padding:12px 14px;margin:8px 0;font-size:15px;line-height:1.5'>{E_(str(t).rstrip())}</div>")

    def aviso_grande(self, t: str, nivel: str = "mal"):
        """Una franja que no se puede pasar por alto (un aviso grave que bloquea)."""
        fondo, borde, color = SUAVE[nivel]
        self.t.append(("⛔ " if nivel == "mal" else "⚠️ ") + t)
        self.h.append(_tabla(f"<tr><td style='padding:12px 14px;font-size:16px;font-weight:800;color:{color}'>"
                             f"{'⛔' if nivel == 'mal' else '⚠️'} {E_(t)}</td></tr>",
                             f"margin:10px 0;background:{fondo};border:2px solid {borde};border-radius:12px"))

    def texto(self) -> str:
        return "\n".join(self.t).strip()

    def html(self) -> str:
        return "".join(self.h)


# ── piezas visuales ─────────────────────────────────────────────────────────────────────────────────────────────────
def _fichas(fichas: list) -> str:
    """Cifras grandes en fichas que se recolocan solas en el móvil: [(valor, etiqueta, estado)] con estado
    «mal» (rojo, bloquea), «ojo» (ámbar), «bien» (verde) o «»."""
    out = []
    for valor, etiqueta, estado in fichas:
        fondo, borde, color = SUAVE.get(estado, SUAVE[""])
        out.append(f"<div style='display:inline-block;vertical-align:top;width:82px;margin:0 6px 8px 0;padding:10px 5px;"
                   f"border-radius:12px;background:{fondo};border:2px solid {borde};text-align:center'>"
                   f"<div style='font-size:26px;font-weight:800;line-height:1.1;color:{color}'>{E_(str(valor))}</div>"
                   f"<div style='font-size:13px;font-weight:700;color:{color};margin-top:4px'>{E_(etiqueta)}</div></div>")
    return f"<div style='margin:2px 0 8px'>{''.join(out)}</div>"


def _corte_movil(t: str, n: int | None = None) -> str:
    """Lo que se ve del título en el inicio de YouTube en el móvil (el mismo corte que hyt_texto.titulo)."""
    n = n or int(getattr(_cargar("hyt_texto"), "MOVIL", 40))
    t = str(t or "").strip()
    return t if len(t) <= n else (t[:n].rsplit(" ", 1)[0] or t[:n]) + "…"


def _mmss(minutos) -> str:
    try:
        s = int(round(float(minutos) * 60))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60}:{s % 60:02d}" if s else ""


def _vista_previa(canal: str, titulo: str, texto_mini: str, minutos=None, promesa: str = "", ancho: int = 320,
                  movil: str = "", fondo: str = "#7c2d12") -> str:
    """Cómo se vería en el inicio de YouTube: una miniatura 16:9 hecha con HTML (el texto de la miniatura en grande y la
    duración) y debajo el título cortado como en el móvil, el canal y la promesa."""
    alto = round(ancho * 9 / 16)
    visto = movil or _corte_movil(titulo)
    mini = E_(texto_mini or "(sin texto)")
    letra = 34 if len(texto_mini or "") <= 12 else 26 if len(texto_mini or "") <= 22 else 20
    dur = _mmss(minutos)
    caja = (f"<tr><td height='{alto}' bgcolor='#111827' style='height:{alto}px;background:#111827;background-image:linear-gradient(135deg,#0b1020 0%,{fondo} 100%);"
            f"border-radius:12px;text-align:center;vertical-align:middle;padding:0 14px'>"
            f"<div style='font-size:{letra}px;font-weight:900;line-height:1.05;color:#fde047;text-transform:uppercase;"
            f"letter-spacing:-0.5px'>{mini}</div>"
            + (f"<div style='text-align:right;margin-top:-4px'><span style='display:inline-block;margin-top:{max(alto // 2 - 40, 8)}px;"
               f"padding:1px 6px;border-radius:4px;background:#000000;color:#ffffff;font-size:12px;font-weight:700'>{dur}</span></div>"
               if dur else "") + "</td></tr>")
    inicial = E_((canal or "?")[:1].upper())
    pie = (f"<tr><td style='padding:10px 0 0'>" + _tabla(
        f"<tr><td width='40' valign='top' style='width:40px;vertical-align:top'><div style='width:32px;height:32px;line-height:32px;"
        f"border-radius:16px;background:{fondo};color:#ffffff;text-align:center;font-weight:800;font-size:15px'>{inicial}</div></td>"
        f"<td valign='top' style='vertical-align:top'><div style='font-size:16px;font-weight:700;line-height:1.3;color:{TINTA}'>{E_(visto)}</div>"
        f"<div style='font-size:13px;color:{TINTA2};margin-top:2px'>{E_(canal)}{' · ' + E_(dur) if dur else ''}</div></td></tr>")
        + "</td></tr>")
    extra = ""
    if visto != str(titulo or "").strip():
        extra += (f"<div style='font-size:13px;color:{TINTA2};margin-top:6px'>Título completo ({len(str(titulo))} caracteres): "
                  f"{E_(titulo)}</div>")
    if promesa:
        extra += f"<div style='font-size:14px;color:{TINTA};margin-top:6px'><b>Promesa:</b> {E_(promesa)}</div>"
    return _tabla(caja + pie, f"max-width:{ancho}px;margin:6px 0 14px", ancho="100%") + extra


def _tarjeta(contenido: str, borde: str = LINEA, izquierda: str = "", fondo: str = CARTA, margen: str = "0 0 12px") -> str:
    return _tabla(f"<tr><td style='padding:12px 14px'>{contenido}</td></tr>",
                  f"margin:{margen};background:{fondo};border:1px solid {borde};border-radius:12px"
                  + (f";border-left:6px solid {izquierda}" if izquierda else ""))


def _avisos(doc: Doc, avisos: list) -> None:
    """Avisos con su color e icono: los graves en rojo (bloquean), los demás en ámbar."""
    lineas, h = [], []
    avisos = sorted(avisos, key=lambda a: not (isinstance(a, dict) and a.get("grave")))   # los graves, primero
    for a in avisos:
        grave = bool(a.get("grave")) if isinstance(a, dict) else False
        t = str(a.get("texto", "")) if isinstance(a, dict) else str(a)
        fondo, borde, color = SUAVE["mal" if grave else "ojo"]
        lineas.append(("⛔ " if grave else "⚠️ ") + t)
        h.append(_tabla(f"<tr><td width='34' valign='top' style='width:34px;padding:10px 0 10px 12px;font-size:18px;vertical-align:top'>"
                        f"{'⛔' if grave else '⚠️'}</td><td style='padding:10px 12px 10px 4px;font-size:15px;color:{color}'>"
                        f"<b>{'Grave' if grave else 'Aviso'}:</b> {E_(t)}</td></tr>",
                        f"margin:0 0 8px;background:{fondo};border:1px solid {borde};border-radius:10px"))
    if not avisos:
        lineas.append("Sin avisos.")
        h.append(_tarjeta(f"<span style='color:{SUAVE['bien'][2]};font-weight:700'>✓ Sin avisos.</span>", SUAVE["bien"][1], fondo=SUAVE["bien"][0]))
    doc.crudo("".join(h), ["- " + l for l in lineas])


def _cambios_editor(doc: Doc, cambios: list) -> None:
    """Los cambios que propone el editor jefe (cierre.json), frase por frase, como «antes → después»."""
    h, t = [], []
    for c in cambios:
        if not isinstance(c, dict):
            continue
        bloque, antes, despues, motivo = (str(c.get(k) or "") for k in ("bloque", "frase", "quedaria", "motivo"))
        t.append(f"- [{bloque}] «{antes}» → «{despues}»" + (f" ({motivo})" if motivo else ""))
        malo, bueno = SUAVE["mal"], SUAVE["bien"]
        h.append(_tarjeta(
            (_chip(_nombre_bloque(bloque), "#ede9fe", "#3b0764") if bloque else "")
            + (f"<div style='font-size:14px;color:{TINTA2};margin:0 0 8px'>{E_(motivo)}</div>" if motivo else "")
            + f"<div style='padding:8px 10px;border-radius:8px;background:{malo[0]};color:{malo[2]};font-size:15px'>"
              f"<b>Antes:</b> <span style='text-decoration:line-through'>{E_(antes)}</span></div>"
            + f"<div style='text-align:center;font-size:18px;font-weight:800;color:{TINTA};line-height:1.4'>↓</div>"
            + f"<div style='padding:8px 10px;border-radius:8px;background:{bueno[0]};color:{bueno[2]};font-size:15px'>"
              f"<b>Después:</b> {E_(despues or '(quitarla)')}</div>"))
    doc.crudo("".join(h), t)


def _estado_dato(x: dict) -> str:
    return x.get("estado", "pendiente") + (f" → {x['valor']}" if x.get("valor") else "")


def _datos_lineas(datos: list, solo_pendientes: bool = False) -> list:
    out = []
    for x in datos or []:
        if not isinstance(x, dict) or (solo_pendientes and x.get("estado", "pendiente") != "pendiente"):
            continue
        out.append(f"{x.get('dato', '')} [{_estado_dato(x)}]" + (f"\nFrase: {x['frase']}" if x.get("frase") else "")
                   + (f"\nFuente: {x['fuente']}" if x.get("fuente") else ""))
    return out


def _datos_tabla(doc: Doc, datos: list, solo_pendientes: bool = False) -> None:
    """Los datos en una tabla (dato y su estado, frase, fuente; la fuente con enlace si es una URL)."""
    datos = [x for x in datos or [] if isinstance(x, dict) and not (solo_pendientes and x.get("estado", "pendiente") != "pendiente")]
    if not datos:
        doc.lista(["Ninguno."])
        return
    th = f"padding:8px 8px;text-align:left;font-size:13px;font-weight:800;color:{TINTA};background:#e6dfd1"
    filas = [f"<tr><th style='{th}'>Dato</th><th style='{th}'>Frase</th><th style='{th}'>Fuente</th></tr>"]
    for x in datos:
        estado = x.get("estado", "pendiente")
        nivel = {"pendiente": "ojo", "verificado": "bien", "corregido": "bien", "eliminado": "mal"}.get(estado, "")
        f = str(x.get("fuente") or "")
        fuente = _enlace(f, _dominio(f)) if _es_url(f) else E_(f or "—")
        td = f"padding:8px;vertical-align:top;border-top:1px solid {LINEA};font-size:14px;line-height:1.4;color:{TINTA}"
        filas.append(f"<tr><td style='{td}'><b>{E_(str(x.get('dato', '')))}</b><br>"
                     + _chip(_estado_dato(x), SUAVE[nivel][0], SUAVE[nivel][2], SUAVE[nivel][1])
                     + f"</td><td style='{td}'>{E_(str(x.get('frase') or '—'))}</td><td style='{td};word-break:break-word'>{fuente}</td></tr>")
    doc.crudo(_tabla("".join(filas), f"margin:4px 0 12px;background:{CARTA};border:1px solid {LINEA};border-radius:10px;overflow:hidden"),
              ["- " + l for l in _datos_lineas(datos)])


# ── el guion por bloques ────────────────────────────────────────────────────────────────────────────────────────────
NOMBRES_BLOQUE = {"intro": "Intro", "conexion": "Conexión", "cierre": "Cierre"}


def _nombre_bloque(b: str) -> str:
    b = str(b or "").strip()
    if b in NOMBRES_BLOQUE:
        return NOMBRES_BLOQUE[b]
    return re.sub(r"-(\d+)$", r" \1", b).replace("-", " ").capitalize() or "Guion"


def _frases_por_bloque(d: Path) -> list:
    """[(bloque, [(n, frase)])]: del guion numerado tal como se presentó, o numerando guion.md."""
    numerado = _lee(d / "guion-numerado.md")
    out: list = []
    if numerado.strip():
        for l in numerado.splitlines():
            m = re.match(r"^##\s+(.+?)\s*$", l)
            n = re.match(r"^\s*(\d+)\.\s+(.*\S)", l)
            if m:
                out.append((_cargar("hyt_texto").plano(m.group(1)).replace(" ", "-"), []))
            elif n:
                if not out:
                    out.append(("", []))
                out[-1][1].append((int(n.group(1)), n.group(2)))
        if any(fs for _, fs in out):
            return out
    for n, bloque, frase in _cargar("hyt_texto").numerar(_lee(d / "guion.md")):
        if not out or out[-1][0] != bloque:
            out.append((bloque, []))
        out[-1][1].append((n, frase))
    return out


def _presupuestos(d: Path, slug: str) -> dict:
    """Palabras presupuestadas por bloque (escaleta.json); la intro, el máximo del canal (75 por defecto)."""
    esc = _json(d / "escaleta.json") or {}
    pres = {str(b.get("id")): int(b.get("palabras") or 0) for b in esc.get("bloques") or [] if isinstance(b, dict) and b.get("palabras")}
    try:
        tope = int(_cargar("hyt_reglas").reglas(C.leer(slug)).get("intro_max_palabras") or 75)
    except Exception:   # noqa: BLE001
        tope = 75
    pres["intro"] = tope
    return pres


def _barra(escritas: int, presupuesto: int, estado: str = "") -> tuple:
    """(html de la barra, estado): verde si está cerca de lo presupuestado, ámbar si se queda corta, rojo si se pasa
    (o el `estado` que se le dé)."""
    r = escritas / presupuesto if presupuesto else 0
    estado = estado or ("mal" if r > 1.1 else "ojo" if r < 0.8 else "bien")
    color = {"mal": ROJO, "ojo": "#d97706", "bien": "#16a34a"}[estado]
    pct = max(2, min(100, round(r * 100)))
    resto = f"<td style='font-size:0;line-height:0'>&nbsp;</td>" if pct < 100 else ""
    return (_tabla(f"<tr><td width='{pct}%' bgcolor='{color}' style='width:{pct}%;height:10px;background:{color};border-radius:5px;"
                   f"font-size:0;line-height:0'>&nbsp;</td>{resto}</tr>", f"margin:6px 0 10px;background:#ddd5c6;border-radius:5px"),
            estado)


def _guion(doc: Doc, d: Path, slug: str, acento: str = "#1e3a8a") -> None:
    """Cada bloque en su tarjeta, con sus frases numeradas y una barra de palabras escritas frente a las presupuestadas.
    Intro y cierre, destacados. Con `doc.limite`, el HTML solo lleva los primeros bloques (el texto, todos)."""
    T = _cargar("hyt_texto")
    pres = _presupuestos(d, slug)
    bloques = _frases_por_bloque(d)
    h, t = [], []
    for i, (bloque, frases) in enumerate(bloques):
        escritas = sum(len(T.palabras(f)) for _, f in frases)
        p = pres.get(bloque, 0)
        nombre = _nombre_bloque(bloque)
        t += ["", f"## {nombre}" + (f" ({escritas}/{p} palabras)" if p else f" ({escritas} palabras)")] + [f"{n}. {f}" for n, f in frases]
        if doc.limite is not None and i >= doc.limite:
            doc.recortado = True
            continue
        barra, estado = _barra(escritas, p) if p else ("", "")
        color_cifra = SUAVE.get(estado, SUAVE[""])[2]
        destacado = bloque in ("intro", "cierre")
        cifra = f"{escritas} / {p} palabras" if p else f"{escritas} palabras"
        cab = _tabla(f"<tr><td style='font-size:17px;font-weight:800;color:{TINTA}'>{'★ ' if destacado else ''}{E_(nombre)}</td>"
                     f"<td align='right' style='text-align:right;font-size:13px;font-weight:800;color:{color_cifra};white-space:nowrap'>"
                     f"{E_(cifra)}</td></tr>")
        filas = "".join(f"<div style='margin:0 0 7px;font-size:15px;line-height:1.5;color:{TINTA}'>"
                        f"<span style='display:inline-block;min-width:28px;font-weight:800;color:{acento}'>{n}</span>{E_(f)}</div>"
                        for n, f in frases)
        h.append(_tarjeta(cab + (barra or "<div style='height:8px'></div>") + filas, LINEA, acento if destacado else "#b9ae9a",
                          "#fff7e6" if destacado else CARTA))
    if doc.recortado:
        url = _panel_url()
        quedan = len(bloques) - (doc.limite or 0)
        h.append(_tarjeta(f"<b>Faltan {quedan} bloque(s) de este guion</b> para que el correo no se corte. "
                          + (f"Está entero en el panel: {_enlace(url)}" if url else "Está entero en la pestaña YouTube del panel."),
                          SUAVE["ojo"][1], fondo=SUAVE["ojo"][0]))
    doc.crudo("".join(h), t + [""])


def _panel_url() -> str:
    return str((B.leer(B.home() / "yt.json", {}) or {}).get("panel_url") or "").strip()


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
    lineas = [l for l in lineas if l]
    filas = "".join(f"<div style='margin:0 0 5px;font-size:15px'><b>{E_(l.split(':', 1)[0])}:</b>{E_(l.split(':', 1)[1])}</div>"
                    for l in lineas)
    doc.crudo(_tarjeta(filas) if filas else "", ["- " + l for l in lineas])


def _cambios(d: Path) -> dict | None:
    """Qué frases han cambiado respecto a la última versión que vio una persona. Cada vez que se monta el paquete se
    guarda el guion tal como se presenta; los retoques internos de antes de la primera revisión no son «cambios»."""
    vistos = sorted((d / ".estado").glob("guion-presentado-*.md"), key=lambda f: int(re.sub(r"\D", "", f.stem) or 0)) \
        if (d / ".estado").is_dir() else []
    if len(vistos) < 2:
        return None
    c = _cargar("hyt_texto").cambios(_lee(vistos[-2]), _lee(vistos[-1]))
    return c if c["nuevas"] or c["quitadas"] else None


def _medidas(d: Path, paq: dict) -> dict:
    """Las cifras de un guion: palabras, minutos, avisos (graves y no), nota, datos por verificar y externos,
    veredicto y cambios del editor jefe."""
    g, rev = paq.get("guion") or {}, paq.get("revision") or {}
    avisos = [a for a in rev.get("avisos") or [] if isinstance(a, dict)]
    graves = int(rev.get("graves") or sum(1 for a in avisos if a.get("grave")))
    datos = [x for x in (_json(d / "datos.json") or {}).get("datos") or paq.get("datos") or [] if isinstance(x, dict)]
    cierre = _json(d / "cierre.json") or {}
    palabras = g.get("palabras")
    if not palabras and (d / "guion.md").exists():
        palabras = _cargar("hyt_texto").medidas(_lee(d / "guion.md"))["palabras"]
    return {"palabras": palabras or 0, "minutos": g.get("minutos") or 0, "graves": graves, "avisos": max(len(avisos) - graves, 0),
            "lista_avisos": avisos, "nota": rev.get("nota", "—"), "datos": datos,
            "pendientes": sum(1 for x in datos if x.get("estado", "pendiente") == "pendiente"),
            "externos": sum(1 for x in datos if _externo(x)),
            "veredicto": cierre.get("veredicto") or (paq.get("editor") or {}).get("veredicto") or "—",
            "cambios": [c for c in cierre.get("cambios") or [] if isinstance(c, dict)],
            "notas": [str(n) for n in (cierre.get("notas") or (paq.get("editor") or {}).get("notas") or [])]}


def _min(m) -> str:
    try:
        return f"{float(m):.1f}".replace(".", ",").replace(",0", "")
    except (TypeError, ValueError):
        return "—"


def _c_revision(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    paq = (_json(d / "paquete.json") if d else None) or {}
    if not d or not paq:
        doc.pre(p.get("texto", ""))
        return
    m = _medidas(d, paq)
    doc.crudo(_fichas([(m["palabras"], "palabras", ""), (_min(m["minutos"]), "minutos", ""),
                       (m["nota"], "nota", "mal" if m["graves"] else ""),
                       (m["graves"], "avisos graves", "mal" if m["graves"] else "bien"),
                       (m["avisos"], "avisos", "ojo" if m["avisos"] else "bien"),
                       (m["pendientes"], "datos por verificar", "ojo" if m["pendientes"] else "bien")]),
              f"{m['palabras']} palabras · {_min(m['minutos'])} min · nota {m['nota']} · {m['graves']} aviso(s) grave(s) · "
              f"{m['avisos']} aviso(s) · {m['pendientes']} dato(s) por verificar")
    if int(p.get("ronda") or 0) or (d / ".estado").is_dir():
        c = _cambios(d)
        if c:
            doc.titulo(f"Lo que ha cambiado desde la versión anterior ({c['pct']} % de las frases)", "🔁")
            doc.lista([f"Frase {n}: {f}" for n, f in c["nuevas"][:40]]
                      + [f"Quitada: {f}" for f in c["quitadas"][:40] if not any(f == x for _, x in c["nuevas"])])
    doc.titulo("Título y miniatura", "▶")
    mini = paq.get("miniatura") if isinstance(paq.get("miniatura"), dict) else {}
    doc.crudo(_vista_previa(_nombre_canal(p["canal"]), paq.get("titulo") or "(sin título elegido)", mini.get("texto", ""),
                            m["minutos"], paq.get("promesa", ""), fondo=TIPOS.get(p["tipo"], TIPOS["revision"])[1]),
              ["Título: " + (paq.get("titulo") or "(sin título elegido)")] + ([f"Promesa: {paq['promesa']}"] if paq.get("promesa") else []))
    _miniatura(doc, paq.get("miniatura"))
    doc.titulo(f"Revisión por código: nota {m['nota']}", "🧭")
    _avisos(doc, m["lista_avisos"])
    if m["cambios"]:
        doc.titulo(f"Cambios que propone el editor jefe ({len(m['cambios'])})", "✏️")
        _cambios_editor(doc, m["cambios"])
    if m["notas"] or m["veredicto"] != "—":
        doc.titulo("Notas del editor" + (f" ({m['veredicto']})" if m["veredicto"] != "—" else ""), "🗒")
        doc.lista(m["notas"])
    doc.titulo("Guion" + (f" ({m['palabras']} palabras, unos {_min(m['minutos'])} min)" if m["palabras"] else ""), "📝")
    doc.parrafo("Cada frase lleva su número: para pedir un cambio puedes decir «frase 14: yo diría…».")
    _guion(doc, d, p["canal"], TIPOS.get(p["tipo"], TIPOS["revision"])[1])
    doc.titulo("Descripción", "📄")
    doc.pre(_lee(d / "descripcion.md") or "(sin descripción)")
    if m["datos"]:
        doc.titulo(f"Datos ({len(m['datos'])})", "🔎")
        _datos_tabla(doc, m["datos"])


def _tema_linea(x: dict) -> str:
    return (f"[{x.get('pilar', '')}] {x.get('titulo', '')}" + (f"\n{x['resumen']}" if x.get("resumen") else "")
            + (f"\nNota: {x['nota']}" if x.get("nota") not in (None, "") else "")
            + (f" · «{x['frase']}»" if x.get("frase") else "")
            + (f"\nParecido a: {x['parecido_a']}" if x.get("parecido_a") else ""))


def _temas_tarjetas(doc: Doc, temas: list, desde: int, suplente: bool = False) -> None:
    h = []
    for i, x in enumerate(temas):
        n = desde + i
        num = (f"<div style='width:38px;height:38px;line-height:38px;border-radius:19px;text-align:center;font-size:18px;font-weight:900;"
               f"background:{'#e2d9c8' if suplente else '#c2410c'};color:{TINTA if suplente else '#ffffff'}'>{n}</div>")
        cuerpo = (_chip(x.get("pilar", "") or "sin pilar", "#ffedd5", "#7c2d12", "#f5b682")
                  + (_chip(f"Nota {x['nota']}", "#f3efe7", TINTA, LINEA) if x.get("nota") not in (None, "") else "")
                  + f"<div style='font-size:17px;font-weight:800;line-height:1.3;color:{TINTA};margin:2px 0 4px'>{E_(str(x.get('titulo', '')))}</div>"
                  + (f"<div style='font-size:15px;color:{TINTA};margin:0 0 6px'>{E_(str(x['resumen']))}</div>" if x.get("resumen") else "")
                  + (f"<div style='font-size:15px;font-style:italic;color:{TINTA2};margin:0 0 4px'>«{E_(str(x['frase']))}»</div>" if x.get("frase") else "")
                  + (f"<div style='font-size:14px;font-weight:700;color:{SUAVE['ojo'][2]};background:{SUAVE['ojo'][0]};padding:6px 8px;"
                     f"border-radius:8px;margin-top:6px'>⚠️ Parecido a: {E_(str(x['parecido_a']))}</div>" if x.get("parecido_a") else ""))
        h.append(_tarjeta(_tabla(f"<tr><td width='50' valign='top' style='width:50px;vertical-align:top'>{num}</td>"
                                 f"<td valign='top' style='vertical-align:top'>{cuerpo}</td></tr>"), LINEA, "" if suplente else "#f97316"))
    doc.crudo("".join(h), [f"{desde + i}. {_tema_linea(x)}" for i, x in enumerate(temas)])


def _c_temas(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    t = (_json(d / "temas.json") if d else None) or {}
    temas = [x for x in t.get("temas") or [] if isinstance(x, dict)]
    if not temas:
        doc.pre(p.get("texto", ""))
        return
    supl = [x for x in t.get("suplentes") or [] if isinstance(x, dict)]
    avisos = [str(a) for a in t.get("avisos") or []]
    doc.crudo(_fichas([(len(temas), "propuestos", ""), (len(supl), "suplentes", ""), (len(avisos), "avisos", "ojo" if avisos else "bien")]))
    doc.titulo(f"Temas propuestos ({len(temas)})", "💡")
    _temas_tarjetas(doc, temas, 1)
    if supl:
        doc.titulo("Suplentes", "🪑")
        _temas_tarjetas(doc, supl, len(temas) + 1, suplente=True)
    if avisos:
        doc.titulo("Avisos", "⚠️")
        _avisos(doc, avisos)


def _c_titulo(p: dict, doc: Doc) -> dict:
    d = _carpeta(p)
    op = (_json(d / "opciones.json") if d else None) or {}
    tits = [x for x in op.get("titulos") or [] if isinstance(x, dict)]
    if not tits:
        doc.pre(p.get("texto", ""))
        return {}
    rec = op.get("recomendacion") or {}
    brief = op.get("brief") or {}
    minis = [x for x in op.get("miniaturas") or [] if isinstance(x, dict)]
    canal = _nombre_canal(p["canal"])
    try:
        tope = int(_cargar("hyt_reglas").reglas(C.leer(p["canal"])).get("titulo_max") or 55)
    except Exception:   # noqa: BLE001
        tope = 55
    if brief.get("promesa"):
        doc.parrafo(f"Promesa del vídeo: {brief['promesa']}")
    if rec.get("titulo") or rec.get("miniatura"):
        doc.parrafo(f"Recomendación: título {rec.get('titulo', '—')} con la miniatura {rec.get('miniatura', '—')}"
                    + (f" (alternativa: título {rec['titulo_alternativo']})" if rec.get("titulo_alternativo") else ""), fuerte=True)
        t_rec = next((x for x in tits if str(x.get("n")) == str(rec.get("titulo"))), None)
        m_rec = next((x for x in minis if str(x.get("n")) == str(rec.get("miniatura"))), None)
        if t_rec:
            doc.crudo(_vista_previa(canal, t_rec.get("texto", ""), (m_rec or {}).get("texto", ""), None, "",
                                    movil=t_rec.get("movil", ""), fondo="#9a3412"))
    doc.titulo("Títulos", "🏷")
    h = []
    for x in tits:
        texto = str(x.get("texto", ""))
        n_car = int(x.get("caracteres") or len(texto))
        es_rec = str(x.get("n")) == str(rec.get("titulo"))
        movil_n = int(getattr(_cargar("hyt_texto"), "MOVIL", 40))   # entero en el móvil, verde; se corta, ámbar; largo, rojo
        barra, _ = _barra(n_car, tope, "bien" if n_car <= movil_n else "ojo" if n_car < tope else "mal")
        h.append(_tarjeta(
            (_chip("★ Recomendado", SUAVE["bien"][0], SUAVE["bien"][2], SUAVE["bien"][1]) if es_rec else "")
            + f"<div style='font-size:18px;font-weight:800;line-height:1.3;color:{TINTA}'><span style='color:#c2410c'>{E_(str(x.get('n', '')))}.</span> "
              f"{E_(texto)}</div>"
            + f"<div style='font-size:13px;font-weight:700;color:{TINTA2};margin-top:6px'>{n_car} de {tope} caracteres</div>" + barra
            + f"<div style='font-size:14px;color:{TINTA}'><b>En el móvil:</b> «{E_(str(x.get('movil') or _corte_movil(texto)))}»</div>"
            + "".join(f"<div style='margin-top:6px;font-size:14px;font-weight:700;color:{SUAVE['ojo'][2]}'>⚠️ {E_(str(a))}</div>"
                      for a in x.get("avisos") or []),
            SUAVE["bien"][1] if es_rec else LINEA, VERDE if es_rec else ""))
    doc.crudo("".join(h), [f"{int(tits[0].get('n') or 1) + i}. {x.get('texto', '')}\n{x.get('caracteres', len(str(x.get('texto', ''))))} "
                           f"caracteres · en el móvil: «{x.get('movil', '')}»" + ("\n" + "; ".join(str(a) for a in x["avisos"]) if x.get("avisos") else "")
                           for i, x in enumerate(tits)])
    doc.titulo("Ideas de miniatura", "🖼")
    for m in minis:
        es_rec = str(m.get("n")) == str(rec.get("miniatura"))
        doc.parrafo(f"Miniatura {m.get('n', '?')}" + (f": {m['concepto']}" if m.get("concepto") else "") + (" ★ recomendada" if es_rec else ""), fuerte=True)
        doc.crudo(_mini_sola(m.get("texto", "")))
        _miniatura(doc, m)
    return rec


def _mini_sola(texto: str, ancho: int = 240) -> str:
    """Solo la miniatura 16:9 (para comparar ideas de miniatura sin repetir el título)."""
    alto = round(ancho * 9 / 16)
    letra = 28 if len(texto or "") <= 12 else 22 if len(texto or "") <= 22 else 17
    return _tabla(f"<tr><td height='{alto}' bgcolor='#111827' style='height:{alto}px;background:#111827;"
                  f"background-image:linear-gradient(135deg,#0b1020 0%,#9a3412 100%);border-radius:10px;text-align:center;vertical-align:middle;padding:0 12px'>"
                  f"<div style='font-size:{letra}px;font-weight:900;line-height:1.05;color:#fde047;text-transform:uppercase'>{E_(texto or '(sin texto)')}</div>"
                  f"</td></tr>", f"max-width:{ancho}px;margin:4px 0 8px")


def _c_voz(p: dict, doc: Doc) -> None:
    d = _carpeta(p)
    doc.pre((_lee(d / "perfil-voz.md") if d else "") or p.get("texto", ""))


def _c_datos(p: dict, doc: Doc) -> None:
    PU = _cargar("hyt_puertas")
    datos = PU.datos_de(p)
    pendientes = [x for x in datos if x.get("estado", "pendiente") == "pendiente"]
    url = _panel_url()
    doc.crudo(_fichas([(len(pendientes), "por verificar", "mal" if pendientes else "bien"), (len(datos), "datos en total", ""),
                       (sum(1 for x in datos if _externo(x)), "con fuente externa", "")]))
    doc.parrafo(f"Hay {len(pendientes)} dato(s) por verificar, uno a uno: verificado, corregido o eliminado.", fuerte=True)
    doc.parrafo("Los datos no se verifican por correo: se hace " + (f"en el panel: {url}" if url else "en la pestaña YouTube del panel")
                + ". Cuando no quede ninguno pendiente, allí mismo se da la puerta por verificada.")
    if url:
        doc.crudo(_boton_web(url, "🔎 Verificar en el panel", "#0f766e"))
    doc.titulo("Datos pendientes", "🔎")
    _datos_tabla(doc, datos, solo_pendientes=True)


# ── elegir entre dos versiones del mismo guion (A, propia; B, investigada) ──────────────────────────────────────────
def _gemelos(p: dict) -> list:
    """[{letra, version, encargo, carpeta}] de una puerta elegir-version."""
    E = _cargar("hyt_encargos")
    out = []
    for g in p.get("gemelos") or []:
        if isinstance(g, dict) and g.get("encargo") and g.get("letra"):
            out.append({**g, "letra": str(g["letra"]).upper(), "carpeta": E.carpeta(p["canal"], g["encargo"])})
    return out


ICONO_FUENTE = {"youtube": "▶", "doc": "📄", "articulo": "📰", "noticia": "🗞"}


def _investigacion(doc: Doc, d: Path) -> None:
    inv = _json(d / "investigacion.json") or {}
    fuentes = [f for f in inv.get("fuentes") or [] if isinstance(f, dict)]
    huecos = [str(h) for h in inv.get("huecos_cubiertos") or [] if str(h).strip()]
    hallazgos = inv.get("hallazgos") or []
    sin_comprobar = sum(1 for f in fuentes if f.get("comprobada") is False)
    doc.crudo(_fichas([(len(fuentes), "fuentes", ""), (len(huecos), "huecos cubiertos", "bien" if huecos else ""),
                       (len(hallazgos), "hallazgos", "")]
                      + ([(sin_comprobar, "fuentes sin comprobar", "ojo")] if sin_comprobar else [])))
    if fuentes:
        h, t = [], []
        for f in fuentes:
            url, tit = str(f.get("url") or ""), str(f.get("titulo") or f.get("url") or "")
            meta = " · ".join(str(x) for x in (f.get("autor_o_canal"), f.get("fecha"), f.get("tipo")) if x)
            dudosa = f.get("comprobada") is False
            t.append(f"- [{f.get('id', '')}] {tit}" + (f" ({meta})" if meta else "") + (" [sin comprobar]" if dudosa else "")
                     + (f"\n  {url}" if url else ""))
            h.append(_tabla(f"<tr><td width='30' valign='top' style='width:30px;padding:9px 0 9px 10px;font-size:17px;vertical-align:top'>"
                            f"{ICONO_FUENTE.get(str(f.get('tipo')), '🔗')}</td><td style='padding:9px 10px 9px 4px;font-size:15px;line-height:1.4'>"
                            + (_enlace(url, tit) if _es_url(url) else f"<b>{E_(tit)}</b>")
                            + (f"<div style='font-size:13px;color:{TINTA2};margin-top:2px'>{E_(meta)}</div>" if meta else "")
                            + (_chip("sin comprobar", *(SUAVE["ojo"][i] for i in (0, 2, 1))) if dudosa else "") + "</td></tr>",
                            f"margin:0 0 8px;background:{CARTA};border:1px solid {LINEA};border-radius:10px"))
        doc.parrafo("Fuentes consultadas:", fuerte=True)
        doc.crudo("".join(h), t)
    if huecos:
        doc.parrafo("Huecos que cubre:", fuerte=True)
        doc.crudo("".join(f"<div style='margin:0 0 6px;font-size:15px;color:{TINTA}'><b style='color:{VERDE}'>✓</b> {E_(x)}</div>" for x in huecos),
                  ["✓ " + x for x in huecos])
    sin = [str(h) for h in inv.get("huecos_sin_cubrir") or [] if str(h).strip()]
    if sin:
        doc.parrafo("Huecos que sigue sin cubrir:", fuerte=True)
        doc.crudo("".join(f"<div style='margin:0 0 6px;font-size:15px;color:{SUAVE['ojo'][2]}'><b>○</b> {E_(x)}</div>" for x in sin),
                  ["○ " + x for x in sin])
    nombres = {str(f.get("id")): str(f.get("autor_o_canal") or f.get("titulo") or f.get("id")) for f in fuentes}
    urls = {str(f.get("id")): str(f.get("url") or "") for f in fuentes}
    h, t = [], []
    for x in hallazgos[:6]:
        if isinstance(x, dict):
            dicho = str(x.get("dicho") or x.get("texto") or x.get("cita") or x.get("dato") or "")
            fu = str(x.get("fuente") or "")
            if not dicho:
                continue
            if _es_url(x.get("url")) and not _es_url(urls.get(fu)):
                urls[fu] = str(x["url"])
            t.append(dicho + (f" [{nombres.get(fu, fu)}]" if fu else "") + (" (una sola fuente)" if x.get("una_fuente") else "")
                     + (" (sin comprobar)" if x.get("comprobado") is False else ""))
            h.append(_tarjeta(f"<div style='font-size:15px;color:{TINTA}'>{E_(dicho)}</div>"
                              + (f"<div style='font-size:13px;color:{TINTA2};margin-top:4px'>"
                                 + (_enlace(urls[fu], nombres.get(fu, fu)) if _es_url(urls.get(fu)) else E_(nombres.get(fu, fu)))
                                 + (" · " + E_(str(x["aporta"])) if x.get("aporta") else "") + "</div>" if fu else "")
                              + (_chip("una sola fuente", *(SUAVE["ojo"][i] for i in (0, 2, 1))) if x.get("una_fuente") else "")
                              + (_chip("cita sin comprobar", *(SUAVE["ojo"][i] for i in (0, 2, 1))) if x.get("comprobado") is False else ""),
                              margen="0 0 8px"))
        elif str(x).strip():
            t.append(str(x))
            h.append(_tarjeta(E_(str(x)), margen="0 0 8px"))
    if t:
        doc.parrafo("Hallazgos" + (f" (los {len(t)} primeros de {len(hallazgos)})" if len(hallazgos) > len(t) else "") + ":", fuerte=True)
        doc.crudo("".join(h), ["- " + x for x in t])
    dudosos = [x for x in inv.get("dudosos") or [] if isinstance(x, dict)]
    if dudosos:
        doc.parrafo(f"Dudosos: las fuentes no coinciden ({len(dudosos)}); lo decide una persona.", fuerte=True)
        for x in dudosos[:5]:
            vs = [v for v in x.get("versiones") or [] if isinstance(v, dict)]
            doc.crudo(_tarjeta(f"<div style='font-weight:800;color:{SUAVE['ojo'][2]}'>⚠️ {E_(str(x.get('dato', '')))}</div>"
                               + "".join(f"<div style='font-size:14px;margin-top:4px'>{E_(str(v.get('valor', '')))} · "
                                         + (_enlace(v['fuente'], _dominio(v['fuente'])) if _es_url(v.get("fuente")) else E_(str(v.get("fuente", ""))))
                                         + "</div>" for v in vs), SUAVE["ojo"][1], fondo=SUAVE["ojo"][0], margen="0 0 8px"),
                      [f"⚠️ {x.get('dato', '')}: " + "; ".join(f"{v.get('valor', '')} ({v.get('fuente', '')})" for v in vs)])


def _c_version(p: dict, doc: Doc, cola: Doc) -> None:
    """Comparación A frente a B: tabla con las cifras, lo que aportó la investigación y, en `cola` (tras los botones),
    los dos guiones por bloques."""
    gem = _gemelos(p)
    if len(gem) < 2:
        doc.pre(p.get("texto", ""))
        return
    canal = _nombre_canal(p["canal"])
    datos = [(g, (_json(g["carpeta"] / "paquete.json") or {})) for g in gem]
    med = [(g, paq, _medidas(g["carpeta"], paq)) for g, paq in datos]
    doc.parrafo("Hay dos versiones del mismo vídeo: " + " y ".join(
        f"{g['letra']} ({g.get('version', '')})" for g in gem) + ". Elige con cuál se sigue; la otra se descarta.", fuerte=True)
    # la vista previa: una si las dos llevan el mismo título y miniatura; si no, una por versión
    vistas = []
    for g, paq, m in med:
        mini = paq.get("miniatura") if isinstance(paq.get("miniatura"), dict) else {}
        vistas.append((g, paq.get("titulo") or "", mini.get("texto", ""), m["minutos"], paq.get("promesa", "")))
    if len({(v[1], v[2]) for v in vistas}) == 1:
        doc.crudo(_vista_previa(canal, vistas[0][1], vistas[0][2], vistas[0][3], vistas[0][4], fondo="#86198f"),
                  [f"Título: {vistas[0][1]}"] + ([f"Promesa: {vistas[0][4]}"] if vistas[0][4] else []))
    else:
        doc.crudo("".join(f"<div style='display:inline-block;vertical-align:top;width:100%;max-width:280px;margin:0 12px 6px 0'>"
                          f"<div style='font-weight:800;margin-bottom:4px'>Versión {E_(g['letra'])}</div>"
                          + _vista_previa(canal, t, mt, mi, pr, ancho=280, fondo="#86198f") + "</div>" for g, t, mt, mi, pr in vistas),
                  [f"Título {g['letra']}: {t}" for g, t, _, _, _ in vistas])
    # la tabla A frente a B
    filas = [("Palabras", lambda m: (m["palabras"], "")), ("Minutos", lambda m: (_min(m["minutos"]), "")),
             ("Nota de la revisión", lambda m: (m["nota"], "")),
             ("Avisos graves", lambda m: (m["graves"], "mal" if m["graves"] else "bien")),
             ("Avisos", lambda m: (m["avisos"], "ojo" if m["avisos"] else "bien")),
             ("Datos por verificar", lambda m: (f"{m['pendientes']} ({m['externos']} externos)" if m["externos"] else m["pendientes"],
                                                "ojo" if m["pendientes"] else "bien")),
             ("Veredicto del editor jefe", lambda m: (m["veredicto"], "bien" if m["veredicto"] == "APROBADO" else "ojo" if m["veredicto"] != "—" else "")),
             ("Cambios del editor jefe", lambda m: (len(m["cambios"]), "ojo" if m["cambios"] else "bien"))]
    colores = ["#1e40af", "#86198f", "#0f766e", "#9a3412"]
    th = "padding:10px 8px;font-size:15px;font-weight:900;color:#ffffff;text-align:center"
    cab = (f"<tr><th style='padding:10px 8px;font-size:13px;text-align:left;color:{TINTA};background:#e6dfd1'>&nbsp;</th>"
           + "".join(f"<th bgcolor='{colores[i % 4]}' style='{th};background:{colores[i % 4]}'>{E_(g['letra'])}<div style='font-size:12px;font-weight:700'>"
                     f"{E_(g.get('version', ''))}</div></th>" for i, (g, _, _) in enumerate(med)) + "</tr>")
    cuerpo, texto = [], ["", "A FRENTE A B", ""]
    for etiqueta, f in filas:
        celdas = []
        for g, _, m in med:
            valor, estado = f(m)
            fondo, _, color = SUAVE.get(estado, SUAVE[""])
            celdas.append(f"<td style='padding:9px 8px;text-align:center;border-top:1px solid {LINEA};background:{fondo};color:{color};"
                          f"font-size:17px;font-weight:800'>{E_(str(valor))}</td>")
        cuerpo.append(f"<tr><td style='padding:9px 8px;border-top:1px solid {LINEA};font-size:14px;font-weight:700;color:{TINTA}'>"
                      f"{E_(etiqueta)}</td>{''.join(celdas)}</tr>")
        texto.append(f"{etiqueta}: " + " · ".join(f"{g['letra']} {f(m)[0]}" for g, _, m in med))
    doc.titulo("A frente a B", "⚖️")
    doc.crudo(_tabla(cab + "".join(cuerpo), f"margin:4px 0 10px;background:{CARTA};border:1px solid {LINEA};border-radius:12px;overflow:hidden"),
              texto[3:])
    for g, _, m in med:
        if m["graves"]:
            doc.aviso_grande(f"La versión {g['letra']} tiene {m['graves']} aviso(s) grave(s): no se puede elegir hasta rehacerla.")
    inv = next((g for g in gem if (g["carpeta"] / "investigacion.json").exists()), None)
    if inv:
        doc.titulo(f"Qué aportó la investigación (versión {inv['letra']})", "🔬")
        _investigacion(doc, inv["carpeta"])
        externos = [x for x in next(m for g, _, m in med if g is inv)["datos"] if _externo(x)]
        if externos:
            doc.parrafo(f"Datos que vienen de fuera ({len(externos)}): se verifican en el panel.", fuerte=True)
            _datos_tabla(doc, externos)
    for g, paq, m in med:
        cola.titulo(f"Versión {g['letra']} · {g.get('version', '')}: {m['palabras']} palabras, unos {_min(m['minutos'])} min", "📝")
        if m["lista_avisos"]:
            _avisos(cola, m["lista_avisos"])
        if m["cambios"]:
            cola.parrafo(f"El editor jefe propone {len(m['cambios'])} cambio(s):", fuerte=True)
            _cambios_editor(cola, m["cambios"][:5])
        _guion(cola, g["carpeta"], p["canal"], "#1e40af" if g["letra"] == "A" else "#86198f")


def palabra(tipo: str, verbo: str) -> str:
    elegir = tipo in ELEGIR
    return {"acepto": "APROBAR", "algunas": "ELEGIR", "cambios": "OTRA" if elegir else "REHACER",
            "rechazo": "NINGUNO" if elegir else "RECHAZAR", "deshacer": "DESHACER"}.get(verbo, "RECHAZAR")


def opciones_correo(p: dict) -> list:
    """Las opciones de la puerta tal como salen en el correo, cada una con su `clave` (la de su código). Casi siempre
    la clave es el verbo; cuando dos opciones comparten verbo (elegir A y elegir B: «algunas» con la letra como
    texto), la clave es «verbo:letra» y el código ya lleva la letra: un solo clic decide."""
    PU = _cargar("hyt_puertas")
    gem = {str(g.get("version") or "").lower(): str(g.get("letra") or "").upper() for g in p.get("gemelos") or [] if isinstance(g, dict)}
    out, vistas = [], set()

    def poner(o: dict, letra: str = ""):
        clave = f"{o['verbo']}:{letra}" if letra else o["verbo"]
        if clave not in vistas:
            vistas.add(clave)
            out.append({**o, "clave": clave, "letra": letra})

    for o in PU.opciones_vigentes(p):
        letra = next((str(o[k]) for k in ("letra", "valor", "version") if isinstance(o.get(k), str) and o.get(k)), "")
        letra = gem.get(letra.lower(), letra).upper()
        valores = [str(v) for v in o.get("valores") or [] if str(v).strip()] if isinstance(o.get("valores"), list) else []
        if o["verbo"] == "algunas" and not letra and (valores or p.get("tipo") == "elegir-version"):
            # una opción por valor (o por gemelo): «Elegir A», «Elegir B»…; solo las letras que la puerta tiene
            letras = [str(g.get("letra")).upper() for g in p.get("gemelos") or [] if isinstance(g, dict) and g.get("letra")]
            for v in [gem.get(v.lower(), v).upper() for v in valores] or letras:
                if not letras or v in letras:
                    poner({**o, "etiqueta": f"✅ Elegir {v}"}, v)
            continue
        poner(o, letra)
    return out


def _ayuda_boton(p: dict, o: dict) -> str:
    v, tipo = o["verbo"], p["tipo"]
    if tipo == "elegir-version" and o.get("letra"):
        g = next((g for g in p.get("gemelos") or [] if str(g.get("letra", "")).upper() == o["letra"]), {})
        return f"Se sigue con la versión {o['letra']}" + (f" ({g['version']})" if g.get("version") else "") + "; la otra se descarta."
    return {"acepto": "Da el visto bueno: pasa al siguiente paso al momento.",
            "algunas": {"elegir-temas": "Abre un correo: escribe los números de los temas y envíalo.",
                        "elegir-titulo": "Ya lleva la pareja recomendada: basta con enviarlo (o cambia los números)."}.get(tipo, "Abre un correo ya escrito: envíalo."),
            "cambios": "Pide otra propuesta." if tipo in ELEGIR else "Escribe qué cambiar; puedes señalar las frases por su número.",
            "rechazo": ("Descarta la propuesta" if tipo in ELEGIR else "Descarta las dos versiones" if tipo == "elegir-version"
                        else "Descarta el vídeo") + "; si quieres, di por qué.",
            }.get(v, "")


def _botones(p: dict, cod: dict, rec: dict | None = None) -> tuple:
    """(botones HTML, líneas de texto, ayuda) de una puerta, según su tipo y sus opciones vigentes."""
    tipo = p["tipo"]
    if tipo == "datos":
        return [], [], ""
    botones, lineas = [], []
    for o in opciones_correo(p):
        v, clave, pal = o["verbo"], o["clave"], palabra(tipo, o["verbo"])
        if clave not in cod:
            continue
        extra = ""
        if o.get("letra"):
            extra = f": {o['letra']}"
        elif v == "cambios" and tipo not in ELEGIR:
            extra = f": {AYUDA_REHACER}"
        elif v == "rechazo":
            extra = f": {AYUDA_MOTIVO}"
        elif v == "algunas" and tipo == "elegir-temas":
            extra = f": {AYUDA_TEMAS}"
        elif v == "algunas" and tipo == "elegir-titulo":
            extra = f"\ntitulo: {(rec or {}).get('titulo') or 1}\nminiatura: {(rec or {}).get('miniatura') or 1}"
        botones.append(_boton(pal, cod[clave], o["etiqueta"], extra, ayuda=_ayuda_boton(p, o)))
        lineas.append(f"  {pal} {cod[clave]}" + (f": {o['letra']}" if o.get("letra") else ": …" if extra.startswith(":") else ""))
    ayuda = {"elegir-temas": "Para elegir, escribe los números, por ejemplo: 1, 4, 7 (los suplentes siguen la numeración). «todos» elige todos los propuestos.",
             "elegir-titulo": "El botón de elegir ya lleva la pareja recomendada: basta con enviarlo. Puedes cambiar los números, escribir un "
                              "título propio («titulo: …»), añadir «nota: …» para la miniatura y «destino: …» para el vídeo al que lleva el cierre.",
             "elegir-version": "Cada botón de elegir ya lleva su versión: basta con enviarlo. Un texto libre no decide nada.",
             }.get(tipo, "Para pedir cambios, responde a este correo diciendo qué cambiar (o usa «Rehacer»). Un «ok» o un «gracias» no deciden nada."
                   if tipo in REVISAR else "")
    return botones, lineas, ayuda


def _hash(p: dict) -> str:
    """Huella de lo que se decide: si cambia entre el envío y la respuesta, los códigos dejan de valer."""
    base = p.get("texto", "")
    carpetas = [_carpeta(p)] + [g["carpeta"] for g in _gemelos(p) if g["encargo"] != p.get("encargo")]
    for d in [c for c in carpetas if c]:
        for nombre in ("guion.md", "opciones.json", "temas.json", "perfil-voz.md"):
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


def _chips(p: dict) -> list:
    """Lo que va en la cabecera: puerta de la cadena, ronda y a quién espera (papel y nombres)."""
    papel = p.get("papel") or "marketing"
    nombres = [str(x.get("nombre") or k) for k, x in personas(p["canal"]).items() if papel in (x.get("roles") or []) and _correo(x)]
    try:
        tope = _cargar("hyt_encargos").rondas_max(p["canal"])
    except Exception:   # noqa: BLE001
        tope = 0
    return [f"Puerta {int(p.get('indice') or 0) + 1} de {p.get('total')}" if int(p.get("total") or 1) > 1 and int(p.get("indice") or 0) >= 0 else "",
            (f"Ronda {p['ronda']}" + (f" de {tope}" if tope else "")) if p.get("ronda") else "",
            f"Espera a: {papel}" + (f" ({', '.join(nombres)})" if nombres else "")]


def componer(p: dict, cod: dict | None = None) -> dict:
    """El correo de una puerta: {asunto, texto, html}. Sin `cod`, sin botones (para enseñarlo o probarlo).
    Si el HTML pasa de TOPE_HTML, se rehace enseñando menos bloques de cada guion (el texto va siempre entero)."""
    for limite in (None, 6, 4, 3, 2, 1, 0):
        m = _componer(p, cod, limite)
        if len(m["html"].encode()) <= TOPE_HTML:
            break
    return m


def _componer(p: dict, cod: dict | None, limite: int | None) -> dict:
    PU = _cargar("hyt_puertas")
    doc, cola, rec = Doc(limite), Doc(limite), {}
    cab = " · ".join(x for x in (f"Puerta {int(p.get('indice') or 0) + 1} de {p.get('total')}" if int(p.get("total") or 1) > 1 and int(p.get("indice") or 0) >= 0 else "",
                                 f"decide: {p['papel']}" if p.get("papel") else "",
                                 f"ronda {p['ronda']}" if p.get("ronda") else "") if x)
    if cab:
        doc.t.append(cab)
    graves = PU.graves(p) if p["tipo"] != "datos" else 0
    if graves:
        doc.aviso_grande("Tiene un aviso grave: no se puede aprobar; solo rehacer o rechazar.")
    if p["tipo"] in ("revision", "revision-final"):
        _c_revision(p, doc)
    elif p["tipo"] == "elegir-temas":
        _c_temas(p, doc)
    elif p["tipo"] == "elegir-titulo":
        rec = _c_titulo(p, doc)
    elif p["tipo"] == "elegir-version":
        _c_version(p, doc, cola)
    elif p["tipo"] == "voz":
        _c_voz(p, doc)
    elif p["tipo"] == "datos":
        _c_datos(p, doc)
    else:
        doc.pre(p.get("texto", ""))
    botones, lineas, ayuda = _botones(p, cod, rec) if cod else ([], [], "")
    texto = f"{_nombre_canal(p['canal'])} · {TIPOS.get(p['tipo'], ('Puerta',))[0]}\n{p['titulo']}\n\n{doc.texto()}"
    if cola.t:
        texto += "\n\n" + cola.texto()
    if lineas:
        texto += "\n\nPara decidir, responde con UNA de estas líneas (o usa los botones):\n" + "\n".join(lineas) + (f"\n\n{ayuda}" if ayuda else "")
    # asunto único por puerta: con el mismo asunto el correo junta la puerta nueva con las viejas y se pulsa un botón que ya no vale
    return {"asunto": f"🚪 {p['titulo']} · {_cuando(p['canal'])}", "texto": texto,
            "html": _envolver(p["titulo"], doc.html(), botones, ayuda, p["tipo"], p["canal"], _chips(p), cola.html())}


def enviar_puerta(p: dict) -> dict:
    """Envía una puerta abierta a quien tiene su papel, con un código por opción. Devuelve lo que se guarda en la puerta."""
    a = destinatarios(p["canal"], p.get("papel", ""))
    if not a:
        return {"enviado": B.ahora(), "a": [], "codigos": {}, "hash": _hash(p)}
    cod = {} if p["tipo"] == "datos" else {o["clave"]: secrets.token_urlsafe(12) for o in opciones_correo(p)}
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
    cuerpo = _parrafos(motivo)
    if p["tipo"] == "datos":
        doc = Doc()
        _c_datos(p, doc)
        motivo += "\n\n" + doc.texto()
        cuerpo += doc.html()
    texto = motivo + ("\n\nPara decidir:\n" + "\n".join(lineas) if lineas else "") + (f"\n\n{ayuda}" if ayuda else "")
    titulo = f"No he hecho nada todavía: {p['titulo']}"
    encolar(p["canal"], a, titulo, texto, _envolver(titulo, cuerpo, botones, ayuda, p["tipo"], p["canal"], _chips(p)),
            en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])


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
    """(puerta, clave del código): la clave es el verbo o, si dos opciones lo comparten, «verbo:letra»."""
    PU = _cargar("hyt_puertas")
    for p in PU.puertas(estados):
        for v, c in ((p.get("correo") or {}).get("codigos") or {}).items():
            if secrets.compare_digest(str(c), codigo):
                return p, v
    return None, None


def _decidir(p: dict, verbo: str, texto: str, clave: str, de: str, ref: str, etiqueta: str = "") -> str:
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
    etiqueta = etiqueta or opcion.get("etiqueta", verbo)
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
    encolar(slug, de, f"🕒 Recibido: {p['titulo']}", t, _html(f"Recibido: {p['titulo']}", t, botones, tipo="confirmacion", canal=slug),
            en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
    return f"decidida {p['id']} ({verbo})"


def _con_codigo(m: dict, de: str, suyos: list, hallado, texto: str) -> str:
    PU = _cargar("hyt_puertas")
    ref = m.get("message_id") or ""
    codigo = hallado.group(2)
    resto = _sin_cita(hallado.group(3) or "")
    resto = _sin_ayudas(re.sub(r"\b(" + "|".join(PALABRAS) + r")\s+" + re.escape(codigo) + r"\s*:?", " ", resto)).strip()
    p, clave_cod = _puerta_del_codigo(codigo)
    if not p:
        return _codigo_viejo(de, suyos, codigo, ref)
    clave = next((k for s, k, _ in suyos if s == p["canal"]), None)
    m["_canal"] = p["canal"]
    if not clave:
        return "descartado: el código no es de una puerta de un canal suyo"
    slug = p["canal"]
    if clave_cod == "deshacer":
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
    verbo, _, letra = str(clave_cod).partition(":")
    if (p.get("correo") or {}).get("hash") != _hash(p):
        PU.marcar(p["id"], correo=None)
        encolar(slug, de, f"Ha cambiado: {p['titulo']}", "Lo que se decide ha cambiado desde que te escribí: te mando la versión nueva. "
                "No he hecho nada con tu respuesta.", en_respuesta_a=ref, tipo="confirmacion", puerta=p["id"])
        return "contenido cambiado: se reenvía"
    opcion = next((o for o in p["opciones"] if o["verbo"] == verbo), None) or {}
    etiqueta = next((o["etiqueta"] for o in opciones_correo(p) if o["clave"] == clave_cod), "")
    if letra:   # el código ya dice qué se elige (elegir A o elegir B): lo escrito detrás no cambia la elección
        resto = letra
    if opcion.get("texto") and not resto:
        if verbo == "rechazo":
            resto = "Rechazado por correo, sin motivo"
        else:
            _recordar_botones(p, de, ref, "Falta decir cuáles eliges." if verbo == "algunas" else
                              "Falta decir qué hay que cambiar: escríbelo detrás del código.")
            return f"{verbo} sin texto: se pide"
    return _decidir(p, verbo, resto, clave, de, ref, etiqueta)


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
    botones = [_boton("PROPUESTA", "", "💡 Pedir una propuesta", extra, ayuda="Preparo una propuesta de temas y te llega para elegir."),
               _boton("TEMA:", "", "✍️ Tema propio", f" {AYUDA_TEMA}\nPILAR: {AYUDA_PILAR}{extra}",
                      ayuda="Escribe el tema (y, si quieres, el pilar): preparo título y miniatura."),
               _boton("ESTADO", "", "📋 Ver el estado", extra, ayuda="Te digo cómo va cada vídeo.")]
    t = (motivo + "\n\n" if motivo else "") + "\n".join(lineas)
    encolar(slug, a, "Cómo pedirme algo", t, _html("Cómo pedirme algo", t, botones, tipo="ayuda", canal=slug), en_respuesta_a=ref, tipo="ayuda")


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
    g = paq.get("guion") or {}
    mini = paq.get("miniatura") if isinstance(paq.get("miniatura"), dict) else {}
    doc.parrafo(f"Aprobado por {p.get('firma', '')}. Ya se puede grabar.", fuerte=True)
    if g.get("palabras"):
        doc.crudo(_fichas([(g["palabras"], "palabras", ""), (_min(g.get("minutos")), "minutos", "")]))
    doc.titulo("Título", "▶")
    doc.parrafo(paq.get("titulo", ""), fuerte=True)
    doc.crudo(_vista_previa(_nombre_canal(slug), paq.get("titulo", ""), mini.get("texto", ""), g.get("minutos"), paq.get("promesa", ""),
                            fondo="#14532d"))
    doc.titulo("Miniatura", "🖼")
    _miniatura(doc, paq.get("miniatura"), con_foto=True)
    doc.titulo("Descripción", "📄")
    doc.pre(_lee(d / "descripcion.md"))
    doc.titulo("Guion", "📝")
    doc.pre(guion)
    asunto = f"🎬 Aprobado, listo para grabar: {paq.get('titulo') or enc.get('nombre', '')}"
    a = {c for papel in ("presentador", "marketing") for _, c in destinatarios(slug, papel)}
    for correo in sorted(a):
        encolar(slug, correo, asunto, doc.texto(), _envolver(asunto, doc.html(), tipo="aprobado", canal=slug), tipo="aprobado", puerta=p["id"])


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
        viejas = sum(1 for p in ps if horas[p["id"]] >= 48)
        tarjetas = "".join(_tarjeta(
            _chip(_nombre_canal(p["canal"]), "#f3efe7", TINTA, LINEA) + _chip(TIPOS.get(p["tipo"], ("Puerta",))[0], "#fdf0d5", "#5c3906", "#e6c27a")
            + f"<div style='font-size:17px;font-weight:800;line-height:1.3;color:{TINTA};margin:2px 0 6px'>{E_(p['titulo'])}</div>"
            + _chip(f"⏳ espera desde hace {edad(horas[p['id']])}", *(SUAVE["mal" if horas[p["id"]] >= 48 else "ojo"][i] for i in (0, 2, 1)))
            + (_chip(f"{PU.datos_pendientes(p)} dato(s) por verificar, en el panel", *(SUAVE["ojo"][i] for i in (0, 2, 1))) if p["tipo"] == "datos" else ""),
            LINEA, ROJO if horas[p["id"]] >= 48 else "#d97706") for p in ps)
        cuerpo = (_fichas([(len(ps), "pendientes", "ojo"), (viejas, "más de 2 días", "mal" if viejas else "bien")]) + tarjetas
                  + _parrafos("Cada una tiene su propio correo, con sus botones: búscalo por su título. Los datos se verifican en el panel."))
        asunto = f"⏳ Te esperan {len(ps)} decisión(es)"
        encolar(ps[0]["canal"], correo, asunto, t, _envolver(asunto, cuerpo, tipo="resumen", canal=ps[0]["canal"]), tipo="resumen")
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
