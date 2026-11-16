"""Pasos de código alrededor de las etapas: lo que no se deja a un modelo.

Antes de una etapa («prepara») el código deja en la carpeta del encargo lo que el agente necesita: la fuente, el
inventario, las referencias de oficio, la voz, la elección de la persona o la lista de ajustes. Así el agente trabaja
solo con lo que tiene delante y no hace falta darle acceso al resto del canal.

Después de una etapa («tras») el código comprueba y transforma su salida: valida que cada cita aparece tal cual en su
fuente, selecciona temas y títulos con las notas, calcula los minutos de los capítulos y monta el paquete.

Cada paso recibe (canal, carpeta del encargo, encargo). Un «prepara» puede devolver {"saltar": motivo}; un «tras»,
{"fallo": motivo} o {"resumen": texto}.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
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


B = _cargar("hyt_base")
C = _cargar("hyt_canales")
PL = _cargar("hyt_pipelines")
F = _cargar("hyt_fuentes")
T = _cargar("hyt_texto")
R = _cargar("hyt_reglas")
Rechazo = B.Rechazo
CRITICOS = (("verificacion.json", "verificacion"), ("voz.json", "voz"), ("retencion.json", "retencion"), ("cierre.json", "cierre"))


def _json(f: Path, defecto=None):
    """Lee un JSON escrito por un agente: tolera que venga envuelto en una valla de código."""
    try:
        t = f.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return defecto
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        return defecto


def _guardar(f: Path, datos) -> None:
    f.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def inventario(slug: str) -> dict:
    return B.leer(C.carpeta(slug) / "inventario.json", None) or {"piezas": [], "contradicciones": []}


def _partir_fuente(ref: str) -> tuple:
    col, _, ident = (ref or "").partition("/")
    if not col or not ident:
        raise Rechazo(f"la fuente «{ref}» no tiene la forma <colección>/<id>")
    return col, ident


# ── antes de la etapa ───────────────────────────────────────────────────────────────────────────────────────────────
def p_fuente(slug: str, d: Path, enc: dict) -> dict:
    """La transcripción que toca, dentro del encargo, y las pistas de corrección del canal."""
    col, ident = _partir_fuente((enc.get("params") or {}).get("fuente", ""))
    origen = F.carpeta(slug) / col / f"{ident}.txt"
    if not origen.exists():
        raise Rechazo(f"no existe la fuente «{col}/{ident}»; cárgala antes con «hyt fuentes cargar»")
    shutil.copyfile(origen, d / "fuente.txt")
    cfg = C.leer(slug)
    _guardar(d / "pistas.json", {"fuente": f"{col}/{ident}",
                                 "correcciones": (cfg.get("transcripcion") or {}).get("correcciones") or {}})
    return {}


def p_fuentes(slug: str, d: Path, enc: dict) -> dict:
    """Todas las fuentes del canal (menos los compilados), dentro del encargo: para volver al original."""
    dest = d / "fuentes"
    dest.mkdir(exist_ok=True)
    idx = [f for f in F.indice(slug)["fuentes"] if not f.get("compilado")]
    if not idx:
        raise Rechazo("el canal no tiene fuentes cargadas")
    for f in idx:
        (dest / f["coleccion"]).mkdir(exist_ok=True)
        shutil.copyfile(F.carpeta(slug) / f["coleccion"] / f"{f['id']}.txt", dest / f["coleccion"] / f"{f['id']}.txt")
    _guardar(dest / "indice.json", {"fuentes": idx})
    return {}


def banco(slug: str) -> list:
    """Lo ya propuesto y lo ya publicado: [{titulo, estado}]. El último estado de cada título manda."""
    ult: dict = {}
    f = C.carpeta(slug) / "temas.jsonl"
    if f.exists():
        for linea in f.read_text(encoding="utf-8").splitlines():
            try:
                x = json.loads(linea)
            except ValueError:
                continue
            if x.get("titulo"):
                ult[T.plano(x["titulo"])] = {"titulo": x["titulo"], "estado": x.get("estado", "propuesta"),
                                             "pilar": x.get("pilar", ""), "encargo": x.get("encargo", "")}
    for v in (B.leer(C.carpeta(slug) / "videos.json", None) or {}).get("publicados", []):
        if v.get("titulo"):
            ult[T.plano(v["titulo"])] = {"titulo": v["titulo"], "estado": "publicado", "pilar": v.get("pilar", "")}
    return list(ult.values())


def p_inventario(slug: str, d: Path, enc: dict) -> dict:
    """El inventario del canal (sin las citas, que no hacen falta para idear) y el banco de ideas."""
    inv = inventario(slug)
    if not inv["piezas"]:
        raise Rechazo("el canal no tiene inventario; lanza antes la pipeline «inventario» sobre sus fuentes")
    ligero = [{k: p.get(k) for k in ("id", "tipo", "pilar", "dicho", "palabras", "fuente", "marca", "usado_en")}
              for p in inv["piezas"]]
    _guardar(d / "inventario.json", {"piezas": ligero, "contradicciones": inv.get("contradicciones") or []})
    _guardar(d / "banco.json", {"ideas": banco(slug)})
    return {}


def p_referencias(slug: str, d: Path, enc: dict) -> dict:
    """Las guías de oficio del plugin, dentro del encargo."""
    origen = PL.raiz() / "referencias"
    if origen.is_dir():
        shutil.copytree(origen, d / "referencias", dirs_exist_ok=True)
    return {}


def p_voz(slug: str, d: Path, enc: dict) -> dict:
    """La guía de voz del canal y fuentes enteras donde habla quien presenta, como ejemplo."""
    wiki = C.carpeta(slug) / "wiki" / "concepts" / "voz.md"
    if wiki.exists():
        shutil.copyfile(wiki, d / "voz-canal.md")
    idx = F.indice(slug)["fuentes"]
    validas = {f"{f['coleccion']}/{f['id']}": f for f in idx if not f.get("compilado")}
    elegidas = []
    if wiki.exists():
        m = re.search(r"^## Ejemplos completos\s*$(.*?)(?=^## |\Z)", wiki.read_text(encoding="utf-8"), re.M | re.S)
        elegidas = [x for x in re.findall(r"[a-z0-9-]+/[a-z0-9-]+", m.group(1) if m else "") if x in validas]
    if not elegidas:   # sin perfil de voz todavía: las fuentes guionizadas, que son las que más se parecen a un guion
        elegidas = [k for k, f in validas.items() if f.get("ppm")]
    ej = d / "ejemplos"
    ej.mkdir(exist_ok=True)
    for ref in elegidas[:3]:
        col, ident = ref.split("/")
        shutil.copyfile(F.carpeta(slug) / col / f"{ident}.txt", ej / f"{col}-{ident}.txt")
    rec = C.carpeta(slug) / "aperturas.jsonl"
    recientes = [json.loads(x) for x in rec.read_text(encoding="utf-8").splitlines()[-10:]] if rec.exists() else []
    _guardar(d / "aperturas-recientes.json", {"aperturas": recientes})
    return {}


def _campo(texto: str, nombre: str) -> str:
    m = re.search(rf"^\s*{nombre}\s*[:=]\s*(.+?)\s*$", texto or "", re.I | re.M)
    return m.group(1).strip() if m else ""


def p_eleccion(slug: str, d: Path, enc: dict) -> dict:
    """La pareja elegida por la persona, con su promesa: lo que el guion tiene que cumplir.

    La elección llega como texto: «titulo: 2» (o el título escrito), «miniatura: 1», «nota: …», «destino: …». Lo que
    no se indique toma la recomendación. Sin opciones previas (un guion lanzado suelto), el título es el tema."""
    if (d / "eleccion.json").exists():
        return {}
    params = enc.get("params") or {}
    op = _json(d / "opciones.json", None)
    texto = enc.get("eleccion") or ((d / "eleccion.md").read_text(encoding="utf-8") if (d / "eleccion.md").exists() else "")
    cfg, avisos = C.leer(slug), []
    if not op:
        el = {"titulo": params.get("titulo") or params.get("tema", ""), "miniatura": None,
              "promesa": params.get("promesa") or params.get("tema", ""), "palabras_clave": [], "propio": True}
    else:
        rec, brief = op.get("recomendacion") or {}, op.get("brief") or {}
        tits = {str(t["n"]): t for t in op.get("titulos") or []}
        minis = {str(m["n"]): m for m in op.get("miniaturas") or []}
        t_txt, m_txt = _campo(texto, "t[ií]tulo"), _campo(texto, "miniatura")
        propio = bool(t_txt) and t_txt not in tits
        titulo = t_txt if propio else (tits.get(t_txt) or tits.get(str(rec.get("titulo"))) or next(iter(tits.values()), {})).get("texto", "")
        mini = minis.get(m_txt) or minis.get(str(rec.get("miniatura"))) or next(iter(minis.values()), None)
        if mini and _campo(texto, "nota"):
            mini = {**mini, "nota_de_la_persona": _campo(texto, "nota")}
        el = {"titulo": titulo, "miniatura": mini, "promesa": brief.get("promesa", ""),
              "palabras_clave": brief.get("palabras_clave") or [], "propio": propio}
        if propio:   # un título escrito por la persona se comprueba y se avisa, pero no se bloquea
            c = T.titulo(titulo, (mini or {}).get("texto", ""), el["palabras_clave"], R.reglas(cfg), cfg.get("titulo_cliches"))
            avisos = [m for _, m in c["fallos"] + c["avisos"]] + [a["texto"] for a in R.comunes(titulo, cfg, "el título")]
    # A dónde lleva el cierre: al vídeo que indicó la persona; si no, a otro tema ya elegido y sin publicar; si no hay
    # ninguno, a los próximos vídeos del canal sin nombrar uno.
    el["destino"] = _campo(texto, "destino") or params.get("destino", "")
    el["destino_tipo"] = "indicado" if el["destino"] else "general"
    if not el["destino"]:
        try:
            el["destino"] = _cargar("hyt_videos").siguiente(slug, excepto=enc.get("id", ""))
        except Exception:   # noqa: BLE001 — sin lista de vídeos, el cierre es general
            el["destino"] = ""
        if el["destino"]:
            el["destino_tipo"] = "otro-tema"
    el["avisos"] = avisos
    if not el["titulo"]:
        raise Rechazo("no hay título elegido ni tema del que partir")
    _guardar(d / "eleccion.json", el)
    return {}


def p_ajustes(slug: str, d: Path, enc: dict) -> dict:
    """La lista de cambios que hay que aplicar al guion, frase por frase. Reúne lo que pidieron los críticos (solo la
    primera vez), lo que falla en la revisión por código, lo que decidió quien verificó los datos y el comentario de
    la persona que pidió rehacer. Si no hay nada que cambiar, la etapa se salta."""
    est = d / ".estado"
    est.mkdir(exist_ok=True)
    memo = B.leer(est / "ajustes.json", None) or {"pasadas": 0, "vistos": []}
    items = []
    if memo["pasadas"] == 0:
        for fichero, origen in CRITICOS:
            for c in (_json(d / fichero, {}) or {}).get("cambios") or []:
                if isinstance(c, dict) and c.get("frase"):
                    items.append({"origen": origen, **{k: c.get(k, "") for k in ("bloque", "frase", "motivo", "quedaria")}})
    guion = (d / "guion.md").read_text(encoding="utf-8") if (d / "guion.md").exists() else ""
    if guion:
        mat = {int(x["n"]) for x in (_json(d / "material.json", {}) or {}).get("material") or [] if str(x.get("n", "")).isdigit()}
        for a in R.guion(guion, C.leer(slug), mat or None, _json(d / "escaleta.json", None)):
            if a["grave"]:
                items.append({"origen": "revision", "bloque": "", "frase": "", "motivo": a["texto"], "quedaria": ""})

    def nuevo(clave: str) -> bool:
        h = hashlib.sha256(clave.encode()).hexdigest()[:16]
        if h in memo["vistos"]:
            return False
        memo["vistos"].append(h)
        return True

    for dato in (_json(d / "datos.json", {}) or {}).get("datos") or []:
        if dato.get("estado") in ("corregido", "eliminado") and nuevo(f"dato:{dato.get('id')}:{dato.get('estado')}:{dato.get('valor', '')}"):
            motivo = (f"dato corregido por una persona: ahora es «{dato.get('valor', '')}»" if dato["estado"] == "corregido"
                      else "dato eliminado por una persona: quita la frase o rehazla sin él")
            items.append({"origen": "datos", "bloque": "", "frase": dato.get("frase", ""), "motivo": f"{dato.get('dato', '')}: {motivo}", "quedaria": ""})
    fb = est / "feedback-ajustar.txt"
    if fb.exists() and fb.read_text().strip() and nuevo("persona:" + fb.read_text()):
        items.append({"origen": "persona", "bloque": "", "frase": "", "motivo": fb.read_text().strip(), "quedaria": ""})
    memo["pasadas"] += 1
    B.escribir(est / "ajustes.json", memo)
    _guardar(d / "ajustes.json", {"ajustes": items})
    if guion:
        shutil.copyfile(d / "guion.md", est / f"guion-antes-{memo['pasadas']}.md")
    return {} if items else {"saltar": "no hay nada que ajustar"}


# ── después de la etapa ─────────────────────────────────────────────────────────────────────────────────────────────
def t_piezas(slug: str, d: Path, enc: dict) -> dict:
    """Solo entran al inventario las piezas cuya cita aparece tal cual en la fuente."""
    datos = _json(d / "piezas.json", None)
    if not isinstance(datos, dict) or not isinstance(datos.get("piezas"), list):
        return {"fallo": "piezas.json no tiene el formato pedido"}
    ref = (enc.get("params") or {}).get("fuente") or datos.get("fuente", "")
    col, ident = _partir_fuente(ref)
    buenas, malas = [], 0
    for p in datos["piezas"]:
        donde = F.cita(slug, col, ident, str(p.get("cita", ""))) if isinstance(p, dict) else None
        if not donde or not p.get("dicho"):
            malas += 1
            continue
        buenas.append({"tipo": p.get("tipo", ""), "pilar": p.get("pilar", ""), "habla": p.get("habla", ""),
                       "cita": p["cita"], "dicho": p["dicho"], "palabras": int(p.get("palabras") or 0),
                       "fuente": f"{col}/{ident}", "marca": donde["marca"], "usado_en": []})
    if datos["piezas"] and malas > len(datos["piezas"]) / 2:
        return {"fallo": f"{malas} de {len(datos['piezas'])} piezas llevan una cita que no está en la fuente"}
    with B.cerrojo("inventario"):
        inv = inventario(slug)
        resto = [p for p in inv["piezas"] if p.get("fuente") != f"{col}/{ident}"]
        n = max([int(p["id"][1:]) for p in resto if re.match(r"^p\d+$", p.get("id", ""))] or [0])
        for i, p in enumerate(buenas, 1):
            p["id"] = f"p{n + i:04d}"
        inv["piezas"] = resto + buenas
        inv["contradicciones"] = [c for c in inv.get("contradicciones") or [] if c.get("fuente") != f"{col}/{ident}"] + \
                                 [{**c, "fuente": f"{col}/{ident}"} for c in datos.get("contradicciones") or [] if isinstance(c, dict)]
        inv["actualizado"] = B.ahora()
        B.escribir(C.carpeta(slug) / "inventario.json", inv)
    vetados = [str(x).strip() for x in datos.get("nombres_vetados") or [] if str(x).strip()]
    if vetados:
        cfg = C.leer(slug)
        todos = sorted(set(cfg.get("nombres_vetados") or []) | set(vetados))
        if todos != sorted(cfg.get("nombres_vetados") or []):
            C.config(slug, "nombres_vetados", todos, "inventario")
    return {"resumen": f"{len(buenas)} piezas al inventario de {col}/{ident}" + (f"; {malas} descartadas por cita no literal" if malas else "")}


def t_seleccionar(slug: str, d: Path, enc: dict) -> dict:
    """De los candidatos y sus notas a la propuesta: orden, vetos, cupo por pilar, material suficiente y parecidos."""
    cand = (_json(d / "candidatos.json", {}) or {}).get("candidatos")
    notas = {n.get("id"): n for n in (_json(d / "puntuacion.json", {}) or {}).get("notas") or [] if isinstance(n, dict)}
    if not isinstance(cand, list) or not cand:
        return {"fallo": "candidatos.json no trae candidatos"}
    if not notas:
        return {"fallo": "puntuacion.json no trae notas"}
    cfg = C.leer(slug)
    r = R.reglas(cfg)
    piezas = {p["id"]: p for p in inventario(slug)["piezas"]}
    # Lo que citan las piezas es un índice, no el guion: la etapa de documentar vuelve a las fuentes. Aquí solo se
    # descarta lo que claramente no tiene de dónde salir.
    minimo, min_piezas = int(r.get("material_min") or 300), int(r.get("material_piezas_min") or 3)
    todos = [c for c in cand if isinstance(c, dict) and c.get("titulo")]
    frec: dict = {}
    for c in todos:
        for w in set(T.contenido(c["titulo"])):
            frec[w] = frec.get(w, 0) + 1
    genericas = {w for w, n in frec.items() if n > len(todos) * 0.3}   # las palabras del canal no distinguen un tema
    previos = [p for p in banco(slug) if not enc.get("id") or p.get("encargo") != enc.get("id")]   # no contra sí misma
    validos, descartes = [], []
    for c in todos:
        n = notas.get(c.get("id"))
        if not n:
            descartes.append({**c, "motivo": "sin nota"})
            continue
        if str(n.get("veto") or "").strip():
            descartes.append({**c, "motivo": f"veto: {n['veto']}"})
            continue
        suyas = [piezas[i] for i in c.get("piezas") or [] if i in piezas]
        material = sum(int(p.get("palabras") or 0) for p in suyas)
        if material < minimo or len(suyas) < min_piezas:
            descartes.append({**c, "motivo": f"material insuficiente ({len(suyas)} piezas, {material} palabras; "
                                             f"hacen falta {min_piezas} y {minimo})"})
            continue
        if R.comunes(f"{c['titulo']}. {c.get('linea', '')}", cfg):
            descartes.append({**c, "motivo": "lleva contenido excluido o una promesa no permitida"})
            continue
        nota = sum(int(n.get(k) or 0) for k in ("tres_publicos", "atemporal", "curiosidad", "diferente", "repetible"))
        parecido = next((p["titulo"] for p in previos if T.similitud(c["titulo"], p["titulo"], genericas) >= 0.5), "")
        validos.append({"id": c["id"], "pilar": c.get("pilar", ""), "titulo": c["titulo"], "resumen": c.get("linea", ""),
                        "origen": sorted({p["fuente"] for p in suyas}), "piezas": [p["id"] for p in suyas],
                        "material_palabras": material, "nota": nota, "frase": n.get("frase", ""), "parecido_a": parecido,
                        "formato": c.get("formato", ""), "serie": c.get("serie", ""), "enlaza_con": c.get("enlaza_con") or [],
                        "demanda": c.get("demanda") or {}})
    validos.sort(key=lambda x: (-x["nota"], bool(x["parecido_a"]), x["id"]))
    temas, suplentes, avisos = [], [], []
    for p in [x["id"] for x in cfg.get("pilares") or [] if isinstance(x, dict)] or sorted({v["pilar"] for v in validos}):
        suyos = [v for v in validos if v["pilar"] == p]
        dentro, fuera = [], []          # variedad: dos temas de la misma serie o con las mismas piezas son el mismo vídeo
        for v in suyos:
            gemelo = next((e for e in dentro if (v["serie"] and v["serie"] == e["serie"])
                           or len(set(v["piezas"]) & set(e["piezas"])) >= 2
                           or T.similitud(v["titulo"], e["titulo"], genericas) >= 0.5), None)
            if gemelo or len(dentro) >= r["temas_por_pilar"]:
                fuera.append({**v, "hermano_de": gemelo["id"]} if gemelo else v)
            else:
                dentro.append(v)
        if len(dentro) < r["temas_por_pilar"]:      # si no hay variedad suficiente, se completa con hermanos
            dentro += fuera[:r["temas_por_pilar"] - len(dentro)]
            fuera = [v for v in fuera if v not in dentro]
        suyos = dentro
        temas += dentro
        suplentes += fuera[:2]
        if len(suyos) < r["temas_por_pilar"]:
            avisos.append(f"El pilar «{p}» se queda corto: {len(suyos)} de {r['temas_por_pilar']} temas con material y sin veto.")
    for i, t in enumerate(temas, 1):
        t["n"] = i
    _guardar(d / "temas.json", {"temas": temas, "suplentes": suplentes, "avisos": avisos, "candidatos": len(todos),
                                "descartados": [{"titulo": x["titulo"], "motivo": x["motivo"]} for x in descartes]})
    elegidos = {t["id"] for t in temas}
    for c in todos:
        B.anotar(C.carpeta(slug) / "temas.jsonl",
                 {"ts": B.ahora(), "encargo": enc.get("id", ""), "titulo": c["titulo"], "pilar": c.get("pilar", ""),
                  "estado": "propuesta" if c.get("id") in elegidos else "candidata"})
    if not temas:
        return {"fallo": "ningún candidato pasa los vetos y tiene material suficiente"}
    return {"resumen": f"{len(temas)} temas propuestos de {len(todos)} candidatos" + (f"; {len(avisos)} pilar(es) cortos" if avisos else "")}


def t_brief(slug: str, d: Path, enc: dict) -> dict:
    b = _json(d / "brief.json", None)
    if not isinstance(b, dict) or not b.get("promesa") or len(b.get("angulos") or []) < 1:
        return {"fallo": "brief.json no tiene promesa o ángulos"}
    if "DEBIL" in T.plano(str(b.get("veredicto", ""))).upper():
        return {"fallo": f"idea débil: {b.get('motivo') or 'sin motivo'}"}
    return {}


def t_opciones(slug: str, d: Path, enc: dict) -> dict:
    """De treinta títulos a los que se presentan: filtro por código, orden por las notas del espectador y variedad
    de palancas y de ángulos. Las miniaturas pasan todas."""
    cfg = C.leer(slug)
    r = R.reglas(cfg)
    brief = _json(d / "brief.json", {}) or {}
    tits = (_json(d / "titulos.json", {}) or {}).get("titulos") or []
    esp = _json(d / "espectador.json", {}) or {}
    minis = (_json(d / "miniaturas.json", {}) or {}).get("miniaturas") or []
    notas = {str(x.get("n")): x for x in esp.get("titulos") or [] if isinstance(x, dict)}
    buenos, descartes, vistos = [], [], set()
    for t in tits:
        if not isinstance(t, dict) or not t.get("texto"):
            continue
        c = T.titulo(t["texto"], claves=brief.get("palabras_clave"), reglas=r, cliches=cfg.get("titulo_cliches"))
        n = notas.get(str(t.get("n")), {})
        motivo = (c["fallos"][0][1] if c["fallos"] else
                  "lleva contenido excluido o una promesa no permitida" if R.comunes(t["texto"], cfg) else
                  "repetido" if T.plano(t["texto"]) in vistos else
                  "no promete lo que da el vídeo" if n.get("cumple") is False else "")
        vistos.add(T.plano(t["texto"]))
        if motivo:
            descartes.append({"texto": t["texto"], "motivo": motivo})
            continue
        nota = sum(int(n.get(k) or 0) for k in ("atencion", "interes", "curiosidad"))
        buenos.append({**t, "caracteres": c["chars"], "movil": c["movil"], "nota": nota,
                       "espera": n.get("espero_ver", ""), "avisos": [m for _, m in c["avisos"]]})
    buenos.sort(key=lambda x: (-x["nota"], x.get("n", 0)))
    k = r["titulos_presentados"]
    elegidos = []
    for criterio in ("palanca", "angulo"):          # primero el mejor de cada palanca; luego, de cada ángulo
        for t in buenos:
            if len(elegidos) < k and t not in elegidos and t.get(criterio) not in {e.get(criterio) for e in elegidos}:
                elegidos.append(t)
    elegidos += [t for t in buenos if t not in elegidos][:max(0, k - len(elegidos))]
    elegidos.sort(key=lambda x: -x["nota"])
    presentados = [{**t, "original": t.get("n"), "n": i} for i, t in enumerate(elegidos, 1)]
    rec = esp.get("recomendacion") or {}
    por_original = {t["original"]: t["n"] for t in presentados}
    _guardar(d / "opciones.json", {
        "brief": {k2: brief.get(k2) for k2 in ("audiencia", "deseo", "palabras_clave", "promesa", "angulos")},
        "titulos": presentados, "titulos_descartados": descartes + [{"texto": t["texto"], "motivo": "quedó fuera por nota"}
                                                                    for t in buenos if t not in elegidos],
        "miniaturas": minis,
        "recomendacion": {"titulo": por_original.get(rec.get("titulo"), 1 if presentados else None),
                          "miniatura": rec.get("miniatura") or (minis[0].get("n") if minis else None),
                          "titulo_alternativo": por_original.get(rec.get("titulo_alternativo"))}})
    return {"resumen": f"{len(presentados)} títulos presentados de {len(tits)} y {len(minis)} ideas de miniatura"}


def t_material(slug: str, d: Path, enc: dict) -> dict:
    """El material con el que se escribe: solo lo que lleva una cita literal de su fuente."""
    m = _json(d / "material.json", None)
    if not isinstance(m, dict) or not isinstance(m.get("material"), list):
        return {"fallo": "material.json no tiene el formato pedido"}
    buenas, malas = [], 0
    for x in m["material"]:
        try:
            col, ident = _partir_fuente(str(x.get("fuente", "")))
            ok = F.cita(slug, col, ident, str(x.get("cita", "")))
        except (Rechazo, AttributeError):
            ok = None
        if ok and str(x.get("n", "")).isdigit():
            buenas.append({**x, "n": int(x["n"]), "marca": ok["marca"]})
        else:
            malas += 1
    # Si da para un vídeo lo decide una cuenta, no una opinión: las palabras útiles tienen que llegar a un porcentaje
    # del guion más corto que admite el canal. Un guion desarrolla su material, pero no puede salir de la nada.
    r = R.reglas(C.leer(slug))
    pct = int(r.get("material_min_pct") or 50)
    minimo = r["ppm"] * r["minutos"][0] * pct // 100
    try:
        utiles = int(m.get("palabras_utiles") or 0)
    except (TypeError, ValueError):
        utiles = 0
    if len(buenas) < 6:
        return {"fallo": f"solo {len(buenas)} piezas de material con cita comprobada ({malas} sin ella): no da para un guion"}
    if utiles < minimo:
        return {"fallo": f"material insuficiente: {utiles} palabras útiles y hacen falta {minimo} (el {pct} % de un guion "
                         f"de {r['minutos'][0]} minutos). Propuesta: {m.get('propuesta') or 'sin propuesta'}"}
    justo = utiles < r["ppm"] * r["minutos"][0]
    _guardar(d / "material.json", {**m, "veredicto": "SUFICIENTE", "material": buenas, "sin_cita": malas, "material_justo": justo})
    return {"resumen": f"{len(buenas)} piezas de material" + (f"; {malas} descartadas por cita no literal" if malas else "")}


def t_datos(slug: str, d: Path, enc: dict) -> dict:
    """La lista de datos que tiene que verificar una persona, uno a uno."""
    v = _json(d / "verificacion.json", None)
    if not isinstance(v, dict):
        return {"fallo": "verificacion.json no tiene el formato pedido"}
    previos = {x.get("dato"): x for x in (_json(d / "datos.json", {}) or {}).get("datos") or []}
    datos = []
    for i, x in enumerate([x for x in v.get("datos") or [] if isinstance(x, dict) and x.get("dato")], 1):
        ya = previos.get(x["dato"], {})
        datos.append({"id": f"d{i}", "dato": x["dato"], "frase": x.get("frase", ""), "motivo": x.get("motivo", "externo"),
                      "fuente": x.get("fuente", ""), "versiones": x.get("versiones") or [],
                      "estado": ya.get("estado", "pendiente"), "valor": ya.get("valor", "")})
    _guardar(d / "datos.json", {"datos": datos})
    return {"resumen": f"{len(datos)} datos a verificar; {len(v.get('cambios') or [])} cambios pedidos"}


def capitulos(guion: str, caps: list, ppm: int) -> list:
    """[(segundo, título)]: cada capítulo empieza donde empieza su bloque (o una frase dentro de él)."""
    bl = T.bloques(guion)
    inicio, acum = {}, 0
    for nombre, texto in bl:
        inicio[nombre] = (acum, texto)
        acum += len(T.palabras(T.sin_marcas(texto)))
    out = []
    for c in caps:
        if not isinstance(c, dict) or c.get("desde") not in inicio:
            continue
        base, texto = inicio[c["desde"]]
        frase = " ".join(T.plano(str(c.get("frase") or "")).split())
        if frase:
            pos = " ".join(T.plano(T.sin_marcas(texto)).split()).find(frase[:60])
            if pos > 0:
                base += len(T.palabras(" ".join(T.plano(T.sin_marcas(texto)).split())[:pos]))
        out.append((round(base * 60 / ppm) if ppm else 0, str(c.get("titulo", "")).strip()))
    out.sort()
    if out:
        out[0] = (0, out[0][1])
    return out


def t_descripcion(slug: str, d: Path, enc: dict) -> dict:
    """La descripción final: el resumen del agente y los capítulos con sus minutos calculados."""
    x = _json(d / "descripcion.json", None)
    if not isinstance(x, dict) or not str(x.get("resumen", "")).strip():
        return {"fallo": "descripcion.json no trae resumen"}
    cfg = C.leer(slug)
    caps = capitulos((d / "guion.md").read_text(encoding="utf-8"), x.get("capitulos") or [], R.reglas(cfg)["ppm"])
    texto = x["resumen"].strip() + "\n\n" + "\n".join(f"{T.mmss(s)} {t}" for s, t in caps) + "\n"
    if str(cfg.get("descripcion_pie") or "").strip():
        texto += "\n" + cfg["descripcion_pie"].strip() + "\n"
    (d / "descripcion.md").write_text(texto, encoding="utf-8")
    return {"resumen": f"descripción con {len(caps)} capítulos"}


def limpio(guion: str) -> str:
    """El guion para el teleprompter: solo lo que se lee, una frase por línea y un hueco entre bloques."""
    return "\n\n".join("\n".join(T.frases(T.sin_marcas(t))) for _, t in T.bloques(guion) if t.strip()) + "\n"


def numerado(guion: str) -> str:
    """El guion para revisar: cada frase con su número, para que un comentario pueda señalarla."""
    out, actual = [], None
    for n, bloque, frase in T.numerar(guion):
        if bloque != actual:
            out.append(f"\n## {bloque}\n")
            actual = bloque
        out.append(f"{n}. {frase}")
    return "\n".join(out).strip() + "\n"


def revisar_paquete(slug: str, d: Path) -> list:
    """Todos los avisos de la revisión por código sobre lo que hay en el encargo."""
    cfg = C.leer(slug)
    el = _json(d / "eleccion.json", {}) or {}
    avisos = []
    if (d / "guion.md").exists():
        guion = (d / "guion.md").read_text(encoding="utf-8")
        mat = {int(x["n"]) for x in (_json(d / "material.json", {}) or {}).get("material") or [] if str(x.get("n", "")).isdigit()}
        rec = [a.get("frase", "") for a in (_json(d / "aperturas-recientes.json", {}) or {}).get("aperturas") or []]
        avisos += R.guion(guion, cfg, mat or None, _json(d / "escaleta.json", None), rec)
        dur = T.medidas(guion, R.reglas(cfg)["ppm"])["minutos"] * 60
        if (d / "descripcion.md").exists():
            avisos += R.descripcion((d / "descripcion.md").read_text(encoding="utf-8"), cfg, el.get("palabras_clave"), dur)
        else:
            avisos.append(R.aviso(True, "sin-descripcion", "falta la descripción"))
    else:
        avisos.append(R.aviso(True, "sin-guion", "falta el guion"))
    if el.get("titulo"):
        c = T.titulo(el["titulo"], ((el.get("miniatura") or {}).get("texto") or ""), el.get("palabras_clave"),
                     R.reglas(cfg), cfg.get("titulo_cliches"))
        avisos += [R.aviso(not el.get("propio"), f"titulo-{k}", m) for k, m in c["fallos"]]
        avisos += R.comunes(el["titulo"], cfg, "el título")
    pendientes = [x for x in (_json(d / "datos.json", {}) or {}).get("datos") or [] if x.get("estado") == "pendiente"]
    if pendientes:
        avisos.append(R.aviso(False, "datos-pendientes", f"{len(pendientes)} datos esperan a que una persona los verifique"))
    return avisos


def t_paquete(slug: str, d: Path, enc: dict) -> dict:
    """Monta el paquete: lo que verá la persona y lo que se exportará."""
    cfg = C.leer(slug)
    r = R.reglas(cfg)
    guion = (d / "guion.md").read_text(encoding="utf-8")
    m = T.medidas(guion, r["ppm"])
    el = _json(d / "eleccion.json", {}) or {}
    cierre = _json(d / "cierre.json", {}) or {}
    avisos = revisar_paquete(slug, d)
    (d / "guion-limpio.txt").write_text(limpio(guion), encoding="utf-8")
    (d / "guion-numerado.md").write_text(numerado(guion), encoding="utf-8")
    medido = int(r.get("ppm_medido") or 0)
    _guardar(d / "paquete.json", {
        "titulo": el.get("titulo", ""), "miniatura": el.get("miniatura"), "promesa": el.get("promesa", ""),
        "guion": {"palabras": m["palabras"], "minutos": m["minutos"],
                  "minutos_a_ritmo_medido": T.minutos(m["palabras"], medido) if medido else None,
                  "frases": m["frases"], "media_frase": m["media"]},
        "datos": (_json(d / "datos.json", {}) or {}).get("datos") or [],
        "revision": {"nota": R.nota(avisos), "graves": sum(1 for a in avisos if a["grave"]), "avisos": avisos},
        "editor": {"veredicto": cierre.get("veredicto", ""), "notas": cierre.get("notas") or []},
        "riesgos": (_json(d / "retencion.json", {}) or {}).get("riesgos") or [],
        "ficheros": {"guion": "guion-limpio.txt", "guion_numerado": "guion-numerado.md", "descripcion": "descripcion.md"}})
    return {"resumen": f"paquete montado: {m['palabras']} palabras ({m['minutos']} min), nota {R.nota(avisos)}, "
                       f"{sum(1 for a in avisos if a['grave'])} avisos graves"}


PREPARA = {"fuente": p_fuente, "fuentes": p_fuentes, "inventario": p_inventario, "referencias": p_referencias, "voz": p_voz,
           "eleccion": p_eleccion, "ajustes": p_ajustes}
TRAS = {"piezas": t_piezas, "seleccionar": t_seleccionar, "brief": t_brief, "opciones": t_opciones,
        "material": t_material, "datos": t_datos, "descripcion": t_descripcion, "paquete": t_paquete}
