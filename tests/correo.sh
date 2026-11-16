#!/usr/bin/env bash
# Correo (lado del plugin, con un Worker de mentira en una carpeta; sin red): a quién va cada puerta según su papel,
# el contenido por tipo de puerta, decidir SOLO por código (persona de ese canal con ese papel, puerta abierta,
# contenido sin cambios), aprobar al momento y lo demás con ventana y DESHACER, la respuesta con instrucción como
# «rehacer», los datos que no se deciden por correo, las tres peticiones, el remitente desconocido, el resumen diario
# y los avisos tras la firma.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T" 2>/dev/null' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HOME="$T/casa" FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros"
export HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HYT_SIN_SCOPE=1
export HYT_CORREO_URL="file://$T/buzon" HYT_CORREO_SECRETO=x HYT_CORREO_BUZON=buzon@x.dev HYT_CORREO_CONF="$T/no-existe.env"
unset HERMES_YT_DESHACER_S
mkdir -p "$T/buzon" "$HOME"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
P="$ROOT/plugin/hermes-youtube"; export P T
C="python3 $P/hyt_canales.py"; H="python3 $P/hyt_cli.py"
$C alta demo "Cocina Clara" "Pepa Ejemplo" >/dev/null; $C alta otro "Otro Canal" "Otra Persona" >/dev/null
$C config demo pilares '[{"id":"arroces","nombre":"Arroces","tipo":"pilar"},{"id":"guisos","nombre":"Guisos","tipo":"pilar"}]' >/dev/null
$C config demo personas '{"marta":{"nombre":"Marta","correo":"Marta@Ejemplo.com","roles":["marketing"]},"mario":{"nombre":"Mario","correo":"mario@ejemplo.com","roles":["marketing"]},"dario":{"nombre":"Darío","correo":"dario@ejemplo.com","roles":["datos"]},"pepa":{"nombre":"Pepa","correo":"pepa@ejemplo.com","roles":["presentador"]},"sincorreo":{"nombre":"Sin","correo":"","roles":["marketing","presentador"]}}' >/dev/null
$C config otro personas '{"marta":{"nombre":"Marta","correo":"marta@ejemplo.com","roles":["marketing"]},"luis":{"nombre":"Luis","correo":"luis@ejemplo.com","roles":["marketing"]}}' >/dev/null
echo '{"max_decisiones": 0, "panel_url": "https://panel.ejemplo.com/youtube"}' > "$HERMES_YT_HOME/yt.json"
jq -n --arg u "$(id -un)" '{admin: {nombre: "Admin", medios: {local: $u, telegram: "9"}, canales: ["*"]}}' > "$HERMES_YT_HOME/aprobadores.json"

cat > "$T/py" <<'PY'
import json, os, sys, time, urllib.parse
from pathlib import Path
sys.path.insert(0, os.environ["P"])
import hyt_base as B, hyt_canales as C, hyt_encargos as E, hyt_puertas as PU, hyt_correo as HC
T = Path(os.environ["T"]); BUZON = T / "buzon"
def enviados():
    HC.despachar()
    return [json.loads(l) for l in (BUZON / "enviados.jsonl").read_text().splitlines()] if (BUZON / "enviados.jsonl").exists() else []
def nuevos(antes): return enviados()[antes:]
def para(correo, lista): return [e for e in lista if e["to"] == correo]
N = [0]
def llega(de, asunto="", texto="", hilo=""):
    """Un correo recibido: pasa por recoger() y devuelve lo que se hizo con él."""
    N[0] += 1
    (BUZON / "pendientes.json").write_text(json.dumps([{"id": f"m{N[0]}-{time.time()}", "de": de, "asunto": asunto, "texto": texto,
                                                         "message_id": f"<r{N[0]}@cliente>", "in_reply_to": hilo}]))
    HC.recoger()
    return json.loads((B.home() / "correo/recibidos.jsonl").read_text().splitlines()[-1])["resultado"]
def mid(e):
    """El Message-ID con el que salió un correo nuestro (para responder en su hilo)."""
    for l in reversed((B.home() / "correo/enviados.jsonl").read_text().splitlines()):
        r = json.loads(l)
        if r["to"] == e["to"] and r["asunto"] == e["subject"]:
            return r["message_id"]
def cod(g): return PU.leer(g)["correo"]["codigos"]
def cuerpo(html_, palabra):
    """El cuerpo del correo que abre el botón de esa palabra."""
    import html as H, re
    for enlace in re.findall(r'href="(mailto:[^"]+)"', html_):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(H.unescape(enlace)).query)
        if q.get("subject", [""])[0].startswith(palabra):
            return q["body"][0]
    return None
