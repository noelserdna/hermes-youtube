"""Las reglas de la revisión mecánica: lo que se comprueba por código, sin modelo, antes de que algo llegue a una
persona. Funciones puras: reciben el contenido y la configuración del canal, devuelven avisos.

Un aviso es {"grave": bool, "codigo": "…", "texto": "…"}. Con un aviso grave el artefacto no se entrega. Los valores
(longitudes, ritmo, listas) son siempre del canal; aquí solo están los tipos de regla y unos valores de partida.
"""
from __future__ import annotations

import importlib.util
import re
import sys
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


T = _cargar("hyt_texto")

BLOQUES = ("intro", "desarrollo-1", "reenganche-1", "conexion", "reenganche-2", "desarrollo-2", "cierre")
PALANCAS = ("afirmacion", "misterio", "contraste", "revelacion", "creencia")
DEFECTO = {"titulo_max": 55, "titulos_presentados": 5, "miniaturas": 3, "miniatura_palabras": 4, "ppm": 150,
           "minutos": [13, 15], "intro_max_palabras": 75, "temas_por_pilar": 3, "frase_media": [11, 16],
           "frase_max": 35, "pct_largas_max": 10, "pct_cortas_min": 25, "muletilla_max": 4,
           "muletillas_total": [0, 99], "gancho_lineas": [2, 6], "presupuesto_pct": 20, "gancho_min": 55}
CIFRA_FUERTE = re.compile(r"\b(mill[oó]n(es)?|billones?|mil|cien(tos)?|por ciento|porcentaje)\b|%", re.I)
MARCA = re.compile(r"\[(\d+)\]")
CAMPOS_MINIATURA = ("angulo", "concepto", "que_se_ve", "composicion", "texto", "reparto", "no_revela",
                    "legible_en_movil", "hipotesis")


def reglas(cfg: dict) -> dict:
    return {**DEFECTO, **((cfg or {}).get("reglas") or {})}


def aviso(grave: bool, codigo: str, texto: str) -> dict:
    return {"grave": bool(grave), "codigo": codigo, "texto": texto}


def nota(avisos: list) -> int:
    """0-100: cuánto le falta a un artefacto. Los graves pesan mucho más."""
    return max(0, 100 - 14 * sum(1 for a in avisos if a["grave"]) - 4 * sum(1 for a in avisos if not a["grave"]))


def _lista(xs: list, n: int = 4) -> str:
    xs = [str(x) for x in xs]
    return ", ".join(f"«{x}»" for x in xs[:n]) + (f" y {len(xs) - n} más" if len(xs) > n else "")


# ── lo que vale para todo ───────────────────────────────────────────────────────────────────────────────────────────
def comunes(texto: str, cfg: dict, donde: str = "") -> list:
    """Contenido excluido, nombres vetados, promesas no permitidas y emojis. Se aplica a todo lo que se entrega."""
    out, en = [], f" en {donde}" if donde else ""
    vistos = set()
    for x in (cfg.get("excluido") or []):
        for nombre, hallado in T.patrones(texto, [x]):
            if (nombre, hallado.lower()) not in vistos:
                vistos.add((nombre, hallado.lower()))
                grave = x.get("grave", True) if isinstance(x, dict) else True
                out.append(aviso(grave, "excluido", f"contenido excluido ({nombre}){en}: «{hallado}»"))
    vetados = T.buscar(texto, cfg.get("nombres_vetados") or [])
    if vetados:
        out.append(aviso(True, "nombre-vetado", f"nombres que no pueden aparecer{en}: {_lista(vetados)}"))
    permite = cfg.get("permite") or {}
    for x in (cfg.get("sin_promesas") or []):
        nombre = x.get("nombre", "") if isinstance(x, dict) else ""
        if nombre in ("empleo", "salario") and permite.get("promesas_empleo"):
            continue
        for n, hallado in T.patrones(texto, [x]):
            out.append(aviso(True, "promesa", f"promesa no permitida ({n}){en}: «{hallado}»"))
    if T.emojis(texto):
        out.append(aviso(True, "emoji", f"lleva emojis{en}"))
    return out


