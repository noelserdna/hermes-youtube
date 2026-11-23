"""Buzón por IMAP y SMTP: la alternativa al Worker de Cloudflare para un buzón de correo normal.

Habla el mismo idioma que el Worker (`/pendientes`, `/hecho`, `/enviar`), así que el resto del correo no cambia. Se
activa con HYT_CORREO_IMAP en correo.env:

  HYT_CORREO_BUZON=sistema@ejemplo.com          la dirección a la que responden las personas
  HYT_CORREO_IMAP=imap.ejemplo.com:993           entrada (SSL)
  HYT_CORREO_SMTP=smtp.ejemplo.com:587           salida (STARTTLS en 587, SSL en 465)
  HYT_CORREO_USUARIO=sistema@ejemplo.com
  HYT_CORREO_CLAVE=…
  HYT_CORREO_AUTENTICA=mx.ejemplo.com            opcional: el servidor cuya cabecera Authentication-Results vale

Lo que llega se filtra igual que en el Worker: nada de más de 1 MB, nada que el servidor de entrada no dé por auténtico
(la PRIMERA cabecera Authentication-Results, la que pone él, con dmarc=pass, o dkim/spf=pass del mismo dominio que el
remitente) y nada automático (respuestas de vacaciones, listas, rebotes). Lo descartado se marca como leído y se cuenta
sin guardar el texto. Un correo se marca como leído cuando el plugin dice que lo ha atendido (`/hecho`).
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import html
import imaplib
import json
import re
import smtplib
import ssl
import time
from datetime import timezone
from email.message import EmailMessage
from pathlib import Path

MAX_BYTES = 1024 * 1024


def _hostport(v: str, defecto: int) -> tuple:
    h, _, p = str(v).partition(":")
    return h.strip(), int(p or defecto)


def _dominio(direccion: str) -> str:
    return str(direccion or "").rsplit("@", 1)[-1].strip().lower().rstrip(">")


def _alineado(d: str, de: str) -> bool:
    """El dominio que firma es el del remitente o uno de sus padres (alineación relajada de DMARC)."""
    d, de = d.lower().strip("."), de.lower().strip(".")
    return bool(d) and (de == d or de.endswith("." + d) or d.endswith("." + de))


def autentico(cabeceras: list, de: str, servidor: str = "") -> bool:
    """`cabeceras`: las Authentication-Results del correo en orden (la primera es la del servidor de entrada)."""
    if not cabeceras:
        return False
    ar = " ".join(str(cabeceras[0]).split()).lower()
    if servidor and not ar.startswith(servidor.lower()):
        return False
    if re.search(r"\bdmarc=pass\b", ar):
        return True
    dom = _dominio(de)
    for d in re.findall(r"\bdkim=pass\b[^;]*?header\.(?:d|i)=@?([a-z0-9.-]+)", ar):
        if _alineado(d, dom):
            return True
    for d in re.findall(r"\bspf=pass\b[^;]*?smtp\.(?:mailfrom|from)=(?:[^@\s;]*@)?([a-z0-9.-]+)", ar):
        if _alineado(d, dom):
            return True
    return False


def automatico(m, de: str) -> str:
    g = lambda k: str(m.get(k) or "").lower()
    if g("auto-submitted") and g("auto-submitted") != "no":
        return "auto-submitted"
    if re.search(r"\b(bulk|list|junk|auto_reply)\b", g("precedence")):
        return "precedence"
    if g("x-autoreply") or g("x-autorespond") or g("x-auto-response-suppress"):
        return "x-autoreply"
    if g("list-id") or g("list-unsubscribe"):
        return "lista"
    if g("return-path").strip() == "<>":
        return "rebote"
    if re.match(r"^(mailer-daemon|postmaster|no-?reply|bounce)", str(de or ""), re.I):
        return "remitente-automatico"
    return ""


def _texto(m) -> str:
    parte = m.get_body(preferencelist=("plain", "html"))
    if parte is None:
        return ""
    t = parte.get_content()
    if parte.get_content_subtype() == "html":
        t = re.sub(r"(?is)<(script|style).*?</\1>", "", t)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return t


def leer(crudo: bytes, uid: str, servidor: str = "") -> tuple:
    """Un correo crudo → (item como los del Worker, "") o (None, motivo del descarte)."""
    if len(crudo) > MAX_BYTES:
        return None, "grande"
    m = email.message_from_bytes(crudo, policy=email.policy.default)
    de = email.utils.parseaddr(str(m.get("from") or ""))[1].lower()
    if not autentico(m.get_all("authentication-results") or [], de, servidor):
        return None, "no-autentico"
    auto = automatico(m, de)
    if auto:
        return None, auto
    try:
        f = email.utils.parsedate_to_datetime(str(m.get("date")))
        fecha = (f.astimezone(timezone.utc) if f.tzinfo else f).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        fecha = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {"id": uid, "ts": fecha, "de": de, "asunto": str(m.get("subject") or "")[:300], "texto": _texto(m)[:20000],
            "message_id": str(m.get("message-id") or "").strip(), "in_reply_to": str(m.get("in-reply-to") or "").strip()}, ""


def _imap(c: dict):
    h, p = _hostport(c["HYT_CORREO_IMAP"], 993)
    im = imaplib.IMAP4_SSL(h, p, ssl_context=ssl.create_default_context(), timeout=30)
    im.login(c["HYT_CORREO_USUARIO"], c["HYT_CORREO_CLAVE"])
    im.select("INBOX")
    return im


def _contar(descartes: dict, motivo: str, dir_estado: Path | None) -> None:
    descartes[motivo] = descartes.get(motivo, 0) + 1
    if dir_estado:
        f = dir_estado / f"descartados-{time.strftime('%Y-%m-%d')}.json"
        d = json.loads(f.read_text()) if f.exists() else {}
        d[motivo] = d.get(motivo, 0) + 1
        f.write_text(json.dumps(d))


def pendientes(c: dict, dir_estado: Path | None = None) -> dict:
    im = _imap(c)
    try:
        _, datos = im.uid("search", None, "UNSEEN")
        uids = (datos[0] or b"").split()[:50]
        out, descartes = [], {}
        for u in uids:
            _, r = im.uid("fetch", u, "(BODY.PEEK[])")
            crudo = next((x[1] for x in r if isinstance(x, tuple)), b"")
            item, motivo = leer(crudo, u.decode(), c.get("HYT_CORREO_AUTENTICA", ""))
            if item:
                out.append(item)
            else:
                im.uid("store", u, "+FLAGS", "(\\Seen)")
                _contar(descartes, motivo, dir_estado)
        hoy = {}
        if dir_estado and (dir_estado / f"descartados-{time.strftime('%Y-%m-%d')}.json").exists():
            hoy = json.loads((dir_estado / f"descartados-{time.strftime('%Y-%m-%d')}.json").read_text())
        return {"correos": out, "descartados_hoy": hoy}
    finally:
        try:
            im.logout()
        except Exception:   # noqa: BLE001
            pass


def hecho(c: dict, ids: list) -> dict:
    if not ids:
        return {"ok": True, "borrados": 0}
    im = _imap(c)
    try:
        for u in ids:
            im.uid("store", str(u), "+FLAGS", "(\\Seen)")
        return {"ok": True, "borrados": len(ids)}
    finally:
        try:
            im.logout()
        except Exception:   # noqa: BLE001
            pass


def mensaje(c: dict, d: dict) -> EmailMessage:
    m = EmailMessage()
    buzon = c["HYT_CORREO_BUZON"]
    m["From"] = email.utils.formataddr((c.get("HYT_CORREO_NOMBRE") or "hermes-youtube", c.get("HYT_CORREO_USUARIO") or buzon))
    m["To"] = d["to"]
    m["Reply-To"] = buzon
    m["Subject"] = str(d["subject"])[:300]
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid(domain=_dominio(buzon) or None)
    m["Auto-Submitted"] = "auto-generated"
    if d.get("in_reply_to"):
        m["In-Reply-To"] = d["in_reply_to"]
        m["References"] = d["in_reply_to"]
    m.set_content(d.get("text") or re.sub(r"<[^>]+>", "", d.get("html") or ""))
    if d.get("html"):
        m.add_alternative(d["html"], subtype="html")
    return m


def enviar(c: dict, d: dict) -> dict:
    if not d.get("to") or not d.get("subject") or not (d.get("text") or d.get("html")):
        return {"ok": False, "error": "faltan to, subject y text/html"}
    m = mensaje(c, d)
    h, p = _hostport(c["HYT_CORREO_SMTP"], 587)
    try:
        if p == 465:
            s = smtplib.SMTP_SSL(h, p, context=ssl.create_default_context(), timeout=30)
        else:
            s = smtplib.SMTP(h, p, timeout=30)
            s.starttls(context=ssl.create_default_context())
        with s:
            s.login(c["HYT_CORREO_USUARIO"], c["HYT_CORREO_CLAVE"])
            s.send_message(m)
        return {"ok": True, "messageId": m["Message-ID"]}
    except (smtplib.SMTPException, OSError) as e:
        return {"ok": False, "error": str(e)[:200]}


def llamar(c: dict, metodo: str, ruta: str, cuerpo: dict | None, dir_estado: Path | None = None) -> dict:
    try:
        if ruta == "/pendientes":
            return pendientes(c, dir_estado)
        if ruta == "/hecho":
            return hecho(c, (cuerpo or {}).get("ids") or [])
        if ruta == "/enviar":
            return enviar(c, cuerpo or {})
    except (imaplib.IMAP4.error, OSError) as e:
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": False, "error": "no existe"}