def guion(tema, ronda=0, indice=0, datos=("pendiente",)):
    """Un encargo de guion con su paquete montado, esperando en la puerta `indice` de su cadena."""
    e = E.lanzar("demo", "guion", {"tema": tema, "pilar": "arroces"})
    d = E.carpeta("demo", e["id"])
    g = "## intro\nEl arroz no se pasa por el tiempo. Se pasa por el agua.\n## desarrollo-1\nMide el agua antes de encender el fuego. El grano hace el resto.\n## cierre\nEso es el agua. Queda el fuego.\n"
    (d / "guion.md").write_text(g)
    (d / "guion-numerado.md").write_text("## intro\n\n1. El arroz no se pasa por el tiempo.\n2. Se pasa por el agua.\n\n## desarrollo-1\n\n3. Mide el agua antes de encender el fuego.\n4. El grano hace el resto.\n")
    (d / "guion-limpio.txt").write_text("El arroz no se pasa por el tiempo.\nSe pasa por el agua.\n")
    (d / "descripcion.md").write_text("Por qué se pasa el arroz y cómo evitarlo.\n\n00:00 La regla del agua\n01:10 El fuego\n")
    mini = {"n": 2, "concepto": "dilema", "que_se_ve": "Dos cazuelas, una pasada y otra en su punto", "texto": "¿AGUA O TIEMPO?",
            "presentador": {"aparece": True, "expresion": "duda", "mirada": "a la cazuela", "foto_a_pedir": "Plano medio con una cazuela en cada mano"},
            "composicion": {"tipo": "cara-derecha-objeto-izquierda"}, "reparto": "el título dice el qué, la miniatura la duda"}
    B.escribir(d / "eleccion.json", {"titulo": f"{tema}: la regla del agua", "miniatura": mini, "promesa": "Arroz suelto siempre", "palabras_clave": ["arroz"]})
    B.escribir(d / "datos.json", {"datos": [{"id": f"d{i}", "dato": f"El dato {i}", "frase": "Se pasa por el agua.", "motivo": "externo", "fuente": "charlas/v01", "estado": s, "valor": ""}
                                            for i, s in enumerate(datos, 1)]})
    B.escribir(d / "paquete.json", {"titulo": f"{tema}: la regla del agua", "miniatura": mini, "promesa": "Arroz suelto siempre",
        "guion": {"palabras": 31, "minutos": 0.2}, "datos": B.leer(d / "datos.json")["datos"],
        "revision": {"nota": 82, "graves": 0, "avisos": [{"grave": False, "codigo": "intro-larga", "texto": "La intro tiene 80 palabras (máximo 75)"}]},
        "editor": {"veredicto": "APROBADO", "notas": ["El cierre enlaza bien con el vídeo del fuego"]}})
    enc = E.leer("demo", e["id"]); enc.update(rondas=ronda, puerta_indice=indice); E.guardar("demo", enc)
    return e["id"], abrir(e["id"])
def abrir(eid):
    """Abre la puerta del encargo sin los avisos de la revisión por código (aquí se prueba el correo, no las reglas)."""
    g = PU.abrir("demo", eid)["id"]
    p = PU.leer(g); p["revision"] = {"avisos": [], "graves": 0}; B.escribir(PU.indice(g), p)
    return g
def firma_ya(g):
    """Da por pasada la ventana para deshacer y deja que el ciclo del correo firme y avise."""
    p = PU.leer(g); p["firmar_en"] = 0; B.escribir(PU.indice(g), p)
    HC.firmar_vencidas(); HC.avisar_firmadas()
    return PU.leer(g)
PY
caso() { python3 - <<PY && ok "$1" || bad "$1"
exec(open("$T/py").read())
$2
PY
}

caso "a quién va cada puerta: las personas del canal con su papel y con correo (sin papel, marketing); su correo es su identidad" '
assert HC.destinatarios("demo") == [("marta", "marta@ejemplo.com"), ("mario", "mario@ejemplo.com")] == HC.destinatarios("demo", "marketing")
assert HC.destinatarios("demo", "presentador") == [("pepa", "pepa@ejemplo.com")] and HC.destinatarios("demo", "datos") == [("dario", "dario@ejemplo.com")]
assert [(s, k) for s, k, _ in HC.de_quien("MARTA@ejemplo.com")] == [("demo", "marta"), ("otro", "marta")] and HC.de_quien("nadie@x.com") == []
assert PU.persona_de("email", "pepa@ejemplo.com", "demo")[0] == "pepa" and PU.persona_de("email", "pepa@ejemplo.com", "otro") == (None, None)
assert PU.persona_de("email", "pepa@ejemplo.com")[0] == "pepa" and PU.persona_de("telegram", "pepa@ejemplo.com") == (None, None)
for persona, papel, medio, puede in (("pepa", "presentador", "email", True), ("pepa", "marketing", "email", False), ("pepa", "", "email", False),
                                     ("pepa", "presentador", "telegram", False), ("pepa", "presentador", "dashboard", False),
                                     ("marta", "", "email", True), ("marta", "marketing", "email", True), ("marta", "datos", "email", False),
                                     ("sincorreo", "marketing", "email", False), ("luis", "marketing", "email", False), ("admin", "marketing", "email", False)):
    assert PU.puede_decidir(persona, "demo", papel, medio) is puede, (persona, papel, medio)
assert HC.activo()
'

