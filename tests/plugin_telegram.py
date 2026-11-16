"""Plugin de Telegram con bot y updates falsos (sin red): publicar en el chat del canal, autorización, texto por
respuesta, deshacer, firma al acabar la ventana, elegir, avisos graves, lecciones, comandos y el resumen en el prompt."""
import asyncio, importlib.util, json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
T = Path(tempfile.mkdtemp()); HOME = T / "home"
os.environ.update(HERMES_YT_HOME=str(HOME), HERMES_YT_DESHACER_S="0", TELEGRAM_HOME_CHANNEL="999", HYT_SIN_PASOS="1",
                  HERMES_BIN=str(ROOT / "tests/dobles/hermes"), FALSO_LLAMADAS=str(T / "llamadas"), FALSO_TABLEROS=str(T / "tableros"))
spec = importlib.util.spec_from_file_location("hyt_plugin", ROOT / "plugin/hermes-youtube/__init__.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
C, PU, B = m.C, m.PU, m.B
fallos = 0
def ok(c, t):
    global fallos
    print(("ok   " if c else "FAIL ") + t); fallos += (not c)

class Bot:
    def __init__(s): s.enviados, s.editados, s.n = [], [], 100
    async def send_message(s, chat_id, text, reply_markup=None, message_thread_id=None, **k):
        s.n += 1; s.enviados.append(NS(chat=chat_id, hilo=message_thread_id, text=text, kb=reply_markup, resp=k.get("reply_to_message_id"))); return NS(chat_id=chat_id, message_id=s.n)
    async def edit_message_text(s, chat_id, message_id, text, reply_markup=None): s.editados.append(NS(text=text, kb=reply_markup))

class Query:
    def __init__(s, data, uid): s.data, s.from_user, s.id = data, NS(id=uid, username="u"), "cb"; s.message = NS(chat_id=111, message_id=7, message_thread_id=55); s.respuestas = []; s.sin_teclado = False
    async def answer(s, text=None, show_alert=False): s.respuestas.append(text)
    async def edit_message_reply_markup(s, reply_markup=None): s.sin_teclado = reply_markup is None

def botones(kb): return [b.callback_data for f in kb.inline_keyboard for b in f] if kb else []
def etiquetas(kb): return [b.text for f in kb.inline_keyboard for b in f] if kb else []

C.alta("demo", "Canal Demo", "Persona Ejemplo")
C.alta("otro", "Otro Canal", "Otra Persona")
C.config("demo", "telegram", {"chat_id": "111", "thread_id": "55"})
(HOME / "aprobadores.json").write_text(json.dumps({"ana": {"nombre": "Ana", "medios": {"telegram": "111"}, "canales": ["*"]},
                                                   "luis": {"nombre": "Luis", "medios": {"telegram": "222"}, "canales": ["otro"]}}))
bot = Bot(); ctx = NS(bot=bot)

async def responder(texto, uid=111):
    pid = int(next(iter(m._pendientes())))
    msg = NS(text=texto, from_user=NS(id=uid, username="u"), message_id=9, reply_to_message=NS(message_id=pid))
    async def rep(t): msg.r = t
    msg.reply_text = rep
    await m._on_respuesta(NS(message=msg), ctx)
    return msg

async def main():
    m._RT["app"] = NS(bot=bot); m._RT["bucle"] = asyncio.get_running_loop().create_future()
    ok(m.PREFIJO == "ys", "el prefijo de los botones de puerta es «ys»")
    g = PU.abrir("demo", tipo="decision", titulo="📊 Una decisión", texto="3 propuestas")["id"]
    await m._vuelta()
    e = bot.enviados[-1]
    ok(e.chat == 111 and e.hilo == 55, "la puerta se publica en el chat (y tema) configurado para su canal")
    ok(botones(e.kb) == [f"ys:acepto:{g}", f"ys:cambios:{g}", f"ys:rechazo:{g}"], f"botones con prefijo ys: ({botones(e.kb)})")
    ok(etiquetas(e.kb) == ["✅ Aprobar", "✏️ Rehacer", "🗑 Rechazar"], f"aprobar, rehacer y rechazar ({etiquetas(e.kb)})")
    n = len(bot.enviados); await m._vuelta(); ok(len(bot.enviados) == n, "una puerta ya publicada no se vuelve a enviar")
    q = Query(f"ys:acepto:{g}", 999); await m._on_boton(NS(callback_query=q), ctx)
    ok("No estás autorizado" in (q.respuestas[-1] or ""), "rechaza a quien no es aprobador")
    q = Query(f"ys:acepto:{g}", 222); await m._on_boton(NS(callback_query=q), ctx)
    ok("No estás autorizado" in (q.respuestas[-1] or "") and PU.leer(g)["estado"] == "abierta", "y a quien no decide en este canal")
    q = Query(f"ys:cambios:{g}", 111); await m._on_boton(NS(callback_query=q), ctx)
    pend = m._pendientes(); ok(len(pend) == 1 and bot.enviados[-1].hilo == 55 and "✏️ Rehacer" in bot.enviados[-1].text, "«Rehacer» pide el texto en el mismo tema")
    msg = await responder("Menos propuestas", uid=222)
    ok("Solo puede responder quien pulsó" in msg.r and PU.leer(g)["estado"] == "abierta", "solo responde quien pulsó el botón")
    q = Query(f"ys:cambios:{g}", 111); await m._on_boton(NS(callback_query=q), ctx)
    await responder("Menos propuestas")
    p = PU.leer(g)
    ok(p["estado"] == "decidida" and p["decision"]["texto"] == "Menos propuestas" and p["decision"]["actor"] == {"persona": "ana", "medio": "telegram", "id": "111"},
       "la respuesta crea la decisión con la identidad de Telegram")
    ok(botones(bot.editados[-1].kb) == [f"ys:deshacer:{g}"], "decidida: solo queda ↩ Deshacer")
    q = Query(f"ys:deshacer:{g}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok(PU.leer(g)["estado"] == "abierta", "Deshacer la reabre")
    q = Query(f"ys:rechazo:{g}", 111); await m._on_boton(NS(callback_query=q), ctx)
    await responder("No toca")
    await m._vuelta()
    p = PU.leer(g)
    ok(p["estado"] == "firmada" and p["resultado"] == "descartado" and p["firma"] == "Ana (telegram)", "pasada la ventana, el bucle firma")
    ok("✅ Ana (telegram): descartado" in bot.editados[-1].text, "el mensaje enseña el resultado")
    n = len(bot.editados); await m._vuelta()
    ok(len(bot.editados) == n, "una puerta firmada y al día no se vuelve a tocar")

    # aprobar no pide texto: se decide con el toque y se firma al acabar la ventana
    ga = PU.abrir("demo", tipo="alta", titulo="🧭 Alta", texto="x")["id"]
    await m._vuelta()
    ok(etiquetas(bot.enviados[-1].kb) == ["✅ Aprobar", "🗑 Rechazar"], "la puerta de alta: aprobar o rechazar")
    q = Query(f"ys:acepto:{ga}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok(PU.leer(ga)["estado"] == "decidida" and "Hecho" in (q.respuestas[-1] or "") and not m._pendientes(), "aprobar se decide con el toque, sin pedir texto")
    await m._vuelta(); ok(PU.leer(ga)["resultado"] == "aprobado", "y el bucle la firma")

    # una decisión tomada en local la firma quien la tomó, no el bucle
    gl = PU.abrir("demo", tipo="decision", titulo="📊 Local", texto="x")["id"]
    await m._vuelta()
    p = PU.leer(gl); p.update(estado="decidida", firmar_en=0, decision={"verbo": "acepto", "texto": "", "actor": {"persona": "ana", "medio": "local", "id": "x"}, "at": B.ahora()})
    B.escribir(PU.indice(gl), p); await m._vuelta()
    ok(PU.leer(gl)["estado"] == "decidida", "el bucle no firma lo decidido por el medio local")
    p = PU.leer(gl); p["estado"] = "reemplazada"; p["nota"] = "se abrió otra"; B.escribir(PU.indice(gl), p)

    # una puerta cerrada por fuera (sustituida): su mensaje pierde los botones y dice por qué
    await m._vuelta()
    ok(bot.editados[-1].kb is None and "Sustituida por una puerta nueva" in bot.editados[-1].text and "se abrió otra" in bot.editados[-1].text, "cerrada como reemplazada: sin botones y lo dice")
    n = len(bot.editados); await m._vuelta(); ok(len(bot.editados) == n, "y no se vuelve a editar")
    q = Query(f"ys:acepto:{gl}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok("ya está resuelta" in (q.respuestas[-1] or "") and bot.editados[-1].kb is None, "pulsar un botón viejo: lo dice y quita los botones")

    # elegir: el texto es la elección; «otra propuesta» no lo necesita
    ge = PU.abrir("demo", tipo="elegir-temas", titulo="💡 Temas", texto="1. A\n2. B\n3. C")["id"]
    await m._vuelta()
    e = bot.enviados[-1]
    ok(botones(e.kb) == [f"ys:algunas:{ge}", f"ys:cambios:{ge}", f"ys:rechazo:{ge}"] and etiquetas(e.kb) == ["✅ Elegir", "🔁 Otra propuesta", "🗑 Ninguno"],
       f"la puerta de elegir: elegir, otra propuesta o ninguno ({etiquetas(e.kb)})")
    q = Query(f"ys:algunas:{ge}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok("responde a este mensaje con lo que eliges" in bot.enviados[-1].text, "«Elegir» pide la elección por respuesta")
    await responder("El 1 y el 3")
    await m._vuelta()
    p = PU.leer(ge)
    ok(p["estado"] == "firmada" and p["decision"]["verbo"] == "algunas" and p["decision"]["texto"] == "El 1 y el 3" and p["resultado"] == "aprobado", "la elección queda firmada con su texto")

    # con un aviso grave de la revisión, la puerta no ofrece el botón de aprobar y lo dice
    R = m._cargar("hyt_revision")
    @R.regla("decision")
    def _grave(c, avisos): R._aviso(avisos, True, "prueba", "Falta algo imprescindible")
    g2 = PU.abrir("demo", tipo="decision", titulo="📊 Con aviso", texto="x")["id"]
    R.REGLAS.clear()
    await m._vuelta()
    e = bot.enviados[-1]
    ok("⛔ Falta algo imprescindible" in e.text and "aviso grave" in e.text and botones(e.kb) == [f"ys:cambios:{g2}", f"ys:rechazo:{g2}"],
       "con un aviso grave no hay botón de aprobar")
    q = Query(f"ys:acepto:{g2}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok("aviso grave" in (q.respuestas[-1] or "") and PU.leer(g2)["estado"] == "abierta", "y un botón de aprobar que alguien conserve tampoco vale")

    # papeles y cadena: la puerta dice quién decide; por Telegram solo quien tiene el papel (ni quien administra)
    E = m._cargar("hyt_encargos")
    eid = E.lanzar("demo", "guion", {"tema": "Un guion", "pilar": "p"})["id"]
    (E.carpeta("demo", eid) / "datos.json").write_text(json.dumps({"datos": [{"id": 1, "dato": "una cifra", "estado": "pendiente"}]}))
    gr = PU.abrir("demo", eid)["id"]
    await m._vuelta()
    e = bot.enviados[-1]
    ok("Puerta 1 de 3 · decide: marketing" in e.text.splitlines()[1] and botones(e.kb)[0] == f"ys:acepto:{gr}", f"la puerta de una cadena dice cuál es y quién la decide ({e.text.splitlines()[1]})")
    q = Query(f"ys:cambios:{gr}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok("papel «marketing»" in (q.respuestas[-1] or "") and not m._pendientes() and PU.leer(gr)["estado"] == "abierta", "quien administra no decide por Telegram una puerta con papel (ni se le pide el texto)")
    C.config("demo", "personas", {"ana": {"nombre": "Ana", "correo": "", "roles": ["marketing"]}})
    q = Query(f"ys:acepto:{gr}", 111); await m._on_boton(NS(callback_query=q), ctx)
    await m._vuelta(); await m._vuelta()
    gd = next(p for p in PU.puertas(("abierta",)) if p.get("encargo") == eid)
    ok(PU.leer(gr)["estado"] == "firmada" and "pasa a la puerta datos (datos)" in PU.leer(gr)["resultado"] and gd["tipo"] == "datos", "con el papel, aprueba; el bucle firma y abre la siguiente puerta de la cadena")
    e = next(x for x in reversed(bot.enviados) if "Puerta 2 de 3" in x.text)
    ok("decide: datos" in e.text and "Quedan 1 dato(s) por verificar" in e.text and botones(e.kb) == [f"ys:rechazo:{gd['id']}"], f"la puerta de datos avisa de lo pendiente y no ofrece aprobar ({botones(e.kb)})")
    q = Query(f"ys:rechazo:{gd['id']}", 111); await m._on_boton(NS(callback_query=q), ctx)
    ok("papel «datos»" in (q.respuestas[-1] or ""), "y marketing no decide la puerta de datos")
    C.config("demo", "personas", {})
    p = PU.leer(gd["id"]); p["estado"] = "caducada"; B.escribir(PU.indice(gd["id"]), p); await m._vuelta()

    # dónde se publica: el chat del canal; si no, el general de yt.json; si no, el chat principal; si no, los aprobadores
    go = PU.abrir("otro", tipo="decision", titulo="📊 Otro canal", texto="x")["id"]
    await m._vuelta()
    ok(bot.enviados[-1].chat == 999 and bot.enviados[-1].hilo is None, "sin chat propio, al chat principal")
    B.escribir(HOME / "yt.json", {"telegram": {"chat_id": "777", "thread_id": "8"}})
    ok(m._destinos(PU.leer(go)) == [(777, 8)] and m._destinos(None) == [(777, 8)] and m._destinos(PU.leer(g2)) == [(111, 55)], "el general de yt.json va antes que el chat principal; el del canal, antes que todos")
    (HOME / "yt.json").unlink(); del os.environ["TELEGRAM_HOME_CHANNEL"]
    ok(sorted(m._destinos(None)) == [(111, None), (222, None)], "sin nada configurado, a cada aprobador con Telegram")
    os.environ["TELEGRAM_HOME_CHANNEL"] = "999"

    # lecciones: aviso con botones «yl:», una vez; confirmar con una persona autorizada
    L = m._cargar("hyt_lecciones")
    (C.carpeta("demo") / "puertas.jsonl").write_text(json.dumps({"puerta": "gabcdef1234"}) + "\n")
    l = L.proponer("demo", "escribir", "Comprobar que la promesa del título aparece en el material antes de escribir", ["gabcdef1234"])
    n = len(bot.enviados); await m._avisar_lecciones(bot)
    e = bot.enviados[-1]
    ok(len(bot.enviados) == n + 1 and e.chat == 999 and botones(e.kb) == [f"yl:confirmar:{l['id']}", f"yl:descartar:{l['id']}"] and "uno de tus canales" in e.text,
       f"la lección propuesta llega con botones yl: ({botones(e.kb)})")
    await m._avisar_lecciones(bot); ok(len(bot.enviados) == n + 1, "y solo se avisa una vez")
    q = Query(f"yl:confirmar:{l['id']}", 999); await m._on_leccion(NS(callback_query=q), ctx)
    ok("No estás autorizado" in (q.respuestas[-1] or ""), "una lección no la confirma cualquiera")
    q = Query(f"yl:confirmar:{l['id']}", 111); await m._on_leccion(NS(callback_query=q), ctx)
    ok(q.respuestas[-1] == "Confirmada" and q.sin_teclado and L.todas()[0]["estado"] == "confirmada" and L.todas()[0]["por"] == "ana", "confirmada por una persona autorizada")

    # comandos y resumen en el prompt
    cmds, secciones, hooks, cableado = {}, {}, {}, []
    ctx_h = NS(profile_name="default", register_telegram_handler=lambda f: cableado.append(f),
               register_hook=lambda n, f, **k: hooks.__setitem__(n, f),
               register_command=lambda n, f, **k: cmds.__setitem__(n, (f, k)),
               register_system_prompt_section=lambda i, f, **k: secciones.__setitem__(i, f))
    m.register(ctx_h)
    ok(set(cmds) == {"yt", "yt_puertas", "yt_pausar", "yt_reanudar"}, f"comandos ({sorted(cmds)})")
    ok(all(not k.get("args_hint", "").startswith("<") for _, k in cmds.values()), "ninguna ayuda empieza por «<» (saldría del menú)")
    ok("Canal Demo (demo)" in cmds["yt"][0]("") and "Otro Canal" not in cmds["yt"][0]("demo"), "/yt da el estado (de todos o de un canal)")
    abiertas = len(PU.puertas(("abierta",)))
    ok(cmds["yt_puertas"][0]("") == f"Te reenvío {abiertas} decisión(es) pendiente(s)." and all(not p.get("telegram") for p in PU.puertas(("abierta",))), "/yt_puertas las deja listas para reenviarlas")
    n = len(bot.enviados); await m._vuelta(); ok(len(bot.enviados) == n + abiertas, "y el bucle las vuelve a publicar con sus botones")
    ok(cmds["yt_pausar"][0]("demo") == "Solo una persona autorizada." and not C.leer("demo")["politicas"]["pausado"], "/yt_pausar sin una persona autorizada no pausa")
    m._persona_sesion = lambda: ("ana", "111")
    ok("demo: en pausa" in cmds["yt_pausar"][0]("demo") and C.leer("demo")["politicas"]["pausado"], "/yt_pausar pausa un canal")
    ok("Todo reanudado" in cmds["yt_reanudar"][0]("") and "demo: reanudado" in cmds["yt_reanudar"][0]("demo") and not C.leer("demo")["politicas"]["pausado"], "/yt_reanudar reanuda (todo o un canal)")
    ok(len(cableado) == 1 and set(hooks) == {"pre_llm_call"}, "registra los manejadores de Telegram y el estado por turno")
    ok(set(secciones) == {"hermes-youtube.canales"}, f"la sección del prompt lleva el nombre nuevo ({sorted(secciones)})")
    resumen = secciones["hermes-youtube.canales"]
    ok("tus canales" in resumen({"profile_name": "default"}) and "Canal Demo" in resumen({"profile_name": "default"}), "la coordinadora ve sus canales en el prompt")
    ok(resumen({"profile_name": "yt-guionista"}) == "" and resumen({"profile_name": "otro"}) == "", "otros perfiles, nada")
    ok(m.log.name == "hermes_plugins.hermes_youtube", "el registro (logger) lleva el nombre del plugin")

asyncio.run(main())
sys.exit(1 if fallos else 0)