# ── temas ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def temas(lista: list, cfg: dict) -> list:
    r, out = reglas(cfg), []
    pilares = {p["id"] for p in (cfg.get("pilares") or []) if isinstance(p, dict)}
    por_pilar: dict = {}
    for t in lista:
        falta = [k for k in ("pilar", "titulo", "resumen", "origen") if not t.get(k)]
        if falta:
            out.append(aviso(True, "tema-incompleto", f"al tema «{t.get('titulo', '?')}» le falta: {', '.join(falta)}"))
        if pilares and t.get("pilar") not in pilares:
            out.append(aviso(True, "pilar-desconocido", f"«{t.get('titulo', '?')}» va a un pilar que el canal no tiene"))
        por_pilar[t.get("pilar")] = por_pilar.get(t.get("pilar"), 0) + 1
        if len(t.get("titulo") or "") >= r["titulo_max"]:
            out.append(aviso(False, "titulo-largo", f"«{t['titulo']}» pasa del largo de un título"))
        out += comunes(f"{t.get('titulo', '')}. {t.get('resumen', '')}", cfg, "un tema")
    for p, n in por_pilar.items():
        if n > r["temas_por_pilar"]:
            out.append(aviso(True, "pilar-lleno", f"hay {n} temas del pilar «{p}»; el máximo es {r['temas_por_pilar']}"))
    for p in sorted(pilares):
        if por_pilar.get(p, 0) < r["temas_por_pilar"]:
            out.append(aviso(False, "pilar-corto",
                             f"el pilar «{p}» se queda en {por_pilar.get(p, 0)} de {r['temas_por_pilar']} temas"))
    return out


# ── títulos y miniaturas ────────────────────────────────────────────────────────────────────────────────────────────
def titulos(lista: list, cfg: dict, claves: list | None = None) -> list:
    r, out = reglas(cfg), []
    if len(lista) != r["titulos_presentados"]:
        out.append(aviso(True, "titulos-numero", f"hay {len(lista)} títulos; se presentan {r['titulos_presentados']}"))
    for t in lista:
        c = T.titulo(t.get("texto", ""), claves=claves, reglas=r, cliches=cfg.get("titulo_cliches"))
        out += [aviso(True, f"titulo-{k}", f"«{c['titulo']}»: {m}") for k, m in c["fallos"]]
        out += [aviso(False, f"titulo-{k}", f"«{c['titulo']}»: {m}") for k, m in c["avisos"]]
        out += comunes(t.get("texto", ""), cfg, "un título")
    palancas = {t.get("palanca") for t in lista if t.get("palanca")}
    if lista and len(palancas) < min(3, len(lista)):
        out.append(aviso(True, "titulos-palancas", f"los títulos usan {len(palancas)} palancas; hacen falta al menos 3"))
    textos = [T.plano(t.get("texto", "")) for t in lista]
    if len(set(textos)) < len(textos):
        out.append(aviso(True, "titulos-repetidos", "hay títulos repetidos"))
    return out


def miniaturas(lista: list, cfg: dict, tits: list | None = None) -> list:
    r, out = reglas(cfg), []
    if len(lista) != r["miniaturas"]:
        out.append(aviso(True, "miniaturas-numero", f"hay {len(lista)} ideas de miniatura; se presentan {r['miniaturas']}"))
    palabras_titulos = set()
    for t in tits or []:
        palabras_titulos |= set(T.contenido(t.get("texto", "")))
    for m in lista:
        n = m.get("n", "?")
        falta = [k for k in CAMPOS_MINIATURA if k != "texto" and not m.get(k)]
        if falta:
            out.append(aviso(True, "miniatura-incompleta", f"a la miniatura {n} le falta: {', '.join(falta)}"))
        texto = m.get("texto") or ""
        if len(T.palabras(texto)) > r["miniatura_palabras"]:
            out.append(aviso(True, "miniatura-larga",
                             f"el texto de la miniatura {n} tiene {len(T.palabras(texto))} palabras; el máximo es {r['miniatura_palabras']}"))
        comunes_ = set(T.contenido(texto)) & palabras_titulos
        if comunes_:
            out.append(aviso(True, "miniatura-repite",
                             f"la miniatura {n} repite palabras de los títulos: {', '.join(sorted(comunes_))}"))
        todo = " ".join(str(m.get(k, "")) for k in ("que_se_ve", "texto", "texto_alternativo", "reparto", "hipotesis"))
        out += comunes(todo, cfg, f"la miniatura {n}")
    for campo, sacar in (("ángulo", lambda m: m.get("angulo")), ("concepto", lambda m: m.get("concepto")),
                         ("composición", lambda m: (m.get("composicion") or {}).get("tipo")),
                         ("expresión", lambda m: (m.get("presentador") or {}).get("expresion"))):
        valores = [T.plano(str(sacar(m))) for m in lista if sacar(m)]
        if len(valores) > 1 and len(set(valores)) < len(valores):
            out.append(aviso(True, "miniaturas-iguales", f"dos ideas de miniatura comparten {campo}: no son distintas"))
    return out


