"""YouTube sin dependencias: buscar vídeos, bajar su transcripción y comprobar que un vídeo existe.

Lo usa la etapa `investigar` (desde la terminal del perfil) y el código que comprueba su trabajo. Habla con las mismas
direcciones públicas que usa la web y la aplicación de YouTube; si YouTube cambia algo, falla con un mensaje claro y
la investigación sigue con las fuentes web.

  hyt_youtube.py buscar "<consulta>" [--n 8] [--idioma es]     vídeos: id, título, canal, duración, vistas, fecha
  hyt_youtube.py transcripcion <url|id> [--idioma es,en]          texto con marcas de tiempo [m:ss]
  hyt_youtube.py existe <url|id>                                  título y canal (oEmbed) o error
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA_WEB = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
ANDROID = {"clientName": "ANDROID", "clientVersion": "20.10.38", "androidSdkVersion": 30}
UA_ANDROID = "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"


class Fallo(Exception):
    pass


def video_id(x: str) -> str:
    x = str(x or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", x):
        return x
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", x)
    if not m:
        raise Fallo(f"no reconozco un vídeo de YouTube en «{x}»")
    return m.group(1)


def _pedir(url: str, datos: dict | None = None, ua: str = UA_WEB, idioma: str = "es") -> bytes:
    req = urllib.request.Request(url, data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"User-Agent": ua, "Accept-Language": idioma, "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=25).read()
    except urllib.error.HTTPError as e:
        raise Fallo(f"YouTube respondió {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise Fallo(f"no se pudo hablar con YouTube: {e}") from e


def existe(x: str, pedir=None) -> dict:
    """oEmbed público: {titulo, canal, url} o Fallo si el vídeo no existe o no es público."""
    vid = video_id(x)
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
    try:
        d = json.loads((pedir or _pedir)(url))
    except ValueError as e:
        raise Fallo("oEmbed no devolvió JSON") from e
    return {"id": vid, "titulo": d.get("title", ""), "canal": d.get("author_name", ""),
            "url": f"https://www.youtube.com/watch?v={vid}"}


def _texto(runs) -> str:
    if isinstance(runs, dict):
        return runs.get("simpleText") or "".join(r.get("text", "") for r in runs.get("runs") or [])
    return ""


def _videos(nodo) -> list:
    out = []
    if isinstance(nodo, dict):
        if "videoRenderer" in nodo:
            v = nodo["videoRenderer"]
            out.append({"id": v.get("videoId"), "titulo": _texto(v.get("title")),
                        "canal": _texto(v.get("ownerText")) or _texto(v.get("longBylineText")),
                        "duracion": _texto(v.get("lengthText")), "vistas": _texto(v.get("viewCountText")),
                        "fecha": _texto(v.get("publishedTimeText")),
                        "url": f"https://www.youtube.com/watch?v={v.get('videoId')}"})
        else:
            for x in nodo.values():
                out += _videos(x)
    elif isinstance(nodo, list):
        for x in nodo:
            out += _videos(x)
    return out


def buscar(consulta: str, n: int = 8, idioma: str = "es") -> list:
    cuerpo = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20251101.00.00", "hl": idioma}},
              "query": consulta}
    try:
        d = json.loads(_pedir("https://www.youtube.com/youtubei/v1/search?prettyPrint=false", cuerpo, idioma=idioma))
    except ValueError as e:
        raise Fallo("la búsqueda no devolvió JSON") from e
    vistos, out = set(), []
    for v in _videos(d):
        if v["id"] and v["id"] not in vistos:
            vistos.add(v["id"])
            out.append(v)
    return out[:n]


def _mmss(ms: int) -> str:
    s = ms // 1000
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def pistas(x: str) -> list:
    vid = video_id(x)
    cuerpo = {"context": {"client": {**ANDROID, "hl": "es"}}, "videoId": vid}
    try:
        d = json.loads(_pedir("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", cuerpo, ua=UA_ANDROID))
    except ValueError as e:
        raise Fallo("el reproductor no devolvió JSON") from e
    estado = (d.get("playabilityStatus") or {}).get("status")
    if estado != "OK":
        raise Fallo(f"YouTube no deja ver el vídeo ({estado}: {(d.get('playabilityStatus') or {}).get('reason', '')})")
    return ((d.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks") or []


def transcripcion(x: str, idiomas: str = "es,en") -> dict:
    """{id, idioma, automatica, texto}: el texto con una marca [m:ss] cada ~30 segundos."""
    ps = pistas(x)
    if not ps:
        raise Fallo("el vídeo no tiene subtítulos")
    orden = [i.strip() for i in idiomas.split(",") if i.strip()]

    def rango(p):
        lang = p.get("languageCode", "")
        pos = next((i for i, l in enumerate(orden) if lang == l or lang.startswith(l + "-")), len(orden))
        return (pos, p.get("kind") == "asr")   # a igualdad de idioma, mejor la escrita a mano que la automática
    p = sorted(ps, key=rango)[0]
    if rango(p)[0] == len(orden):
        raise Fallo(f"no hay subtítulos en {idiomas} (hay: {', '.join(sorted({q.get('languageCode', '') for q in ps}))})")
    xml = _pedir(p["baseUrl"], ua=UA_ANDROID).decode("utf-8", "replace")
    trozos, ultima = [], -30000
    for t, cuerpo in re.findall(r'<p t="(\d+)"[^>]*>(.*?)</p>', xml, re.S):
        frase = html.unescape(re.sub(r"<[^>]+>", "", cuerpo)).replace("\n", " ").strip()
        if not frase:
            continue
        if int(t) - ultima >= 30000:
            trozos.append(f"\n[{_mmss(int(t))}] ")
            ultima = int(t)
        trozos.append(frase + " ")
    texto = re.sub(r"[ \t]+", " ", "".join(trozos)).strip()
    if not texto:
        raise Fallo("los subtítulos vinieron vacíos")
    return {"id": video_id(x), "idioma": p.get("languageCode", ""), "automatica": p.get("kind") == "asr", "texto": texto}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hyt_youtube.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buscar"); b.add_argument("consulta"); b.add_argument("--n", type=int, default=8)
    b.add_argument("--idioma", default="es")
    t = sub.add_parser("transcripcion"); t.add_argument("video"); t.add_argument("--idioma", default="es,en")
    sub.add_parser("existe").add_argument("video")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "buscar":
            for v in buscar(x.consulta, x.n, x.idioma):
                print(json.dumps(v, ensure_ascii=False))
        elif x.cmd == "transcripcion":
            r = transcripcion(x.video, x.idioma)
            print(f"# {r['id']} · idioma {r['idioma']}{' (automática)' if r['automatica'] else ''}\n")
            print(r["texto"])
        elif x.cmd == "existe":
            print(json.dumps(existe(x.video), ensure_ascii=False))
    except Fallo as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
