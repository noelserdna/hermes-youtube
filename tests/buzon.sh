#!/usr/bin/env bash
# Buzón por IMAP y SMTP (hyt_buzon.py), sin red: qué correo se da por auténtico, qué se descarta por automático, cómo
# se lee un correo crudo y cómo sale uno nuestro (remitente, respuesta al buzón, hilo).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
caso() { python3 - "$ROOT/plugin/hermes-youtube" <<PY && ok "$1" || bad "$1"
import sys; sys.path.insert(0, sys.argv[1])
import hyt_buzon as Z
import base64, hashlib, hyt_dkim as K
# clave RSA de 2048 bits solo para estas pruebas
NK = 0xac57eb555f7a8c9bee79d94011516334dd3d30ad362a961b80e272d8e19b7fa06554a718251f4f8793bc0a9d291fd9cc01f661521fa0a3b3b8fbaccfff8e8d780cec82ca8974e8a72d77fba420b7f9e7d2deb0c2a4dd473dde6037093ddf47bbd421fc92a1c17b2b4d2e716fee7858bb942b009211b73fca571b2856d5813391fe9f0b9097ad1f496bc1a7f5caba18b52ac7fb21b880418a69c7fd5fe554f1f81d5d7bd6d448d3641c87af55e053b74e18ff5fc0d8f43194af22c986fd05b408246cbe581500f1ce2cab4614666c481c1e131f8bd5e6d731ed068114b414cc3afe68ac768c5a12432e4fd5d3729ea2a6e3ee5f3dd926482fbf0632ed09275e09
DK = 0x867f227800c839bd6311927ace490ebbedc0582184f91d261fa21970aa3859148a9fd2bb241558527cf7adecd27039df5cd4b3448ccc27951552cb9d9359e38b81c27d9ba4442960763a8196a7b60c005fef4c50caaaa9735dfd06565f03c60e8e516bb3df2a887dd580de24351d9459e71adc1a225b391c26785a35d1ef3f9772e24a1e0cfbff26479f05c39b7f3dcc9365732cba8eee7d2e8af50dba72c049f974feb7e337cf60e5611df39c13df92470c197ff86fef460fca246d349abd284eddedb8f5a6c43b40505c0d9e616050b3408820f852587e2b136e9fc940fd8b79386fb9935df135ffcd1678124b0bf9fad48f22e3900510e60ea2fd9abd3735
PUB = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArFfrVV96jJvuedlAEVFjNN09MK02KpYbgOJy2OGbf6BlVKcYJR9Ph5O8Cp0pH9nMAfZhUh+go7O4+6zP/46NeAzsgsqJdOinLXf7pCC3+efS3rDCpN1HPd5gNwk930e71CH8kqHBeytNLnFv7nhYu5QrAJIRtz/KVxsoVtWBM5H+nwuQl60fSWvBp/XKuhi1Ksf7IbiAQYppx/1f5VTx+B1de9bUSNNkHIevVeBTt04Y/1/A2PQxlK8iyYb9BbQIJGy+WBUA8c4sq0YUZmxIHB4TH4vV5tcx7QaBFLQUzDr+aKx2jFoSQy5P1dNynqKm4+5fPdkmSC+/BjLtCSdeCQIDAQAB"
dns = lambda nombre: [PUB] if nombre == "prueba._domainkey.ejemplo.com" else []
def firmar(raw, dominio="ejemplo.com", c="relaxed/relaxed", h="from:to:subject:date:message-id"):
    cabs, cuerpo = K._partir(raw)
    ch, cb = c.split("/")
    bh = base64.b64encode(hashlib.sha256(K.cuerpo_canonico(cuerpo, cb)).digest()).decode()
    sig = f"DKIM-Signature: v=1; a=rsa-sha256; c={c}; d={dominio}; s=prueba;\r\n h={h}; bh={bh};\r\n b="
    datos = b"".join(K.cabecera_canonica([x for n, x in cabs if n == nombre][-1], ch) for nombre in h.split(":"))
    datos += K.cabecera_canonica(sig.encode() + b"\r\n", ch).rstrip(b"\r\n")
    k = (NK.bit_length() + 7) // 8; t = K.DIGESTINFO_SHA256 + hashlib.sha256(datos).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    b = base64.b64encode(pow(int.from_bytes(em, "big"), DK, NK).to_bytes(k, "big")).decode()
    return (sig + b[:60] + "\r\n " + b[60:] + "\r\n").encode() + raw
def crudo(cab, cuerpo="REHACER abc: alárgalo"):
    return ("\r\n".join(cab) + "\r\n\r\n" + cuerpo + "\r\n").encode()
BASE = ["From: Marta <marta@ejemplo.com>", "To: sistema@buzon.es", "Subject: Re: Revisión", "Message-ID: <1@ejemplo.com>",
        "In-Reply-To: <0@buzon.es>", "Date: Mon, 23 Nov 2026 10:00:00 +0100", "Content-Type: text/plain; charset=utf-8"]
$2
PY
}
caso "auténtico: dmarc=pass, o dkim/spf=pass del dominio del remitente, en la cabecera del servidor de entrada" '
assert Z.autentico(["mx.buzon.es; dmarc=pass header.from=ejemplo.com"], "marta@ejemplo.com")
assert Z.autentico(["mx.buzon.es; dkim=pass header.d=ejemplo.com; spf=none"], "marta@ejemplo.com")
assert Z.autentico(["mx.buzon.es; spf=pass smtp.mailfrom=rebotes.ejemplo.com"], "marta@ejemplo.com")
assert not Z.autentico(["mx.buzon.es; dkim=pass header.d=otro.com; spf=pass smtp.mailfrom=otro.com"], "marta@ejemplo.com")
assert not Z.autentico(["mx.buzon.es; dkim=fail header.d=ejemplo.com"], "marta@ejemplo.com")
assert not Z.autentico([], "marta@ejemplo.com")
assert not Z.autentico(["otro.servidor; dmarc=pass"], "marta@ejemplo.com", "mx.buzon.es")
assert not Z.autentico(["mx.buzon.es; dmarc=fail", "mx.buzon.es; dmarc=pass"], "marta@ejemplo.com")'
caso "leer: un correo auténtico sale como los del Worker, con su hilo y el texto" '
i, m = Z.leer(crudo(BASE + ["Authentication-Results: mx.buzon.es; dkim=pass header.d=ejemplo.com"]), "7", "mx.buzon.es")
assert m == "" and i["id"] == "7" and i["de"] == "marta@ejemplo.com" and i["in_reply_to"] == "<0@buzon.es>", i
assert i["texto"].strip() == "REHACER abc: alárgalo" and i["asunto"] == "Re: Revisión" and i["ts"] == "2026-11-23T09:00:00Z", i'
caso "leer: sin autenticación, automático, rebote o demasiado grande, se descarta con su motivo" '
assert Z.leer(crudo(BASE), "1", "mx.buzon.es") == (None, "no-autentico")
ar = ["Authentication-Results: mx.buzon.es; dmarc=pass"]
assert Z.leer(crudo(BASE + ar + ["Auto-Submitted: auto-replied"]), "2", "mx.buzon.es") == (None, "auto-submitted")
assert Z.leer(crudo(BASE + ar + ["List-Id: <x.ejemplo.com>"]), "3", "mx.buzon.es") == (None, "lista")
assert Z.leer(crudo(BASE + ar + ["Return-Path: <>"]), "4", "mx.buzon.es") == (None, "rebote")
assert Z.leer(b"x" * (Z.MAX_BYTES + 1), "5") == (None, "grande")'
caso "leer: un correo solo en HTML se queda en texto" '
cab = [l for l in BASE if not l.startswith("Content-Type")] + ["Authentication-Results: mx.buzon.es; dmarc=pass", "Content-Type: text/html; charset=utf-8"]
i, _ = Z.leer(crudo(cab, "<p>APROBAR abc</p><p>Gracias &amp; saludos</p>"), "6", "mx.buzon.es")
assert "APROBAR abc" in i["texto"] and "Gracias & saludos" in i["texto"] and "<p>" not in i["texto"], i'
caso "dkim: la firma del dominio vale con relaxed y con simple; un cambio en el cuerpo o en el asunto la rompe" '
for c in ("relaxed/relaxed", "simple/simple", "relaxed/simple"):
    raw = firmar(crudo(BASE), c=c)
    assert K.verificar(raw, dns) == ["ejemplo.com"], c
    assert K.verificar(raw.replace("alárgalo".encode(), "acórtalo".encode()), dns) == [], c
    assert K.verificar(raw.replace(b"Subject: Re:", b"Subject: RE:"), dns) == [], c
