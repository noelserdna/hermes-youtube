"""Fuentes de un canal: el material propio del que sale todo el contenido. Carga sin modelo.

Una fuente es una transcripción con marcas de tiempo. Cargarla es: leer el texto (de una carpeta o de un zip), partirlo
por sus marcas «[h:mm:ss]», quitar el ruido del reconocimiento automático («[música]», «[risas]») y, si viene con
subtítulos .vtt, medir a qué ritmo habla la persona. No corrige palabras mal transcritas: eso necesita contexto y lo
hace la etapa de inventario con las pistas del canal.

  canales/<canal>/fuentes/indice.json                 qué hay cargado, y el ritmo de lectura medido
  canales/<canal>/fuentes/<colección>/<id>.json       la fuente por tramos: [{t, marca, texto, palabras}]
  canales/<canal>/fuentes/<colección>/<id>.txt        la misma, legible, para las etapas

  hyt_fuentes.py cargar <canal> <carpeta|zip> --coleccion <nombre> --tipo <tipo>
  hyt_fuentes.py lista <canal>

El tipo es libre («directo», «guionizado», «podcast»…). El ritmo de lectura solo se mide en las fuentes guionizadas:
en un directo hablan varias personas y hay silencios, y el número no dice nada.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import statistics
import sys
import zipfile
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
T = _cargar("hyt_texto")
Rechazo = B.Rechazo

MARCA = re.compile(r"^\[(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\]\s*$", re.M)
RUIDO = re.compile(r"\[[a-záéíóúüñ ]{2,30}\]", re.I)          # [música], [risas], [grito ahogado]…
TIEMPO_VTT = re.compile(r"-->\s*(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})")
GUIONIZADOS = ("guionizado", "pildora", "píldora", "video", "vídeo")
NOMBRE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def carpeta(slug: str) -> Path:
    return B.home() / "canales" / B.validar_slug(slug) / "fuentes"


def indice(slug: str) -> dict:
    return B.leer(carpeta(slug) / "indice.json", None) or {"fuentes": [], "ppm_medido": 0}


def _id(nombre: str) -> str:
    """«P01 - Reto … 1 10 · La IA no te reemplaza.txt» → «p01»; sin separador, el nombre entero en minúsculas."""
    base = Path(nombre).name
    base = re.sub(r"\.(txt|vtt)$", "", base, flags=re.I)
    base = re.sub(r"\.[a-z]{2,3}(-orig)?$", "", base)                      # «.es-orig», «.spa» de los subtítulos
    cabeza = base.split(" - ")[0] if " - " in base else base
    ident = re.sub(r"[^a-z0-9]+", "-", T.plano(cabeza).replace("ñ", "n")).strip("-")[:40]
    return ident or "fuente"


def _leer_origen(origen: Path) -> dict:
    """{nombre de fichero: texto} con los .txt y .vtt de una carpeta o de un zip."""
    out = {}
    if origen.is_dir():
        for f in sorted(origen.rglob("*")):
            if f.suffix.lower() in (".txt", ".vtt") and not f.name.startswith("."):
                out[f.name] = f.read_text(encoding="utf-8", errors="replace")
    elif zipfile.is_zipfile(origen):
        with zipfile.ZipFile(origen) as z:
            for i in z.infolist():
                nombre = i.filename
                if not i.flag_bits & 0x800:                                 # nombre sin marca UTF-8: suele serlo igual
                    try:
                        nombre = nombre.encode("cp437").decode("utf-8")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                if nombre.lower().endswith((".txt", ".vtt")) and not Path(nombre).name.startswith("."):
                    out[Path(nombre).name] = z.read(i).decode("utf-8", errors="replace")
    else:
        raise Rechazo(f"«{origen}» no es una carpeta ni un zip")
    return out


def limpiar(texto: str, ruido: list | None = None) -> str:
    """Quita las etiquetas de ruido y los espacios de más. No toca las palabras."""
    texto = RUIDO.sub(" ", texto)
    for r in ruido or []:
        texto = texto.replace(r, " ")
    return re.sub(r"\s+", " ", texto).strip()


def tramos(texto: str, ruido: list | None = None) -> tuple:
    """(título, [{t, marca, texto, palabras}]) de una transcripción con marcas «[h:mm:ss]» en línea propia."""
    titulo = ""
    m = re.match(r"\s*#\s+(.+)", texto)
    if m:
        titulo, texto = m.group(1).strip(), texto[m.end():]
    out, pos, t, marca = [], 0, 0, "0:00:00"

    def cerrar(hasta: int):
        limpio = limpiar(texto[pos:hasta], ruido)
        if limpio:
            out.append({"t": t, "marca": marca, "texto": limpio, "palabras": len(T.palabras(limpio))})

    for m in MARCA.finditer(texto):
        cerrar(m.start())
        h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
        t, marca, pos = h * 3600 + mi * 60 + s, f"{h}:{mi:02d}:{s:02d}", m.end()
    cerrar(len(texto))
    return titulo, out


def duracion_vtt(vtt: str) -> float:
    """Segundos hasta el final del último subtítulo."""
    fin = 0.0
    for h, mi, s, ms in TIEMPO_VTT.findall(vtt):
        fin = max(fin, int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000)
    return fin


def cargar(slug: str, origen, coleccion: str, tipo: str = "directo", ruido: list | None = None, quien: str = "") -> dict:
    """Carga (o recarga) las fuentes de una colección. Devuelve {cargadas, palabras, ppm_medido, avisos}."""
    if not NOMBRE.match(coleccion or ""):
        raise Rechazo("El nombre de la colección va en minúsculas, con letras, números y guiones")
    tipo = (tipo or "directo").strip().lower()
    ficheros = _leer_origen(Path(os.path.expanduser(str(origen))))
    textos = {n: t for n, t in ficheros.items() if n.lower().endswith(".txt")}
    if not textos:
        raise Rechazo("No hay ningún .txt con transcripciones en el origen")
    subtitulos = {_id(n): t for n, t in ficheros.items() if n.lower().endswith(".vtt")}
    cfg = B.leer(B.home() / "canales" / B.validar_slug(slug) / "canal.json", None)
    if cfg is None:
        raise Rechazo(f"No existe el canal «{slug}»")
    ruido = list(ruido or ((cfg.get("transcripcion") or {}).get("ruido") or []))
    dest = carpeta(slug) / coleccion
    dest.mkdir(parents=True, exist_ok=True)
    nuevas, avisos, vistos = [], [], set()
    for nombre in sorted(textos):
        ident = _id(nombre)
        if ident in vistos:
            avisos.append(f"«{nombre}» repite el identificador «{ident}» y se ha saltado")
            continue
        vistos.add(ident)
        titulo, tr = tramos(textos[nombre], ruido)
        if not tr:
            avisos.append(f"«{nombre}» está vacío")
            continue
        total = sum(x["palabras"] for x in tr)
        dur = duracion_vtt(subtitulos[ident]) if ident in subtitulos else 0.0
        ppm = round(total * 60 / dur) if dur and tipo in GUIONIZADOS else 0
        ficha = {"id": ident, "coleccion": coleccion, "tipo": tipo, "titulo": titulo or Path(nombre).stem,
                 "origen": nombre, "palabras": total, "duracion_s": round(dur or tr[-1]["t"]), "ppm": ppm,
                 "tramos": len(tr)}
        B.escribir(dest / f"{ident}.json", {**ficha, "tramos": tr})
        (dest / f"{ident}.txt").write_text(
            f"# {ficha['titulo']}\n\n" + "\n\n".join(f"[{x['marca']}]\n{x['texto']}" for x in tr) + "\n", encoding="utf-8")
        nuevas.append(ficha)
    # Un fichero que contiene el arranque de varios otros es un compilado: se marca para no contar su material dos veces
    cabezas = {f["id"]: " ".join(T.plano(B.leer(dest / f"{f['id']}.json", {})["tramos"][0]["texto"]).split())[:160]
               for f in nuevas}
    for f in nuevas:
        entero = " ".join(T.plano(x["texto"]) for x in B.leer(dest / f"{f['id']}.json", {})["tramos"])
        entero = " ".join(entero.split())
        dentro = [i for i, c in cabezas.items() if i != f["id"] and len(c) > 60 and c in entero]
        if len(dentro) >= 2:
            f["compilado"] = True
            avisos.append(f"«{f['id']}» contiene {len(dentro)} de las otras fuentes: se marca como compilado y no se usa")
    with B.cerrojo("fuentes"):
        idx = indice(slug)
        idx["fuentes"] = sorted([f for f in idx["fuentes"] if f.get("coleccion") != coleccion] + nuevas,
                                key=lambda f: (f["coleccion"], f["id"]))
        ritmos = [f["ppm"] for f in idx["fuentes"] if f.get("ppm") and not f.get("compilado")]
        idx["ppm_medido"] = round(statistics.median(ritmos)) if ritmos else 0
        idx["actualizado"] = B.ahora()
        B.escribir(carpeta(slug) / "indice.json", idx)
    B.anotar(B.home() / "canales" / slug / "acciones.jsonl",
             {"ts": B.ahora(), "accion": "fuentes-cargar", "coleccion": coleccion, "tipo": tipo, "fuentes": len(nuevas),
              "quien": quien})
    return {"cargadas": len(nuevas), "palabras": sum(f["palabras"] for f in nuevas), "ppm_medido": idx["ppm_medido"],
            "avisos": avisos}


def leer(slug: str, coleccion: str, ident: str) -> dict:
    f = carpeta(slug) / coleccion / f"{ident}.json"
    d = B.leer(f, None)
    if d is None:
        raise Rechazo(f"No existe la fuente «{coleccion}/{ident}»")
    return d


def cita(slug: str, coleccion: str, ident: str, literal: str) -> dict | None:
    """¿Aparece esta cita, tal cual, en la fuente? Devuelve el tramo donde está ({t, marca}) o None. Se compara sin
    tildes ni mayúsculas y con los espacios normalizados: lo que no puede cambiar son las palabras."""
    aguja = " ".join(T.plano(literal).split())
    if len(aguja) < 12:
        return None
    for tr in leer(slug, coleccion, ident)["tramos"]:
        if aguja in " ".join(T.plano(tr["texto"]).split()):
            return {"t": tr["t"], "marca": tr["marca"]}
    return None


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(a) >= 3 and a[0] == "cargar":
            def op(n, d=""):
                return a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d
            r = cargar(a[1], a[2], op("--coleccion"), op("--tipo", "directo"), quien=os.environ.get("HYT_QUIEN", ""))
            print(json.dumps(r, ensure_ascii=False))
        elif len(a) >= 2 and a[0] == "lista":
            idx = indice(a[1])
            for f in idx["fuentes"]:
                ritmo = (f" · {f['ppm']} ppm" if f.get("ppm") else "") + (" · compilado" if f.get("compilado") else "")
                print(f"{f['coleccion']}/{f['id']}  {f['tipo']}  {f['palabras']} palabras{ritmo}  {f['titulo']}")
            print(f"Ritmo de lectura medido: {idx.get('ppm_medido') or 'sin medir'}")
        else:
            print(__doc__)
            return 1
    except Rechazo as e:
        print(f"No se puede: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