caso "revisión: el correo va a marketing con título, miniatura, guion numerado, descripción, nota, avisos, notas del editor y datos; botones con código" '
eid, g = guion("Arroz suelto")
assert HC.enviar_puertas() == 1 and HC.enviar_puertas() == 0
env = enviados(); c = cod(g)
assert sorted(e["to"] for e in env) == ["mario@ejemplo.com", "marta@ejemplo.com"] and PU.leer(g)["correo"]["a"] == ["marta@ejemplo.com", "mario@ejemplo.com"]
e = para("marta@ejemplo.com", env)[0]
for trozo in ("Arroz suelto: la regla del agua", "Promesa: Arroz suelto siempre", "Qué se ve: Dos cazuelas", "Texto: «¿AGUA O TIEMPO?»", "Expresión: duda",
              "Reparto con el título", "1. El arroz no se pasa por el tiempo.", "4. El grano hace el resto.", "00:00 La regla del agua", "nota 82",
              "La intro tiene 80 palabras", "El cierre enlaza bien", "El dato 1 [pendiente]", "Puerta 1 de 3 · decide: marketing"):
    assert trozo.lower() in e["text"].lower(), trozo
    assert __import__("html").escape(trozo) in e["html"], trozo
assert "Foto que hay que pedir" not in e["text"] and "ha cambiado" not in e["text"]                       # eso es para quien graba; y no hay versión anterior
assert set(c) == {"acepto", "cambios", "rechazo", "deshacer"} and len(set(c.values())) == 4
assert cuerpo(e["html"], "APROBAR") == "APROBAR " + c["acepto"] and cuerpo(e["html"], "REHACER") == "REHACER " + c["cambios"] + ": " + HC.AYUDA_REHACER
assert cuerpo(e["html"], "RECHAZAR").startswith("RECHAZAR " + c["rechazo"]) and "mailto:buzon@x.dev" in e["html"] and c["deshacer"] not in e["html"]
assert "APROBAR " + c["acepto"] in e["text"] and "max-width:640px" in e["html"] and e["subject"].startswith("🚪 📝 Guion · Cocina Clara · ")
print(eid, g, file=open(T / "revision", "w"))
'
caso "un «sí» suelto no decide; en el hilo, un acuse («perfecto, gracias») tampoco: se contesta con los botones" '
eid, g = open(T / "revision").read().split(); c = cod(g); n = len(enviados())
hilo = mid(para("marta@ejemplo.com", enviados())[0])
assert llega("marta@ejemplo.com", "sí", "sí, adelante").startswith("ayuda") and PU.leer(g)["estado"] == "abierta"
for acuse in ("Perfecto, gracias", "ok", "👍", "Recibido, muchas gracias. Un saludo", "Vale, de acuerdo"):
    assert not HC.con_instruccion(acuse), acuse
    assert llega("marta@ejemplo.com", "Re: Guion", acuse + "\n\nEl lun, 16 nov 2026 a las 10:00, hermes escribió:\n> En la frase 2 cambia el orden de las palabras", hilo) == "respuesta sin instrucción: botones"
