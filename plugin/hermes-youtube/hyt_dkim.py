"""Comprobación de firmas DKIM sin dependencias (RFC 6376): rsa-sha256, canonicalización simple y relaxed.

La usa el buzón IMAP cuando su servidor de entrada no deja una cabecera Authentication-Results propia: entonces la
única prueba de que un correo viene de quien dice es la firma DKIM del dominio del remitente, comprobada aquí con la
clave pública que ese dominio publica en el DNS (`<selector>._domainkey.<dominio>`, registro TXT).

  verificar(crudo, dns=txt) → lista de dominios cuya firma es válida (vacía si ninguna)
"""
from __future__ import annotations

import base64
import hashlib
import random
import re
import socket
import struct

DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


# ── mensaje en bruto ────────────────────────────────────────────────────────────────────────────────────────────────
def _partir(crudo: bytes) -> tuple:
    """(cabeceras [(nombre, campo en bruto con CRLF)], cuerpo) con finales de línea CRLF."""
    crudo = re.sub(rb"\r?\n", b"\r\n", crudo)
    i = crudo.find(b"\r\n\r\n")
    cab, cuerpo = (crudo[:i + 2], crudo[i + 4:]) if i >= 0 else (crudo, b"")
    campos = []
    for linea in cab.split(b"\r\n")[:-1] if cab.endswith(b"\r\n") else cab.split(b"\r\n"):
        if linea[:1] in (b" ", b"\t") and campos:
            campos[-1][1] += linea + b"\r\n"
        elif b":" in linea:
            campos.append([linea.split(b":", 1)[0].strip().lower(), linea + b"\r\n"])
    return [(n.decode("latin-1"), c) for n, c in campos], cuerpo


def cuerpo_canonico(cuerpo: bytes, modo: str) -> bytes:
    if modo == "relaxed":
        lineas = [re.sub(rb"[ \t]+", b" ", l).rstrip(b" \t") for l in cuerpo.split(b"\r\n")]
        cuerpo = b"\r\n".join(lineas)
        cuerpo = re.sub(rb"(\r\n)*$", b"", cuerpo)
        return cuerpo + b"\r\n" if cuerpo else b""
    cuerpo = re.sub(rb"(\r\n)*$", b"", cuerpo)
    return cuerpo + b"\r\n"


def cabecera_canonica(campo: bytes, modo: str) -> bytes:
    if modo == "relaxed":
        nombre, valor = campo.split(b":", 1)
        valor = re.sub(rb"\r\n(?=[ \t])", b"", valor)
        valor = re.sub(rb"[ \t]+", b" ", valor.replace(b"\r\n", b"")).strip(b" \t")
        return nombre.strip().lower() + b":" + valor + b"\r\n"
    return campo


