#!/usr/bin/env bash
# Buzón por IMAP y SMTP (hyt_buzon.py), sin red: qué correo se da por auténtico, qué se descarta por automático, cómo
# se lee un correo crudo y cómo sale uno nuestro (remitente, respuesta al buzón, hilo).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
caso() { python3 - "$ROOT/plugin/hermes-youtube" <<PY && ok "$1" || bad "$1"
import sys; sys.path.insert(0, sys.argv[1])
import hyt_buzon as Z
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
i, m = Z.leer(crudo(BASE + ["Authentication-Results: mx.buzon.es; dkim=pass header.d=ejemplo.com"]), "7")
assert m == "" and i["id"] == "7" and i["de"] == "marta@ejemplo.com" and i["in_reply_to"] == "<0@buzon.es>", i
assert i["texto"].strip() == "REHACER abc: alárgalo" and i["asunto"] == "Re: Revisión" and i["ts"] == "2026-11-23T09:00:00Z", i'
caso "leer: sin autenticación, automático, rebote o demasiado grande, se descarta con su motivo" '
assert Z.leer(crudo(BASE), "1") == (None, "no-autentico")
ar = ["Authentication-Results: mx.buzon.es; dmarc=pass"]
assert Z.leer(crudo(BASE + ar + ["Auto-Submitted: auto-replied"]), "2") == (None, "auto-submitted")
assert Z.leer(crudo(BASE + ar + ["List-Id: <x.ejemplo.com>"]), "3") == (None, "lista")
assert Z.leer(crudo(BASE + ar + ["Return-Path: <>"]), "4") == (None, "rebote")
assert Z.leer(b"x" * (Z.MAX_BYTES + 1), "5") == (None, "grande")'
caso "leer: un correo solo en HTML se queda en texto" '
cab = [l for l in BASE if not l.startswith("Content-Type")] + ["Authentication-Results: mx.buzon.es; dmarc=pass", "Content-Type: text/html; charset=utf-8"]
i, _ = Z.leer(crudo(cab, "<p>APROBAR abc</p><p>Gracias &amp; saludos</p>"), "6")
assert "APROBAR abc" in i["texto"] and "Gracias & saludos" in i["texto"] and "<p>" not in i["texto"], i'
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