assert PU.leer(g)["estado"] == "abierta"
r = nuevos(n)[-1]
assert r["to"] == "marta@ejemplo.com" and "no he decidido nada" in r["text"] and cuerpo(r["html"], "REHACER").startswith("REHACER " + c["cambios"]) and r["in_reply_to"].startswith("<r")
'
caso "en el hilo, una respuesta con una instrucción vale como REHACER (sin la cita), con ventana y DESHACER; deshacer la reabre y se reenvía con códigos nuevos" '
eid, g = open(T / "revision").read().split(); c = cod(g); n = len(enviados())
hilo = mid(para("marta@ejemplo.com", enviados())[0])
pedido = "En la frase 2 yo diría «se pasa por exceso de agua», más corto y más directo."
assert HC.con_instruccion(pedido)
assert llega("pepa@ejemplo.com", "Re: Guion", pedido, hilo) == "texto libre de quien no decide esta puerta"   # quien presenta no decide la puerta de marketing
assert PU.leer(g)["estado"] == "abierta" and "papel «marketing»" in enviados()[-1]["text"] and "mailto:" not in enviados()[-1]["html"]
res = llega("marta@ejemplo.com", "Re: Guion", pedido + "\n\nEl lun, 16 nov 2026 a las 10:00, hermes escribió:\n> APROBAR " + c["acepto"], hilo)
p = PU.leer(g)
assert res == f"decidida {g} (cambios)" and p["estado"] == "decidida" and p["decision"]["verbo"] == "cambios" and p["decision"]["texto"] == pedido, (res, p.get("decision"))
assert p["decision"]["actor"] == {"persona": "marta", "medio": "email", "id": "marta@ejemplo.com"} and p["firmar_en"] - time.time() > 1500
conf = nuevos(n)[-1]
assert conf["subject"].startswith("🕒 Recibido") and "DESHACER " + c["deshacer"] in conf["text"] and cuerpo(conf["html"], "DESHACER") == "DESHACER " + c["deshacer"] and pedido in conf["text"]
assert llega("mario@ejemplo.com", "DESHACER " + c["deshacer"], "DESHACER " + c["deshacer"]).startswith("no deshecha")        # solo quien decidió
assert llega("marta@ejemplo.com", "DESHACER " + c["deshacer"], "DESHACER " + c["deshacer"]) == f"deshecha {g}"
assert PU.leer(g)["estado"] == "abierta" and "correo" not in PU.leer(g)
assert HC.enviar_puertas() == 1 and cod(g)["acepto"] != c["acepto"]
assert llega("marta@ejemplo.com", "APROBAR " + c["acepto"], "APROBAR " + c["acepto"]) == "descartado: código desconocido (avisado)" and PU.leer(g)["estado"] == "abierta"
assert "No reconozco ese código" in enviados()[-1]["text"]
'
caso "decide el código: ni un desconocido, ni alguien de otro canal, ni quien no tiene el papel; si el contenido cambió, se reenvía" '
eid, g = open(T / "revision").read().split(); c = cod(g); n = len(enviados())
linea = "APROBAR " + c["acepto"]
assert llega("intruso@x.com", linea, linea) == "descartado: remitente desconocido (avisado)"
assert llega("intruso@x.com", linea, linea) == "descartado: remitente desconocido (ya avisado hoy)"
av = nuevos(n); assert len(av) == 1 and av[0]["to"] == "intruso@x.com" and "no está autorizada" in av[0]["subject"]
ac = [json.loads(l) for l in (B.home() / "acciones.jsonl").read_text().splitlines()]
assert ac[-1]["tipo"] == "correo-no-autorizado" and ac[-1]["de"] == "intruso@x.com" and len(ac) == 1
assert llega("luis@ejemplo.com", linea, linea) == "descartado: el código no es de una puerta de un canal suyo"
assert llega("pepa@ejemplo.com", linea, linea).startswith("rechazada: Esta puerta la decide quien tiene el papel «marketing»")
assert llega("marta@ejemplo.com", "REHACER " + c["cambios"], "REHACER " + c["cambios"] + ": " + HC.AYUDA_REHACER) == "cambios sin texto: se pide"   # el botón enviado tal cual
assert PU.leer(g)["estado"] == "abierta"
d = E.carpeta("demo", eid); (d / "guion.md").write_text((d / "guion.md").read_text() + "\nUna frase nueva.\n")
assert llega("marta@ejemplo.com", linea, linea) == "contenido cambiado: se reenvía" and PU.leer(g)["estado"] == "abierta" and "correo" not in PU.leer(g)
assert HC.enviar_puertas() == 1
'
caso "APROBAR se firma al momento, con un solo correo; se abre la puerta de datos, que va a quien verifica, sin botones y mandando al panel" '
eid, g = open(T / "revision").read().split(); c = cod(g); n = len(enviados())
res = llega("marta@ejemplo.com", "APROBAR " + c["acepto"], "APROBAR " + c["acepto"] + "\n\n> REHACER " + c["cambios"])
p = PU.leer(g)
assert res == f"firmada {g} (acepto)" and p["estado"] == "firmada" and p["firma"] == "Marta (email)" and "pasa a la puerta datos" in p["resultado"], (res, p)
hecho = [e for e in nuevos(n) if e["to"] == "marta@ejemplo.com"]
assert len(hecho) == 1 and hecho[0]["subject"].startswith("✅ Hecho") and "pasa a la puerta datos" in hecho[0]["text"]
n = len(enviados()); HC.ciclo()
mas = nuevos(n); gd = next(x for x in PU.puertas(("abierta",)) if x.get("encargo") == eid)
assert [e["to"] for e in mas] == ["dario@ejemplo.com"], [(e["to"], e["subject"]) for e in mas]                # ni otro «hecho» a Marta ni nada a marketing
e = mas[0]
assert gd["tipo"] == "datos" and gd["correo"]["codigos"] == {} and "mailto:" not in e["html"] and "APROBAR" not in e["text"]
assert "1 dato(s) por verificar" in e["text"] and "El dato 1 [pendiente]" in e["text"] and "https://panel.ejemplo.com/youtube" in e["text"]
assert llega("dario@ejemplo.com", "Re: datos", "El dato está bien, lo he comprobado con la fuente original y es correcto", mid(e)) == "texto libre en una puerta que no lo admite: botones"
r = enviados()[-1]; assert PU.leer(gd["id"])["estado"] == "abierta" and "se verifican en el panel" in r["text"] and "mailto:" not in r["html"]
PU.verificar_dato(gd["id"], "d1", "verificado", "", "dario", "email", "dario@ejemplo.com")
p = PU.leer(gd["id"]); p["revision"] = {"avisos": [], "graves": 0}; B.escribir(PU.indice(gd["id"]), p)     # sin los avisos de las reglas
PU.decidir(gd["id"], "acepto", "", "dario", "email", "dario@ejemplo.com"); PU.firmar_ya(gd["id"])
print(eid, file=open(T / "final", "w"))
'
caso "revisión final: va a quien presenta, con las frases que han cambiado; su RECHAZAR (con ventana) se notifica a marketing con el motivo" '
eid = open(T / "final").read().strip(); d = E.carpeta("demo", eid)
(d / ".estado").mkdir(exist_ok=True); (d / ".estado/guion-antes-1.md").write_text("## intro\nEl arroz no se pasa por el tiempo. Se pasa por el caldo.\n## desarrollo-1\nMide el agua antes de encender el fuego. El grano hace el resto.\n## cierre\nEso es el agua. Queda el fuego.\n")
n = len(enviados()); HC.ciclo()
g = next(x for x in PU.puertas(("abierta",)) if x.get("encargo") == eid)["id"]
mas = [e for e in nuevos(n) if e["subject"].startswith("🚪")]
assert [e["to"] for e in mas] == ["pepa@ejemplo.com"] and PU.leer(g)["tipo"] == "revision-final"
t = mas[0]["text"]
assert "LO QUE HA CAMBIADO DESDE LA VERSIÓN ANTERIOR" in t and "Frase 2: Se pasa por el agua." in t and "Puerta 3 de 3 · decide: presentador" in t and "El dato 1 [verificado]" in t
c = cod(g); n = len(enviados())
assert llega("pepa@ejemplo.com", "RECHAZAR " + c["rechazo"], "RECHAZAR " + c["rechazo"] + ": No me veo contando esto así") == f"decidida {g} (rechazo)"
assert PU.leer(g)["decision"]["texto"] == "No me veo contando esto así" and PU.leer(g)["estado"] == "decidida"
assert HC.firmar_vencidas() == 0                                                                          # la ventana sigue abierta
p = firma_ya(g)
assert p["estado"] == "firmada" and p["firma"] == "Pepa (email)" and E.leer("demo", eid)["estado"] == "descartado"
mas = nuevos(n)
av = [e for e in mas if e["subject"].startswith("🗑 Rechazado por quien presenta")]
assert sorted(e["to"] for e in av) == ["mario@ejemplo.com", "marta@ejemplo.com"] and "Motivo: No me veo contando esto así" in av[0]["text"]
assert [e["subject"][:7] for e in para("pepa@ejemplo.com", mas)] == ["🕒 Recib", "✅ Hecho"]
assert HC.avisar_firmadas() == 0 and len(enviados()) == n + len(mas)                                      # una sola vez
'
caso "al aprobar la última puerta de un guion: a quien presenta y a marketing, con título, miniatura y su foto, descripción y el guion limpio" '
eid, g = guion("Sofrito sin prisa", indice=2, datos=("verificado",))
HC.enviar_puertas(); c = cod(g); n = len(enviados())
assert llega("pepa@ejemplo.com", "APROBAR " + c["acepto"], "APROBAR " + c["acepto"]) == f"firmada {g} (acepto)" and E.leer("demo", eid)["estado"] == "cerrado"
HC.ciclo(); mas = nuevos(n)
listo = [e for e in mas if e["subject"].startswith("🎬 Aprobado, listo para grabar: Sofrito sin prisa")]
assert sorted(e["to"] for e in listo) == ["mario@ejemplo.com", "marta@ejemplo.com", "pepa@ejemplo.com"], [(e["to"], e["subject"]) for e in mas]
t = listo[0]["text"]
for trozo in ("Aprobado por Pepa (email)", "Sofrito sin prisa: la regla del agua", "Foto que hay que pedir: Plano medio con una cazuela en cada mano", "00:00 La regla del agua",
              "El arroz no se pasa por el tiempo.\nSe pasa por el agua."):
    assert trozo in t, trozo