def etiquetas(valor: str) -> dict:
    out = {}
    for parte in valor.split(";"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ── clave pública y RSA ────────────────────────────────────────────────────────────────────────────────────────────
def _der(b: bytes, i: int) -> tuple:
    """(etiqueta, contenido, siguiente posición) de un elemento DER."""
    tag, ln = b[i], b[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(b[i:i + n], "big")
        i += n
    return tag, b[i:i + ln], i + ln


def clave_rsa(der: bytes) -> tuple:
    """(n, e) desde SubjectPublicKeyInfo o RSAPublicKey en DER."""
    tag, seq, _ = _der(der, 0)
    t1, c1, j = _der(seq, 0)
    if t1 == 0x30:   # SubjectPublicKeyInfo: algoritmo y BIT STRING con RSAPublicKey dentro
        _, bits, _ = _der(seq, j)
        _, seq, _ = _der(bits[1:], 0)
        t1, c1, j = _der(seq, 0)
    _, e, _ = _der(seq, j)
    return int.from_bytes(c1, "big"), int.from_bytes(e, "big")


def rsa_ok(n: int, e: int, firma: bytes, resumen: bytes) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(firma) != k or k < 128:   # claves de menos de 1024 bits no valen
        return False
    m = pow(int.from_bytes(firma, "big"), e, n).to_bytes(k, "big")
    t = DIGESTINFO_SHA256 + resumen
    return m == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


# ── DNS (TXT) por UDP, con TCP si la respuesta viene truncada ───────────────────────────────────────────────────────
def _resolutor() -> str:
    try:
        for l in open("/etc/resolv.conf"):
            p = l.split()
            if len(p) >= 2 and p[0] == "nameserver" and ":" not in p[1]:
                return p[1]
    except OSError:
        pass
    return "8.8.8.8"


def _nombre(b: bytes, i: int) -> int:
    while True:
        ln = b[i]
        if ln == 0:
            return i + 1
        if ln & 0xC0 == 0xC0:
            return i + 2
        i += ln + 1


def txt(nombre: str, servidor: str = "", timeout: float = 5.0) -> list:
    qid = random.randint(0, 0xFFFF)
    q = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 1)
    q += b"".join(bytes([len(p)]) + p.encode() for p in nombre.strip(".").split(".")) + b"\x00" + struct.pack(">HH", 16, 1)
    q += b"\x00" + struct.pack(">HHIH", 41, 4096, 0, 0)   # EDNS0: respuestas de hasta 4096 bytes
    srv = servidor or _resolutor()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(q, (srv, 53))
        r = s.recv(65535)
    finally:
        s.close()
    if r[2] & 0x02:   # truncada
        with socket.create_connection((srv, 53), timeout=timeout) as t:
            t.sendall(struct.pack(">H", len(q)) + q)
            ln = struct.unpack(">H", t.recv(2))[0]
            r = b""
            while len(r) < ln:
                r += t.recv(ln - len(r))
    if struct.unpack(">H", r[:2])[0] != qid:
        return []
    an = struct.unpack(">H", r[6:8])[0]
    i = _nombre(r, 12) + 4
    out = []
    for _ in range(an):
        i = _nombre(r, i)
        tipo, _, _, ln = struct.unpack(">HHIH", r[i:i + 10])
        i += 10
        if tipo == 16:
            dato, j, partes = r[i:i + ln], 0, []
            while j < len(dato):
                partes.append(dato[j + 1:j + 1 + dato[j]])
                j += 1 + dato[j]
            out.append(b"".join(partes).decode("latin-1"))
        i += ln
    return out


# ── verificación ────────────────────────────────────────────────────────────────────────────────────────────────────
def _una(cabs: list, cuerpo: bytes, idx: int, dns) -> str:
    """El dominio (d=) si la firma número `idx` es válida; si no, ""."""
    campo = [c for n, c in cabs if n == "dkim-signature"][idx]
    t = etiquetas(re.sub(rb"\r\n", b"", campo.split(b":", 1)[1]).decode("latin-1"))
    if t.get("v") != "1" or t.get("a") != "rsa-sha256" or not all(t.get(k) for k in ("b", "bh", "d", "h", "s")):
        return ""
    ch, _, cb = (t.get("c") or "simple/simple").partition("/")
    cb = cb or "simple"
    cuerpo_c = cuerpo_canonico(cuerpo, cb)
    if t.get("l", "").isdigit():
        cuerpo_c = cuerpo_c[:int(t["l"])]
    if base64.b64encode(hashlib.sha256(cuerpo_c).digest()).decode() != re.sub(r"\s", "", t["bh"]):
        return ""
    usados, datos = {}, b""
    for nombre in [x.strip().lower() for x in t["h"].split(":") if x.strip()]:
        todos = [c for n, c in cabs if n == nombre]
        k = usados.get(nombre, 0)
        if k < len(todos):   # de abajo arriba; si no quedan, la cabecera cuenta como vacía
            datos += cabecera_canonica(todos[len(todos) - 1 - k], ch)
        usados[nombre] = k + 1
    sin_b = re.sub(rb"(\bb[ \t\r\n]*=)[^;]*", rb"\1", campo, count=1)
    datos += cabecera_canonica(sin_b, ch).rstrip(b"\r\n")
    registros = [r for r in dns(f"{t['s']}._domainkey.{t['d']}") if "p=" in r]
    if not registros:
        return ""
    clave = etiquetas(registros[0])
    if clave.get("k", "rsa") != "rsa" or not clave.get("p"):
        return ""
    try:
        n, e = clave_rsa(base64.b64decode(re.sub(r"\s", "", clave["p"])))
        firma = base64.b64decode(re.sub(r"\s", "", t["b"]))
    except (ValueError, IndexError):
        return ""
    return t["d"].lower() if rsa_ok(n, e, firma, hashlib.sha256(datos).digest()) else ""


def verificar(crudo: bytes, dns=None) -> list:
    dns = dns or txt
    cabs, cuerpo = _partir(crudo)
    out = []
    for i in range(sum(1 for n, _ in cabs if n == "dkim-signature")):
        try:
            d = _una(cabs, cuerpo, i, dns)
        except (OSError, ValueError, IndexError, struct.error):
            d = ""
        if d:
            out.append(d)
    return out
