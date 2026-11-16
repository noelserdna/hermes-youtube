"""Medidas y comprobaciones de texto sin modelo: lo que la revisión mecánica necesita para juzgar un título, una
miniatura, un guion o una descripción. Funciones puras: reciben texto y reglas, devuelven datos. No leen ni escriben
ficheros y no saben nada de ningún canal.

  hyt_texto.py medir <fichero>              medidas de un texto hablado (palabras, frases, minutos)
  hyt_texto.py titulo "<título>" [--miniatura "<texto>"] [--clave palabra]…
  hyt_texto.py gancho "<primera frase>"

Las comprobaciones de título y miniatura como pareja y la nota del gancho se inspiran en youtube-agent-skill (MIT),
reescritas para el español.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata

# ── piezas básicas ──────────────────────────────────────────────────────────────────────────────────────────────────
PALABRA = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[.,][0-9]+)*", re.UNICODE)
FIN_FRASE = re.compile(r"(?<=[.!?…])[\"»”')\]]*\s+(?=[¿¡\"«“(\[]*[0-9A-ZÁÉÍÓÚÜÑ])")
VACIAS = set("""a al algo ante aquí así aun aún bien cada como con contra cual cuando de del desde donde dos el ella ellas
ellos en entre era es esa ese eso esta este esto está están fue ha han hay la las le les lo los me mi mis más muy ni no
nos o os para pero por porque que qué se sea ser si sí sin sobre su sus también te tu tus un una uno unas unos va vas
y ya yo él tú""".split())


def plano(t: str) -> str:
    """Minúsculas y sin tildes (la ñ se conserva): para comparar sin que una tilde cambie el resultado."""
    t = unicodedata.normalize("NFD", t.lower()).replace("ñ", "ñ")
    return unicodedata.normalize("NFC", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def palabras(t: str) -> list:
    return PALABRA.findall(t)


def contenido(t: str) -> list:
    """Palabras con significado, en plano: sin artículos, preposiciones ni pronombres."""
    return [w for w in (plano(x) for x in palabras(t)) if w not in VACIAS and len(w) > 1]


def frases(t: str) -> list:
    """Parte un texto hablado en frases. Los saltos de línea también cortan."""
    out = []
    for linea in t.splitlines():
        linea = linea.strip()
        if linea:
            out += [f.strip() for f in FIN_FRASE.split(linea) if f.strip()]
    return out


def sin_marcas(t: str) -> str:
    """Quita lo que no se lee en voz alta: cabeceras, marcas de cita [n] y comentarios HTML."""
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"^\s*#{1,6}\s.*$", "", t, flags=re.M)
    t = re.sub(r"\s*\[\d+\]", "", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def minutos(n_palabras: int, ppm: int) -> float:
    return round(n_palabras / ppm, 2) if ppm else 0.0


def mmss(segundos: float) -> str:
    s = int(round(segundos))
    return f"{s // 60:02d}:{s % 60:02d}"


# ── medidas de un texto hablado ─────────────────────────────────────────────────────────────────────────────────────
def medidas(t: str, ppm: int = 150) -> dict:
    fr = frases(sin_marcas(t))
    largos = sorted(len(palabras(f)) for f in fr)
    n = len(largos)
    total = sum(largos)
    if not n:
        return {"palabras": 0, "frases": 0, "media": 0, "mediana": 0, "max": 0, "pct_cortas": 0, "pct_largas": 0,
                "racha_largas": 0, "minutos": 0.0}
    racha = mejor = 0
    for f in fr:
        racha = racha + 1 if len(palabras(f)) > 25 else 0
        mejor = max(mejor, racha)
    return {"palabras": total, "frases": n, "media": round(total / n, 1),
            "mediana": largos[n // 2] if n % 2 else round((largos[n // 2 - 1] + largos[n // 2]) / 2, 1),
            "max": largos[-1], "pct_cortas": round(100 * sum(1 for x in largos if x <= 8) / n),
            "pct_largas": round(100 * sum(1 for x in largos if x > 25) / n), "racha_largas": mejor,
            "minutos": minutos(total, ppm)}


def bloques(guion: str) -> list:
    """[(nombre, texto)] de un guion con sus bloques marcados como «## nombre». Lo anterior al primero se ignora."""
    out, nombre, buf = [], None, []
    for linea in guion.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", linea)
        if m:
            if nombre is not None:
                out.append((nombre, "\n".join(buf).strip()))
            nombre, buf = plano(m.group(1)).replace(" ", "-"), []
        elif nombre is not None:
            buf.append(linea)
    if nombre is not None:
        out.append((nombre, "\n".join(buf).strip()))
    return out