assert "## intro" not in t.split("GUION")[-1] and "white-space:pre-wrap" in listo[0]["html"]
assert len([e for e in para("pepa@ejemplo.com", mas) if e["subject"].startswith("✅ Hecho")]) == 1
'
caso "un descarte por tope de rondas se notifica a marketing" '
eid, g = guion("Caldo de verdad", ronda=3)
HC.enviar_puertas(); c = cod(g); n = len(enviados())
assert "ronda 3" in para("marta@ejemplo.com", enviados())[-1]["text"]
llega("marta@ejemplo.com", "REHACER " + c["cambios"], "REHACER " + c["cambios"] + ": otra vuelta más a la intro")
p = firma_ya(g)
assert p["resultado"] == "descartado: superó las 3 rondas" and E.leer("demo", eid)["estado"] == "descartado"
av = [e for e in nuevos(n) if e["subject"].startswith("🗑 Descartado por rondas")]
assert [e["to"] for e in av] == ["mario@ejemplo.com"] and "otra vuelta más a la intro" in av[0]["text"]     # a Marta ya se le dice el resultado
assert "descartado: superó las 3 rondas" in [e for e in para("marta@ejemplo.com", nuevos(n)) if e["subject"].startswith("✅ Hecho")][0]["text"]
'

caso "elegir temas: numerados, con los suplentes siguiendo la numeración; ELEGIR pide los números; un texto libre no decide" '
e = E.lanzar("demo", "propuesta"); d = E.carpeta("demo", e["id"])
tema = lambda n, t, p, **k: {"n": n, "id": f"c{n}", "pilar": p, "titulo": t, "resumen": f"Resumen de {t}", "nota": 20 + n, "frase": f"Yo vería {t}", "piezas": ["p1", "p2"], "origen": ["charlas/v01"], **k}
B.escribir(d / "temas.json", {"temas": [tema(1, "Arroz al horno", "arroces"), tema(2, "El sofrito lento", "guisos", parecido_a="El sofrito de siempre"), tema(3, "Caldo corto", "guisos")],
                              "suplentes": [tema(9, "Arroz caldoso", "arroces")], "avisos": ["El pilar «arroces» se queda corto: 1 de 3 temas con material y sin veto."]})