# ── guion ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def guion(texto: str, cfg: dict, material: set | None = None, escaleta: dict | None = None,
          recientes: list | None = None) -> list:
    """`material` son los números de pieza que existen; `escaleta` da el presupuesto por bloque; `recientes` son las
    primeras frases de los últimos guiones del canal."""
    r, out = reglas(cfg), []
    bl = T.bloques(texto)
    nombres = [n for n, _ in bl]
    faltan = [b for b in BLOQUES if b not in nombres]
    if faltan:
        out.append(aviso(True, "bloque-falta", f"faltan bloques: {', '.join(faltan)}"))
    sobran = [n for n in nombres if n not in BLOQUES]
    if sobran:
        out.append(aviso(True, "bloque-sobra", f"bloques que no son del formato: {', '.join(sobran)}"))
    if not faltan and not sobran and tuple(nombres) != BLOQUES:
        out.append(aviso(True, "bloque-orden", "los bloques no están en su orden"))
    d = dict(bl)
    m = T.medidas(texto, r["ppm"])
    lo, hi = r["ppm"] * r["minutos"][0], r["ppm"] * r["minutos"][1]
    if not lo <= m["palabras"] <= hi:
        out.append(aviso(True, "duracion", f"{m['palabras']} palabras; tiene que estar entre {lo} y {hi} "
                                           f"({r['minutos'][0]}-{r['minutos'][1]} minutos a {r['ppm']} por minuto)"))
    intro = len(T.palabras(T.sin_marcas(d.get("intro", ""))))
    if intro > r["intro_max_palabras"]:
        out.append(aviso(True, "intro-larga", f"la intro tiene {intro} palabras; el máximo es {r['intro_max_palabras']}"))
    vetadas = T.buscar(T.sin_marcas(texto), cfg.get("prohibidas") or [])
    if vetadas:
        out.append(aviso(True, "vetada", f"expresiones que quien presenta no usa: {_lista(vetadas)}"))
    anuncia = T.buscar(T.sin_marcas(d.get("cierre", "")), cfg.get("cierres_prohibidos") or [])
    if anuncia:
        out.append(aviso(True, "cierre-anuncia", f"el cierre anuncia el final o pide algo: {_lista(anuncia)}"))
    raros = T.no_se_lee(texto)
    if raros:
        out.append(aviso(True, "no-se-lee", f"lleva cosas que no se leen en voz alta: {' '.join(raros[:8])}"))
    digitos = T.cifras_en_digitos(texto)
    if digitos:
        out.append(aviso(True, "cifra-digitos", f"cifras en dígitos, y van como se leen: {_lista(digitos)}"))
    # trazabilidad: las marcas existen y toda cifra fuerte lleva una
    usadas = {int(x) for x in MARCA.findall(texto)}
    if material is not None:
        fuera = sorted(usadas - set(material))
        if fuera:
            out.append(aviso(True, "marca-inexistente", f"marcas que no están en el material: {_lista(fuera)}"))
        sin = []
        for _, cuerpo in bl:
            for linea in cuerpo.splitlines():
                if CIFRA_FUERTE.search(linea) and not MARCA.search(linea):
                    sin.append(linea.strip()[:70])
        if sin:
            out.append(aviso(True, "cifra-sin-marca", f"{len(sin)} líneas con una cifra y sin marca de su fuente: {_lista(sin, 2)}"))
    # forma
    largas = [f for f in T.frases(T.sin_marcas(texto)) if len(T.palabras(f)) > r["frase_max"]]
    if largas:
        out.append(aviso(True, "frase-larga", f"{len(largas)} frases de más de {r['frase_max']} palabras: {_lista([f[:60] for f in largas], 2)}"))
    if m["frases"]:
        if not r["frase_media"][0] <= m["media"] <= r["frase_media"][1]:
            out.append(aviso(False, "frase-media", f"media de {m['media']} palabras por frase; lo suyo es {r['frase_media'][0]}-{r['frase_media'][1]}"))
        if m["pct_largas"] > r["pct_largas_max"]:
            out.append(aviso(False, "frases-largas", f"el {m['pct_largas']} % de las frases pasa de 25 palabras"))
        if m["pct_cortas"] < r["pct_cortas_min"]:
            out.append(aviso(False, "frases-cortas", f"solo el {m['pct_cortas']} % de las frases es corto; faltan golpes secos"))
    total, plano_g = 0, T.plano(T.sin_marcas(texto))
    for mu in cfg.get("muletillas") or []:
        base = T.plano(mu).strip("¿?¡! ")
        n = len(re.findall(r"(?<![0-9a-zñ])" + re.escape(base) + r"(?![0-9a-zñ])", plano_g)) if base else 0
        total += n
        if n > r["muletilla_max"]:
            out.append(aviso(False, "muletilla", f"«{mu}» sale {n} veces; el tope es {r['muletilla_max']}"))
    if cfg.get("muletillas") and not r["muletillas_total"][0] <= total <= r["muletillas_total"][1]:
        out.append(aviso(False, "muletillas", f"{total} muletillas en total; lo suyo es entre {r['muletillas_total'][0]} y {r['muletillas_total'][1]}"))
    rep = T.repetidos(texto)
    if rep:
        out.append(aviso(False, "repeticion", f"se repite: {_lista([f'{k} ({v})' for k, v in rep], 3)}"))
    arr = T.arranques_repetidos(texto)
    if arr:
        out.append(aviso(False, "arranque", f"varias frases seguidas empiezan igual: {_lista(arr)}"))
    lineas = [x for x in d.get("cierre", "").splitlines() if x.strip()]
    if d.get("cierre") is not None and "cierre" in d and not r["gancho_lineas"][0] <= len(lineas) <= r["gancho_lineas"][1]:
        out.append(aviso(False, "cierre-lineas", f"el cierre tiene {len(lineas)} líneas; lo suyo es de {r['gancho_lineas'][0]} a {r['gancho_lineas'][1]}"))
    for b in (escaleta or {}).get("bloques") or []:
        pres, real = b.get("palabras"), len(T.palabras(T.sin_marcas(d.get(b.get("id"), ""))))
        if pres and abs(real - pres) > pres * r["presupuesto_pct"] / 100:
            out.append(aviso(False, "presupuesto", f"«{b['id']}» tiene {real} palabras y su presupuesto era {pres}"))
    primeras = T.frases(T.sin_marcas(d.get("intro", "")))
    if primeras:
        g = T.gancho(primeras[0])
        if g["nota"] < r["gancho_min"]:
            out.append(aviso(False, "apertura-floja", f"la primera frase puntúa {g['nota']}: {g['arreglo']}"))
        for otra in recientes or []:
            if T.similitud(primeras[0], otra) >= 0.6:
                out.append(aviso(False, "apertura-repetida", f"la apertura se parece a la de otro guion: «{otra[:60]}»"))
                break
    return out + comunes(T.sin_marcas(texto), cfg, "el guion")


# ── descripción ─────────────────────────────────────────────────────────────────────────────────────────────────────
def descripcion(texto: str, cfg: dict, claves: list | None = None, duracion: float | None = None) -> list:
    out = []
    caps = T.leer_capitulos(texto)
    resumen = re.split(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}\s", texto, maxsplit=1, flags=re.M)[0].strip()
    if not resumen:
        out.append(aviso(True, "sin-resumen", "la descripción no tiene resumen"))
    out += [aviso(True, "capitulos", f) for f in T.capitulos_validos(caps, duracion)]
    if claves and resumen:
        cabeza = T.plano(" ".join(resumen.splitlines()[:2]))
        if not any(T.plano(c) in cabeza for c in claves):
            out.append(aviso(False, "descripcion-clave", "las dos primeras líneas no llevan ninguna palabra clave del título"))
    genericos = [t for _, t in caps if T.plano(t).replace(" ", "-") in BLOQUES or re.match(r"(desarrollo|bloque|parte)\b", T.plano(t))]
    if genericos:
        out.append(aviso(True, "capitulo-generico", f"capítulos con nombre de bloque en vez de contenido: {_lista(genericos)}"))
    return out + comunes(texto, cfg, "la descripción")