def numerar(guion: str) -> list:
    """[(n, bloque, frase)]: las frases del guion numeradas de corrido, para que un comentario pueda señalar una."""
    out, n = [], 0
    for nombre, texto in bloques(guion) or [("", guion)]:
        for f in frases(sin_marcas(texto)):
            n += 1
            out.append((n, nombre, f))
    return out


# ── búsquedas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def buscar(t: str, expresiones: list) -> list:
    """Expresiones de una lista que aparecen en el texto, como palabras enteras y sin distinguir tildes ni mayúsculas.
    Unos puntos suspensivos al final de una expresión («en el vertiginoso mundo de…») valen por cualquier continuación."""
    p, out = plano(t), []
    for e in expresiones:
        base = plano(e).rstrip(".… ").strip()
        if base and re.search(r"(?<![0-9a-zñ])" + re.escape(base) + r"(?![0-9a-zñ])", p):
            out.append(e)
    return out


def patrones(t: str, lista: list) -> list:
    """Patrones (expresiones regulares) de una lista que casan con el texto. Cada elemento es una cadena o
    {"patron": "...", "nombre": "..."}; se devuelve [(nombre, lo encontrado)]."""
    out = []
    for x in lista:
        pat, nombre = (x.get("patron"), x.get("nombre") or x.get("patron")) if isinstance(x, dict) else (x, x)
        try:
            m = re.search(pat, t, re.I)
        except re.error:
            continue
        if m:
            out.append((nombre, m.group(0)))
    return out


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
NO_SE_LEE = re.compile(r"https?://\S+|www\.\S+|[()\[\]{};@#%&=+*/\\<>|~^$€]")


def emojis(t: str) -> list:
    return EMOJI.findall(t)


def no_se_lee(t: str) -> list:
    """Lo que un teleprompter no debería llevar: URL, paréntesis, punto y coma, símbolos."""
    return sorted(set(NO_SE_LEE.findall(sin_marcas(t))))


def cifras_en_digitos(t: str) -> list:
    """Números escritos con cifras: en un guion van como se leen («veintiséis millones»)."""
    return re.findall(r"(?<![A-Za-z])\d[\d.,]*", sin_marcas(t))


def repetidos(t: str, n: int = 3, tope: int = 3) -> list:
    """Secuencias de n palabras con significado que se repiten más de `tope` veces."""
    w = contenido(sin_marcas(t))
    cuenta: dict = {}
    for i in range(len(w) - n + 1):
        k = " ".join(w[i:i + n])
        cuenta[k] = cuenta.get(k, 0) + 1
    return sorted(((k, v) for k, v in cuenta.items() if v > tope), key=lambda x: -x[1])


def arranques_repetidos(t: str, tope: int = 3) -> list:
    """Frases seguidas que empiezan igual (las dos primeras palabras) más de `tope` veces."""
    out, previo, racha = [], None, 0
    for f in frases(sin_marcas(t)):
        ini = " ".join(plano(x) for x in palabras(f)[:2])
        racha = racha + 1 if ini and ini == previo else 1
        if racha == tope + 1:
            out.append(ini)
        previo = ini
    return out


def similitud(a: str, b: str, genericas: set | None = None) -> float:
    """Parecido entre dos textos cortos (0-1) por palabras con significado en común, sin las propias del canal."""
    g = {plano(x) for x in (genericas or ())}
    A, B = set(contenido(a)) - g, set(contenido(b)) - g
    return round(len(A & B) / len(A | B), 2) if A and B else 0.0


def cambios(antes: str, despues: str) -> dict:
    """Qué frases cambian entre dos versiones de un guion: {pct, nuevas, quitadas}."""
    import difflib
    a, d = [f for _, _, f in numerar(antes)], [f for _, _, f in numerar(despues)]
    nuevas, quitadas = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, d, autojunk=False).get_opcodes():
        if op != "equal":
            quitadas += a[i1:i2]
            nuevas += [(j + 1, d[j]) for j in range(j1, j2)]
    return {"pct": round(100 * len(nuevas) / len(d)) if d else 0, "nuevas": nuevas, "quitadas": quitadas}