g = abrir(e["id"]); HC.enviar_puertas(); c = cod(g); env = enviados()
m = para("marta@ejemplo.com", env)[-1]
for trozo in ("1. [arroces] Arroz al horno\nResumen de Arroz al horno\nNota: 21 · «Yo vería Arroz al horno»", "2. [guisos] El sofrito lento", "Parecido a: El sofrito de siempre",
              "SUPLENTES", "4. [arroces] Arroz caldoso", "El pilar «arroces» se queda corto", "escribe los números, por ejemplo: 1, 4, 7"):
    assert trozo in m["text"], trozo
assert "<ol start=\x274\x27" in m["html"] and set(c) == {"algunas", "cambios", "rechazo", "deshacer"}
assert cuerpo(m["html"], "ELEGIR") == "ELEGIR " + c["algunas"] + ": " + HC.AYUDA_TEMAS and cuerpo(m["html"], "OTRA") == "OTRA " + c["cambios"] and cuerpo(m["html"], "NINGUNO").startswith("NINGUNO " + c["rechazo"])
n = len(env)
assert llega("marta@ejemplo.com", "Re: temas", "Me gustan mucho el primero y el tercero de la lista que has mandado", mid(m)) == "texto libre en una puerta que no lo admite: botones"
assert llega("marta@ejemplo.com", "ELEGIR " + c["algunas"], "ELEGIR " + c["algunas"] + ": " + HC.AYUDA_TEMAS) == "algunas sin texto: se pide"   # enviado sin escribir nada
assert PU.leer(g)["estado"] == "abierta" and "Falta decir cuáles eliges" in enviados()[-1]["text"]
assert llega("marta@ejemplo.com", "ELEGIR " + c["algunas"], "ELEGIR " + c["algunas"] + ": 1, 7").startswith("rechazada:") and PU.leer(g)["estado"] == "abierta"   # el 7 no existe
assert llega("marta@ejemplo.com", "ELEGIR " + c["algunas"], "ELEGIR " + c["algunas"] + ": 1, 4\n\n-- \nMarta") == f"decidida {g} (algunas)"
p = PU.leer(g); assert p["decision"]["texto"] == "1, 4" and p["firmar_en"] - time.time() > 1500
p = firma_ya(g); assert "2 tema(s) en marcha" in p["resultado"], p["resultado"]
assert sorted(x["params"]["tema"] for x in E.listar("demo") if x["pipeline"] == "titulo-miniatura") == ["Arroz al horno", "Arroz caldoso"]
'
caso "elegir título: títulos con sus caracteres y su corte en móvil, ideas de miniatura y recomendación; el botón ELEGIR ya lleva la pareja recomendada" '
e = next(x for x in E.listar("demo") if x["pipeline"] == "titulo-miniatura" and x["params"]["tema"] == "Arroz al horno"); d = E.carpeta("demo", e["id"])
B.escribir(d / "opciones.json", {"brief": {"promesa": "Arroz al horno que no se seca", "palabras_clave": ["arroz"]},
    "titulos": [{"n": 1, "texto": "Arroz al horno: el fallo que lo seca", "caracteres": 36, "movil": "Arroz al horno: el fallo que lo seca", "avisos": []},
                {"n": 2, "texto": "Por qué tu arroz al horno queda seco y cómo arreglarlo", "caracteres": 54, "movil": "Por qué tu arroz al horno queda seco y c…", "avisos": ["se corta en el móvil"]}],
    "miniaturas": [{"n": 1, "concepto": "antes y después", "que_se_ve": "Una bandeja seca y otra jugosa", "texto": "SECO", "presentador": {"expresion": "sorpresa"}, "reparto": "el título explica, la miniatura enseña"},
                   {"n": 2, "concepto": "el culpable", "que_se_ve": "El caldo midiéndose en una jarra", "texto": "ES EL CALDO", "presentador": {"expresion": "seria"}, "reparto": "la miniatura da la pista"}],
    "recomendacion": {"titulo": 2, "miniatura": 1, "titulo_alternativo": 1}})
enc = E.leer("demo", e["id"]); enc["estado"] = "en-curso"; E.guardar("demo", enc)
g = abrir(e["id"]); HC.enviar_puertas(); c = cod(g); m = para("marta@ejemplo.com", enviados())[-1]
for trozo in ("Recomendación: título 2 con la miniatura 1 (alternativa: título 1)", "1. Arroz al horno: el fallo que lo seca\n36 caracteres · en el móvil: «Arroz al horno: el fallo que lo seca»",
              "54 caracteres · en el móvil: «Por qué tu arroz al horno queda seco y c…»\nse corta en el móvil", "Miniatura 2: el culpable", "Qué se ve: El caldo midiéndose en una jarra",
              "Texto: «ES EL CALDO»", "Expresión: seria", "Reparto con el título: la miniatura da la pista", "título propio", "nota:", "destino:"):
    assert trozo in m["text"], trozo