assert K.verificar(crudo(BASE), dns) == []
assert K.verificar(firmar(crudo(BASE), dominio="otro.com"), dns) == []'
caso "sin servidor de confianza: vale solo la firma DKIM del dominio del remitente, no una cabecera que trae el correo" '
falsa = BASE + ["Authentication-Results: mx.buzon.es; dmarc=pass header.from=ejemplo.com"]
assert Z.leer(crudo(falsa), "8", dns=dns) == (None, "no-autentico")
i, m = Z.leer(firmar(crudo(BASE)), "9", dns=dns); assert m == "" and i["de"] == "marta@ejemplo.com", m
otro = [l.replace("marta@ejemplo.com", "marta@intruso.com") for l in BASE]
assert Z.leer(firmar(crudo(otro)), "10", dns=dns) == (None, "no-autentico")'
caso "enviar: sale de la cuenta con respuesta al buzón, en el hilo y marcado como automático; texto y HTML" '
c = {"HYT_CORREO_BUZON": "sistema@buzon.es", "HYT_CORREO_USUARIO": "sistema@buzon.es", "HYT_CORREO_NOMBRE": "Canal"}
m = Z.mensaje(c, {"to": "marta@ejemplo.com", "subject": "Revisión", "text": "hola", "html": "<p>hola</p>", "in_reply_to": "<0@buzon.es>"})
assert m["From"] == "Canal <sistema@buzon.es>" and m["Reply-To"] == "sistema@buzon.es" and m["References"] == "<0@buzon.es>"
assert m["Auto-Submitted"] == "auto-generated" and m["Message-ID"].endswith("@buzon.es>") and m.is_multipart()
assert Z.enviar(c, {"to": "", "subject": "x", "text": "y"})["ok"] is False'
caso "el correo del plugin usa el buzón IMAP cuando está configurado, y sin clave no se activa" '
import os; os.environ.update(HYT_CORREO_CONF="/no/existe", HYT_CORREO_IMAP="imap.buzon.es:993", HYT_CORREO_SMTP="smtp.buzon.es:587",
                              HYT_CORREO_BUZON="sistema@buzon.es", HYT_CORREO_USUARIO="sistema@buzon.es")
import hyt_correo as HC
assert not HC.activo()
os.environ["HYT_CORREO_CLAVE"] = "x"; assert HC.activo()'
exit $fail