# ── título y miniatura, como pareja ─────────────────────────────────────────────────────────────────────────────────
VAGAS = set("""increible alucinante brutal definitivo definitiva secreto secretos mejor mejores ultimo ultima
revolucionario revolucionaria epico epica perfecto perfecta completo completa todo impresionante""".split())
MOVIL = 40   # caracteres que suele enseñar la página de inicio en el móvil


def titulo(t: str, miniatura: str = "", claves: list | None = None, reglas: dict | None = None,
           cliches: list | None = None) -> dict:
    """Comprueba un título (y su pareja con el texto de la miniatura). Devuelve {chars, movil, fallos, avisos}:
    los fallos impiden presentarlo; los avisos se enseñan a quien decide."""
    r = reglas or {}
    tope, t = int(r.get("titulo_max") or 55), t.strip()
    fallos, avisos = [], []
    n = len(t)
    if n >= tope:
        fallos.append(("largo", f"{n} caracteres; el máximo del canal es menos de {tope}"))
    visto = t if n <= MOVIL else t[:MOVIL].rsplit(" ", 1)[0] + "…"
    encontrados = buscar(t, cliches or [])
    if encontrados:
        fallos.append(("cliche", "fórmula gastada: " + ", ".join(encontrados)))
    if emojis(t):
        fallos.append(("emoji", "lleva emojis"))
    gritos = [w for w in t.split() if len(w) > 3 and w.isupper()]
    if len(gritos) > 2:
        avisos.append(("mayusculas", f"{len(gritos)} palabras en mayúsculas"))
    vagas = [w for w in contenido(t) if w in VAGAS]
    if vagas:
        avisos.append(("vago", "palabras vagas: " + ", ".join(sorted(set(vagas)))))
    if claves:
        cabeza = plano(t[:25])
        if not any(plano(c) in cabeza for c in claves):
            avisos.append(("clave", "ninguna palabra clave en los primeros 25 caracteres"))
        elif n > MOVIL and not any(plano(c) in plano(visto) for c in claves):
            avisos.append(("movil", f"en el móvil se lee «{visto}» y se pierde la palabra clave"))
    if miniatura:
        comunes = set(contenido(t)) & set(contenido(miniatura))
        if comunes:
            fallos.append(("repite", "la miniatura repite el título en: " + ", ".join(sorted(comunes))))
        if len(palabras(miniatura)) > int(r.get("miniatura_palabras") or 4):
            fallos.append(("miniatura-larga", f"{len(palabras(miniatura))} palabras en la miniatura"))
    return {"titulo": t, "chars": n, "movil": visto, "fallos": fallos, "avisos": avisos}


# ── la apertura ─────────────────────────────────────────────────────────────────────────────────────────────────────
TU = re.compile(r"\b(tú|tu|tus|te|ti|contigo|vas|tienes|sabes|quieres|puedes|haces|crees|estás|eres|necesitas)\b", re.I)
RIESGO = re.compile(r"\b(pierdes?|perder|perdiendo|falla[sn]?|fallo|error(es)?|equivoca\w*|cuesta|coste|riesgo|antes de|"
                    r"deja de|nunca|sin darte cuenta|tarde|mal|peor|problema)\b", re.I)
INTRIGA = re.compile(r"\b(por qué|cómo|qué|cuál|hasta que|pero|nadie|casi|excepto|salvo|motivo|razón|en realidad|"
                     r"no es|lo que)\b", re.I)
CONCRETO = re.compile(r"\d|\b(un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|cien|mil|millón|millones)\b", re.I)
SE_RESPONDE = re.compile(r"\b(porque|así que|lo que significa)\b", re.I)
ARREGLO = {"concrecion": "cambia un adjetivo por una cifra, un nombre o una fecha",
           "apelacion": "habla de tú en las primeras seis palabras",
           "en_juego": "di qué le cuesta seguir como hasta ahora",
           "curiosidad": "quita la mitad de la frase que se responde sola",
           "brevedad": "de 9 a 24 palabras: léela en voz alta y para donde te quedes sin aire"}