listo = cuerpo(m["html"], "ELEGIR")
assert listo == "ELEGIR " + c["algunas"] + "\ntitulo: 2\nminiatura: 1"
assert llega("marta@ejemplo.com", "Re: títulos", "El segundo título me parece el mejor de todos con diferencia", mid(m)) == "texto libre en una puerta que no lo admite: botones"
assert llega("marta@ejemplo.com", "ELEGIR " + c["algunas"], listo) == f"decidida {g} (algunas)"                 # basta con enviarlo
assert PU.leer(g)["decision"]["texto"] == "titulo: 2\nminiatura: 1"
c2 = cod(g); assert llega("marta@ejemplo.com", "DESHACER " + c2["deshacer"], "DESHACER " + c2["deshacer"]) == f"deshecha {g}"
HC.enviar_puertas(); c = cod(g)
propio = "ELEGIR " + c["algunas"] + "\ntitulo: El arroz al horno no se seca solo\nminiatura: 2\nnota: sin texto encima\ndestino: el vídeo del caldo"
assert llega("marta@ejemplo.com", "ELEGIR " + c["algunas"], propio) == f"decidida {g} (algunas)" and PU.leer(g)["decision"]["texto"].startswith("titulo: El arroz al horno no se seca solo\nminiatura: 2\nnota:")
'
caso "voz: el perfil va a quien presenta; su respuesta con una instrucción vale como rehacer" '
e = E.lanzar("demo", "perfil-voz"); d = E.carpeta("demo", e["id"])
(d / "perfil-voz.md").write_text("# Perfil de voz\n\nHabla de tú, con frases cortas, y remata con una pregunta.\n")
g = abrir(e["id"]); HC.enviar_puertas(); env = enviados()
m = env[-1]
assert m["to"] == "pepa@ejemplo.com" and "remata con una pregunta" in m["text"] and cuerpo(m["html"], "APROBAR") and cuerpo(m["html"], "REHACER")
assert llega("pepa@ejemplo.com", "Re: voz", "Yo nunca digo «remata»: quita esa palabra y pon mis muletillas de verdad", mid(m)) == f"decidida {g} (cambios)"
assert PU.leer(g)["decision"]["texto"].startswith("Yo nunca digo")
'

caso "peticiones de marketing, sin modelo: ESTADO, PROPUESTA y TEMA (con PILAR); con varios canales hay que decir cuál; lo demás, la ayuda con sus tres botones" '
n = len(enviados())
assert llega("marta@ejemplo.com", "ESTADO", "ESTADO") == "ayuda: falta decir el canal" and "CANAL: <nombre corto>" in enviados()[-1]["text"]
assert llega("marta@ejemplo.com", "ESTADO", "ESTADO\nCANAL: demo") == "petición: estado"
r = enviados()[-1]; assert r["subject"] == "📋 Estado de Cocina Clara" and "Sofrito sin prisa" in r["text"] and "Aprobado" in r["text"] and "Descartado" in r["text"], r["text"]
assert llega("luis@ejemplo.com", "Re: ESTADO", "ESTADO") == "petición: estado" and "Todavía no hay ningún vídeo" in enviados()[-1]["text"]      # con un solo canal no hace falta decirlo
antes = len(E.listar("otro"))
assert llega("luis@ejemplo.com", "Propuesta de colaboración", "Propuesta de colaboración para el canal, ¿hablamos esta semana?") == "ayuda: no es una orden" and len(E.listar("otro")) == antes
ay = enviados()[-1]
assert cuerpo(ay["html"], "PROPUESTA") == "PROPUESTA" and cuerpo(ay["html"], "ESTADO") == "ESTADO" and cuerpo(ay["html"], "TEMA") == "TEMA: " + HC.AYUDA_TEMA + "\nPILAR: " + HC.AYUDA_PILAR
assert llega("luis@ejemplo.com", "PROPUESTA", "PROPUESTA").startswith("petición: propuesta propuesta-") and [x["pipeline"] for x in E.listar("otro")] == ["propuesta"]
assert E.listar("otro")[0]["quien"] == "luis (correo)" and "Estoy preparando una propuesta" in enviados()[-1]["text"]
assert llega("luis@ejemplo.com", "PROPUESTA", "PROPUESTA").startswith("petición: propuesta") and len(E.listar("otro")) == 1 and "ya había una en marcha" in enviados()[-1]["text"]
assert llega("marta@ejemplo.com", "TEMA: ", "TEMA: " + HC.AYUDA_TEMA + "\nPILAR: " + HC.AYUDA_PILAR + "\nCANAL: demo") == "ayuda: tema vacío"          # el botón enviado sin escribir
assert llega("marta@ejemplo.com", "TEMA: ", "TEMA: El arroz que no se pasa\nPILAR: postres\nCANAL: demo") == "ayuda: pilar desconocido" and "arroces, guisos" in enviados()[-1]["text"]
res = llega("marta@ejemplo.com", "TEMA: ", "TEMA: El arroz que no se pasa\nPILAR: arroces\nCANAL: demo\n\n-- \nMarta")
e = next(x for x in E.listar("demo") if x["params"].get("tema") == "El arroz que no se pasa")
assert res == "petición: tema " + e["id"] and e["pipeline"] == "titulo-miniatura" and e["params"]["pilar"] == "arroces" and e["quien"] == "marta (correo)"
assert llega("marta@ejemplo.com", "TEMA: Guisos de cuchara en verano", "CANAL: demo").startswith("petición: tema")                                   # el tema, en el asunto; sin pilar
assert next(x for x in E.listar("demo") if x["params"].get("tema") == "Guisos de cuchara en verano")["params"]["pilar"] == "sin-pilar"
assert llega("pepa@ejemplo.com", "PROPUESTA", "PROPUESTA") == "ayuda: no es de marketing" and "quien lleva marketing" in enviados()[-1]["text"]
assert llega("dario@ejemplo.com", "", "") == "vacío"
'
caso "tope: a partir de 20 correos sin código de una persona en un día, no se atienden más (los códigos, siempre)" '
hechos = sum(1 for l in (B.home() / "correo/recibidos.jsonl").read_text().splitlines() if "mario@ejemplo.com" in l and "\"sin_codigo\": true" in l)
for i in range(HC.TOPE_DIA - hechos):
    assert llega("mario@ejemplo.com", "hola", f"hola {i}").startswith("ayuda"), i
