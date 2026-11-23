#!/usr/bin/env bash
# Herramienta de YouTube (hyt_youtube.py), sin red: reconocer un vídeo en cualquier enlace, leer los resultados de una
# búsqueda, elegir los subtítulos por idioma (mejor escritos que automáticos) y montar la transcripción con marcas.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
caso() { python3 - "$ROOT/plugin/hermes-youtube" <<PY && ok "$1" || bad "$1"
import json, sys; sys.path.insert(0, sys.argv[1])
import hyt_youtube as Y
$2
PY
}
caso "reconoce el vídeo en cualquier forma de enlace y rechaza lo que no es un vídeo" '
for u in ("abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk&t=3", "https://youtu.be/abcdefghijk",
          "https://www.youtube.com/shorts/abcdefghijk", "https://www.youtube.com/embed/abcdefghijk"):
    assert Y.video_id(u) == "abcdefghijk", u
try: Y.video_id("https://ejemplo.com/x"); assert False
except Y.Fallo: pass'
caso "búsqueda: saca los vídeos (sin repetir) de la respuesta, estén donde estén" '
v = lambda i, t: {"videoRenderer": {"videoId": i, "title": {"runs": [{"text": t}]}, "ownerText": {"runs": [{"text": "Canal"}]},
                                    "lengthText": {"simpleText": "5:08"}, "viewCountText": {"simpleText": "10 vistas"}}}
resp = {"contents": {"a": [{"b": v("aaaaaaaaaaa", "Uno")}, {"shelf": [v("bbbbbbbbbbb", "Dos"), v("aaaaaaaaaaa", "Uno")]}]}}
Y._pedir = lambda *a, **k: json.dumps(resp).encode()
r = Y.buscar("x")
assert [(x["id"], x["titulo"], x["canal"], x["duracion"]) for x in r] == [("aaaaaaaaaaa", "Uno", "Canal", "5:08"), ("bbbbbbbbbbb", "Dos", "Canal", "5:08")], r'
caso "transcripción: el idioma pedido, mejor la escrita a mano, con una marca cada ~30 s; sin el idioma, error claro" '
pistas = [{"languageCode": "de", "baseUrl": "de"}, {"languageCode": "es", "kind": "asr", "baseUrl": "es-auto"},
          {"languageCode": "es-ES", "baseUrl": "es-mano"}]
Y.pistas = lambda x: pistas
xml = {"es-mano": "<timedtext><body><p t=%s0%s d=%s1%s>Hola &amp; bienvenidos</p><p t=%s12000%s d=%s1%s>seguimos</p>".replace("%s", chr(34))
                  + "<p t=%s45000%s d=%s1%s>otra <s>parte</s></p></body></timedtext>".replace("%s", chr(34))}
Y._pedir = lambda url, *a, **k: xml[url].encode()
r = Y.transcripcion("abcdefghijk", "es,en")
assert r["idioma"] == "es-ES" and not r["automatica"] and r["texto"] == "[0:00] Hola & bienvenidos seguimos " + chr(10) + "[0:45] otra parte", r
try: Y.transcripcion("abcdefghijk", "fr"); assert False
except Y.Fallo as e: assert "no hay subtítulos en fr" in str(e)'
exit $fail