def gancho(t: str) -> dict:
    """Nota orientativa (0-100) de una frase de apertura en cinco propiedades. La nota final pesa un 60 % la media y
    un 40 % la peor: una apertura falla por su punto más débil. Sirve para mirar otra vez una apertura floja, no para
    predecir un éxito."""
    w = palabras(t)
    if not w:
        return {"nota": 0, "partes": {}, "debil": "", "arreglo": ""}
    lim = lambda x: max(0, min(100, int(x)))
    toks = t.split()   # nombres propios: mayúscula inicial que no abre frase
    propios = sum(1 for a, x in zip(toks, toks[1:]) if x[:1].isupper() and a[-1:] not in ".!?…")
    vagas = sum(1 for x in contenido(t) if x in VAGAS)
    n = len(w)
    partes = {
        "concrecion": lim(34 + 22 * len(CONCRETO.findall(t)) + min(18, 6 * propios) - 16 * vagas),
        "apelacion": lim(26 + 20 * len(TU.findall(t)) + (30 if TU.search(" ".join(t.split()[:6])) else 0)),
        "en_juego": lim(22 + 26 * len(RIESGO.findall(t)) + (14 if CONCRETO.search(t) else 0)),
        "curiosidad": lim(24 + 17 * len(INTRIGA.findall(t)) + (18 if t.strip().endswith("?") else 0)
                          - (18 if SE_RESPONDE.search(t) else 0)),
        "brevedad": 100 if 9 <= n <= 24 else lim(100 - (9 - n) * 11) if n < 9 else max(10, lim(100 - (n - 24) * 7)),
    }
    v = list(partes.values())
    debil = min(partes, key=partes.get)
    return {"nota": round(0.6 * sum(v) / len(v) + 0.4 * min(v)), "partes": partes, "debil": debil,
            "arreglo": ARREGLO[debil]}


# ── capítulos ───────────────────────────────────────────────────────────────────────────────────────────────────────
MIN_CAPITULOS, MIN_SEGUNDOS = 3, 10


def capitulos_de_bloques(bl: list, ppm: int) -> list:
    """[(segundo, título)] a partir de [(título, palabras)]: los minutos se calculan, no se estiman a ojo."""
    out, acumulado = [], 0
    for tit, n in bl:
        out.append((round(acumulado * 60 / ppm) if ppm else 0, tit))
        acumulado += n
    return out


def leer_capitulos(descripcion: str) -> list:
    """[(segundo, título)] de las líneas «MM:SS Título» (o «H:MM:SS Título») de una descripción."""
    out = []
    for m in re.finditer(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+(\S.*?)\s*$", descripcion, re.M):
        h, mi, s, tit = m.groups()
        out.append((int(h or 0) * 3600 + int(mi) * 60 + int(s), tit))
    return out


def capitulos_validos(caps: list, duracion: float | None = None) -> list:
    """Las reglas de YouTube para que una lista se convierta en capítulos. Devuelve los fallos (vacío = válida)."""
    fallos = []
    if len(caps) < MIN_CAPITULOS:
        fallos.append(f"hay {len(caps)} capítulos; YouTube pide al menos {MIN_CAPITULOS}")
    if caps and caps[0][0] != 0:
        fallos.append("el primer capítulo no empieza en 00:00")
    tiempos = [c[0] for c in caps] + ([duracion] if duracion else [])
    if any(b <= a for a, b in zip(tiempos, tiempos[1:])):
        fallos.append("los capítulos no van en orden creciente")
    elif any(b - a < MIN_SEGUNDOS for a, b in zip(tiempos, tiempos[1:])):
        fallos.append(f"algún capítulo dura menos de {MIN_SEGUNDOS} segundos")
    return fallos


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) >= 2 and a[0] == "medir":
        print(json.dumps(medidas(open(a[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
    elif len(a) >= 2 and a[0] == "titulo":
        mini = a[a.index("--miniatura") + 1] if "--miniatura" in a else ""
        claves = [a[i + 1] for i, x in enumerate(a) if x == "--clave" and i + 1 < len(a)]
        print(json.dumps(titulo(a[1], mini, claves), ensure_ascii=False, indent=1))
    elif len(a) >= 2 and a[0] == "gancho":
        print(json.dumps(gancho(a[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