n = len(enviados())
assert llega("mario@ejemplo.com", "hola", "otra más") == "descartado: tope diario de correos sin código" and len(enviados()) == n
eid, g = guion("Tope"); HC.enviar_puertas(); c = cod(g)
assert llega("mario@ejemplo.com", "APROBAR " + c["acepto"], "APROBAR " + c["acepto"]) == f"firmada {g} (acepto)"
'
caso "resumen diario: un correo por persona con sus puertas abiertas y su antigüedad, solo si alguna lleva más de 24 h, y una vez al día" '
for p in PU.puertas(("abierta", "decidida")):                       # se parte de cero: solo las puertas de este caso
    p["estado"] = "caducada"; B.escribir(PU.indice(p["id"]), p)
_, g1 = guion("Resumen uno"); _, g2 = guion("Resumen dos"); _, g3 = guion("Resumen tres", indice=2, datos=("verificado",))
HC.enviar_puertas(); n = len(enviados())
assert HC.resumen() == 0 and len(enviados()) == n                   # ninguna lleva más de 24 h
p = PU.leer(g1); p["creada"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 50 * 3600)); B.escribir(PU.indice(g1), p)
assert HC.resumen() == 2                                            # Marta y Mario (marketing); a Pepa, cuya puerta es de hoy, no
mas = nuevos(n)
assert sorted(e["to"] for e in mas) == ["mario@ejemplo.com", "marta@ejemplo.com"] and all(e["subject"] == "⏳ Te esperan 2 decisión(es)" for e in mas)
t = mas[0]["text"]; assert "espera desde hace 2 días" in t and t.count("•") == 2 and t.index("2 días") < t.index("0 h")
assert HC.resumen() == 0 and len(enviados()) == n + 2               # hoy ya se envió
'

# ── la CLI y el ciclo ──
N=$(wc -l < "$T/buzon/enviados.jsonl")
si "hyt correo prueba: a las personas de marketing del canal" "$H correo prueba demo | grep -q 'encolado para 2 persona(s) de marketing'"
si "hyt correo ciclo: recoge y envía" "$H correo ciclo | grep -q 'recogidos 0 · enviados 2' && [ \$(wc -l < $T/buzon/enviados.jsonl) = \$((N + 2)) ] && tail -1 $T/buzon/enviados.jsonl | jq -e '.subject | test(\"Prueba del correo de hermes-youtube\")'"
si "hyt correo resumen" "$H correo resumen | grep -q '0 resumen(es) encolado(s)'"
si "sin configurar, el ciclo no hace nada y la CLI lo dice" "! HYT_CORREO_URL= $H correo ciclo 2> $T/err && grep -q 'no está configurado' $T/err && [ \"\$(HYT_CORREO_URL= python3 $P/hyt_correo.py ciclo)\" = 'recogidos 0 · enviados 0' ]"
si "un envío que falla se queda en la cola con su error y sale cuando vuelve el transporte" "$H correo prueba otro >/dev/null && HYT_CORREO_URL=http://127.0.0.1:9 $H correo ciclo | grep -q 'enviados 0' && [ \$(ls $HERMES_YT_HOME/correo/salida | wc -l) = 2 ] && jq -e '.intentos == 1' $HERMES_YT_HOME/correo/salida/\$(ls $HERMES_YT_HOME/correo/salida | head -1) && $H correo ciclo | grep -q 'enviados 2'"
si "el buzón del worker no lleva datos de una instalación real" "grep -q 'ejemplo.com' $ROOT/correo/wrangler.toml && grep -q 'PON_AQUI' $ROOT/correo/wrangler.toml"
exit $fail
