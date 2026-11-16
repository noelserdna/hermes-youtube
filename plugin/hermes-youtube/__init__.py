"""hermes-youtube — plugin de Hermes: puertas en Telegram, notario, comandos y el estado de los canales para la coordinadora.

Telegram es un medio, no decide ni firma: (1) publica cada puerta abierta con sus botones en el chat configurado para
su canal (o en el chat principal), (2) convierte el toque de una persona autorizada en una decisión
(hyt_puertas.decidir), (3) deja una ventana para deshacer y (4) llama al notario (hyt_puertas.firmar), que valida y
ejecuta. La identidad sale del update de Telegram (from.id), nunca de un texto.

Los botones usan el prefijo «ys:» (puertas) y «yl:» (lecciones) para convivir con otros plugins de puertas.

El correo (hyt_correo: puertas con botones y código de un solo uso) va en su propia tarea, _bucle_correo(): cada
minuto recoge lo recibido, envía las puertas abiertas a quien tiene su papel, firma lo decidido por correo y avisa.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import shutil
import sys
import time
from pathlib import Path

log = logging.getLogger("hermes_plugins.hermes_youtube")
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
PU = _cargar("hyt_puertas")
_RT: dict = {"app": None}
PREFIJO = "ys"


def _path_cmds() -> str:
    dirs = [f"{Path.home()}/.local/bin", f"{Path.home()}/.npm-global/bin", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    for cmd in ("hermes", "node", "claude", "jq"):
        p = shutil.which(cmd)
        if p and str(Path(p).parent) not in dirs:
            dirs.insert(0, str(Path(p).parent))
    return ":".join(dirs)


os.environ["PATH"] = _path_cmds() + ":" + os.environ.get("PATH", "")


# ── dónde se publica ────────────────────────────────────────────────────────────────────────────────────────────────
def _destinos(puerta: dict | None) -> list:
    """[(chat_id, thread_id|None)]: el chat (y tema) configurado para el canal; si no, el general de yt.json, el chat
    principal o los aprobadores. Sin puerta (lecciones, que son de todos los canales), el general."""
    tg = {}
    if puerta and puerta.get("canal"):
        try:
            tg = C.leer(puerta["canal"]).get("telegram") or {}
        except B.Rechazo:
            tg = {}
    if not tg.get("chat_id"):
        tg = (B.leer(B.home() / "yt.json", {}) or {}).get("telegram") or {}
    if tg.get("chat_id"):
        return [(int(tg["chat_id"]), int(tg["thread_id"]) if tg.get("thread_id") else None)]
    home = os.environ.get("TELEGRAM_HOME_CHANNEL", "").strip()
    if home:
        return [(int(home), None)]
    return [(int(p["medios"]["telegram"]), None) for p in (B.leer(B.home() / "aprobadores.json", {}) or {}).values()
            if (p.get("medios") or {}).get("telegram")]


def _teclado(puerta: dict):
    from telegram import InlineKeyboardButton as Bt, InlineKeyboardMarkup as Mk
    if puerta.get("estado") == "decidida":
        return Mk([[Bt("↩ Deshacer", callback_data=f"{PREFIJO}:deshacer:{puerta['id']}")]])
    if puerta.get("estado") != "abierta":
        return None
    bs = [Bt(o["etiqueta"], callback_data=f"{PREFIJO}:{o['verbo']}:{puerta['id']}") for o in PU.opciones_vigentes(puerta)]
    return Mk([bs[i:i + 2] for i in range(0, len(bs), 2)])


# puertas cerradas sin decisión (por el sistema o en una sesión): el mensaje pierde los botones y dice por qué
CERRADAS = {"reemplazada": "🔁 Sustituida por una puerta nueva: esta ya no vale.",
            "caducada": "⌛ Caducada sin decidir: si hace falta, se vuelve a abrir."}


def _render(puerta: dict) -> str:
    partes = [puerta["titulo"], "", puerta["texto"]]
    cabecera = " · ".join(x for x in (
        f"Puerta {int(puerta.get('indice') or 0) + 1} de {puerta['total']}" if int(puerta.get("total") or 1) > 1 else "",
        f"decide: {puerta['papel']}" if puerta.get("papel") else "") if x)
    if cabecera:
        partes.insert(1, cabecera)
    if puerta.get("estado") == "abierta" and PU.datos_pendientes(puerta):
        partes += ["", f"🔎 Quedan {PU.datos_pendientes(puerta)} dato(s) por verificar, uno a uno: hasta entonces no se puede aprobar."]
    elif PU.graves(puerta) and puerta.get("estado") == "abierta":
        partes += ["", "⛔ Tiene un aviso grave: solo se puede rehacer o rechazar."]
    est = puerta.get("estado")
    dec = puerta.get("decision") or {}
    if est == "decidida":
        quien = (dec.get("actor") or {}).get("persona")
        falta = max(0, int(float(puerta.get("firmar_en") or 0) - time.time()))
        partes += ["", f"🕒 Decidido por {quien}: «{dec.get('verbo')}». Se ejecuta en {falta // 60} min {falta % 60} s si nadie lo deshace."]
    elif est == "firmada":
        partes += ["", f"✅ {puerta.get('firma')}: {puerta.get('resultado')}"]
    elif est == "error":
        partes += ["", f"⚠️ No se pudo completar: {puerta.get('error')}"]
    elif est in CERRADAS:
        partes += ["", CERRADAS[est] + (f" ({puerta['nota']})" if puerta.get("nota") else "")]
    return "\n".join(partes)[:4000]


def _vista(puerta: dict) -> str:
    return "|".join([puerta.get("estado", ""), str((puerta.get("decision") or {}).get("at", ""))])


async def _publicar(bot, puerta: dict) -> None:
    enviados = []
    for chat, hilo in _destinos(puerta):
        m = await bot.send_message(chat_id=chat, message_thread_id=hilo, text=_render(puerta), reply_markup=_teclado(puerta))
        enviados.append({"chat": m.chat_id, "msg": m.message_id})
    PU.marcar(puerta["id"], telegram=enviados, tg_vista=_vista(puerta))


async def _sincronizar(bot, puerta: dict) -> None:
    if not puerta.get("telegram") or puerta.get("tg_vista") == _vista(puerta):
        return
    for t in puerta["telegram"]:
        try:
            await bot.edit_message_text(chat_id=t["chat"], message_id=t["msg"], text=_render(puerta), reply_markup=_teclado(puerta))
        except Exception as e:
            log.debug("hermes-youtube: no se pudo editar %s: %s", t, e)
    PU.marcar(puerta["id"], tg_vista=_vista(puerta))


# ── botones y respuestas ────────────────────────────────────────────────────────────────────────────────────────────
def _pendientes() -> dict:
    return B.leer(B.home() / "pendientes.json", {}) or {}


def _pendiente(msg_id, valor=None, sacar: bool = False):
    d = _pendientes()
    if sacar:
        v = d.pop(str(msg_id), None)
        B.escribir(B.home() / "pendientes.json", d)
        return v
    d[str(msg_id)] = valor
    B.escribir(B.home() / "pendientes.json", d)
    return valor


async def _on_boton(update, context) -> None:
    _asegurar_bucle()
    q = update.callback_query
    _, verbo, gid = (q.data.split(":", 2) + ["", ""])[:3]
    persona, _ = PU.persona_de("telegram", q.from_user.id)
    if not persona:
        await q.answer("No estás autorizado para decidir esta puerta", show_alert=True)
        return
    try:
        puerta = PU.leer(gid)
    except B.Rechazo as e:
        await q.answer(str(e), show_alert=True)
        return
    if verbo == "deshacer":
        try:
            puerta = PU.deshacer(gid, persona)
        except B.Rechazo as e:
            await q.answer(str(e), show_alert=True)
            return
        await q.answer("Deshecho: vuelve a estar pendiente")
        await _sincronizar(context.bot, puerta)
        return
    if not PU.puede_decidir(persona, puerta["canal"], puerta.get("papel", ""), "telegram"):
        await q.answer(PU._no_autorizado(puerta.get("papel", "")), show_alert=True)
        return
    opcion = next((o for o in puerta.get("opciones", []) if o["verbo"] == verbo), None)
    if not opcion or puerta.get("estado") != "abierta":
        await q.answer("Esta puerta ya está resuelta" if opcion else "Opción no válida", show_alert=True)
        try:   # que el mensaje deje de ofrecer botones que ya no valen
            await context.bot.edit_message_text(chat_id=q.message.chat_id, message_id=q.message.message_id,
                                                text=_render(puerta), reply_markup=_teclado(puerta))
        except Exception:   # noqa: BLE001
            pass
        return
    if opcion.get("texto"):
        from telegram import ForceReply
        await q.answer()
        m = await context.bot.send_message(
            chat_id=q.message.chat_id, message_thread_id=getattr(q.message, "message_thread_id", None),
            text=(f"{opcion['etiqueta']}: responde a este mensaje con lo que eliges." if verbo == "algunas" else
                  f"{opcion['etiqueta']}: responde a este mensaje explicando qué quieres, con tus palabras."),
            reply_markup=ForceReply(selective=True, input_field_placeholder="Qué eliges, qué cambiar o por qué…"))
        _pendiente(m.message_id, [gid, verbo, persona])
        return
    await q.answer(await _decidir(context.bot, gid, verbo, "", q.from_user, persona))


async def _decidir(bot, gid: str, verbo: str, texto: str, user, persona: str) -> str:
    try:
        puerta = PU.decidir(gid, verbo, texto, persona, "telegram", str(user.id), {"user": user.username or ""})
    except B.Rechazo as e:
        return str(e)
    await _sincronizar(bot, puerta)
    return f"Hecho. Tienes {PU.deshacer_s() // 60} min para deshacerlo."


async def _on_respuesta(update, context) -> None:
    m = update.message
    gid, verbo, persona = _pendiente(m.reply_to_message.message_id, sacar=True)
    if PU.persona_de("telegram", m.from_user.id)[0] != persona:
        await m.reply_text("Solo puede responder quien pulsó el botón.")
        return
    await m.reply_text(await _decidir(context.bot, gid, verbo, m.text.strip(), m.from_user, persona))


# ── lecciones entre canales ────────────────────────────────────────────────────────────────────────────────────────────
async def _avisar_lecciones(bot) -> None:
    L = _cargar("hyt_lecciones")
    avisadas = B.leer(B.home() / "lecciones-avisadas.json", {}) or {}
    from telegram import InlineKeyboardButton as Bt, InlineKeyboardMarkup as Mk
    for l in L.pendientes():
        clave = f"{l['id']}:{l['estado']}"
        if clave in avisadas:
            continue
        if l["estado"] == "propuesta":
            texto = (f"💡 Lección propuesta desde uno de tus canales (etapa «{l['etapa']}»):\n\n{l['regla']}\n\n"
                     "Si la confirmas, se tendrá en cuenta en los demás canales.")
            kb = Mk([[Bt("✅ Confirmar", callback_data=f"yl:confirmar:{l['id']}"), Bt("🗑 Descartar", callback_data=f"yl:descartar:{l['id']}")]])
        else:
            texto = f"♻️ Esta lección ya se ha usado en {len(l['usos'])} canales. ¿Sigue sirviendo?\n\n{l['regla']}"
            kb = Mk([[Bt("♻️ Mantener", callback_data=f"yl:mantener:{l['id']}"), Bt("⌛ Caducar", callback_data=f"yl:caducar:{l['id']}")]])
        for chat, hilo in _destinos(None):
            await bot.send_message(chat_id=chat, message_thread_id=hilo, text=texto, reply_markup=kb)
        avisadas[clave] = B.ahora()
        B.escribir(B.home() / "lecciones-avisadas.json", avisadas)


async def _on_leccion(update, context) -> None:
    q = update.callback_query
    _, accion, lid = (q.data.split(":", 2) + ["", ""])[:3]
    persona, _ = PU.persona_de("telegram", q.from_user.id)
    if not persona:
        await q.answer("No estás autorizado", show_alert=True)
        return
    try:
        l = _cargar("hyt_lecciones").decidir(lid, accion, persona)
    except B.Rechazo as e:
        await q.answer(str(e), show_alert=True)
        return
    await q.answer({"confirmada": "Confirmada", "descartada": "Descartada", "caducada": "Caducada"}.get(l["estado"], "Hecho"))
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── el bucle: publicar, firmar, sincronizar ────────────────────────────────────────────────────────────────────
async def _vuelta() -> None:
    bot = _RT["app"].bot
    if time.time() - _RT.get("vueltas_t", 0) > 30:   # la verificación pidió cambios: vuelta automática (una vez)
        _RT["vueltas_t"] = time.time()
        try:
            for slug, eid, desde in await asyncio.to_thread(_cargar("hyt_encargos").vueltas_pendientes):
                log.info("hermes-youtube: %s/%s vuelve a %s (la verificación pidió cambios)", slug, eid, desde)
        except Exception as e:   # noqa: BLE001 — nunca para el bucle de las puertas
            log.warning("hermes-youtube: vueltas de verificación: %s", e)
    for p in PU.puertas(("abierta", "decidida", "error", "firmada", *CERRADAS)):
        if p["estado"] in ("firmada", *CERRADAS) and p.get("tg_vista") == _vista(p):
            continue
        if p["estado"] in CERRADAS:
            if p.get("telegram"):
                await asyncio.wait_for(_sincronizar(bot, p), 60)
            continue
        if p["estado"] in ("abierta", "decidida") and not p.get("telegram"):
            await asyncio.wait_for(_publicar(bot, p), 60)
            continue
        if p["estado"] == "decidida" and time.time() >= float(p.get("firmar_en") or 0) \
                and (p.get("decision") or {}).get("actor", {}).get("medio") != "local":
            try:
                p = await asyncio.to_thread(PU.firmar, p["id"])
            except B.Rechazo as e:
                log.warning("hermes-youtube: no se pudo firmar %s: %s", p["id"], e)
            p = PU.leer(p["id"])
        await asyncio.wait_for(_sincronizar(bot, p), 60)


async def _bucle() -> None:
    log.info("hermes-youtube: bucle en marcha")
    while True:
        await asyncio.sleep(5)
        try:
            await _vuelta()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("hermes-youtube: error en una vuelta del bucle (sigue)")
        try:
            await _avisar_lecciones(_RT["app"].bot)
        except Exception:
            log.exception("hermes-youtube: error al avisar de lecciones")
        try:
            B.escribir(B.home() / "latido.json", {"ts": B.ahora(), "pid": os.getpid()})
        except Exception:
            pass


async def _bucle_correo() -> None:
    """El correo va en su propia tarea (cada minuto, en un hilo): nunca frena la firma de las puertas. Si no está
    configurado, el ciclo no hace nada."""
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_cargar("hyt_correo").ciclo)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("hermes-youtube: error en el ciclo del correo (sigue)")


def _asegurar_bucle() -> None:
    t = _RT.get("bucle")
    if t is None or t.done():
        _RT["bucle"] = asyncio.get_running_loop().create_task(_bucle())
    t = _RT.get("bucle_correo")
    if t is None or t.done():
        _RT["bucle_correo"] = asyncio.get_running_loop().create_task(_bucle_correo())


# ── comandos ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _persona_sesion():
    try:
        from gateway.session_context import get_session_env
        uid = get_session_env("HERMES_SESSION_USER_ID") or ""
    except Exception:
        uid = ""
    return (PU.persona_de("telegram", uid)[0], uid) if uid else (None, "")


def _cli(*args: str) -> str:
    import subprocess
    r = subprocess.run([sys.executable, str(AQUI / "hyt_cli.py"), *args], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "HYT_QUIEN": _persona_sesion()[0] or "telegram"})
    return (r.stdout if r.returncode == 0 else r.stderr).strip() or "Hecho."


def _foto(info) -> str:
    """Lo que la coordinadora (perfil default) sabe al abrir una sesión: sus canales y qué hay en marcha."""
    perfil = str((info or {}).get("profile_name") or "")
    try:
        if perfil == "default":
            return "## hermes-youtube: tus canales\n" + _cargar("hyt_cli").estado()[:3500]
    except Exception as e:
        log.warning("hermes-youtube: resumen de canales para %s: %s", perfil, e)
    return ""


PLATAFORMAS_TURNO = ("telegram", "cli", "email", "")   # conversación con una persona; no cron


def _hook_turno(**kw):
    """pre_llm_call de la coordinadora: el estado real de todos los canales en cada turno, recalculado."""
    if str(kw.get("platform") or "") not in PLATAFORMAS_TURNO:
        return None
    try:
        texto = _cargar("hyt_estado").canales()
        return {"context": texto} if texto else None
    except Exception as e:   # noqa: BLE001 — nunca bloquea un turno
        log.warning("hermes-youtube: estado por turno: %s", e)
        return None


def register(ctx):
    # Hermes carga los plugins por perfil. El bucle de puertas, los botones y los comandos viven en el perfil principal
    # (un solo dueño del bot), que es además el de la coordinadora: solo ella recibe el estado en cada turno.
    try:
        perfil = str(getattr(ctx, "profile_name", "") or "")
    except Exception:
        perfil = ""
    if hasattr(ctx, "register_hook") and perfil == "default":
        ctx.register_hook("pre_llm_call", _hook_turno)

    def _wire(application, adapter):
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters

        class _EsRespuesta(filters.MessageFilter):
            def filter(self, message):
                r = message.reply_to_message
                return bool(r and str(r.message_id) in _pendientes())

        _RT["app"] = application
        application.add_handler(CallbackQueryHandler(_on_boton, pattern=rf"^{PREFIJO}:"))
        application.add_handler(CallbackQueryHandler(_on_leccion, pattern=r"^yl:"))
        application.add_handler(MessageHandler(filters.TEXT & _EsRespuesta(), _on_respuesta))
        _asegurar_bucle()

    def _cmd_yt(raw: str = "") -> str:
        return _cli("estado", *raw.split()[:1])

    def _cmd_puertas(raw: str = "") -> str:
        abiertas = PU.puertas(("abierta",))
        for p in abiertas:   # el bucle las vuelve a publicar con sus botones
            PU.marcar(p["id"], telegram=None, tg_vista=None)
        return f"Te reenvío {len(abiertas)} decisión(es) pendiente(s)." if abiertas else "No hay nada pendiente de decidir."

    def _cmd_pausar(raw: str = "") -> str:
        return _cli("pausar", raw.split()[0] if raw.split() else "todo") if _persona_sesion()[0] else "Solo una persona autorizada."

    def _cmd_reanudar(raw: str = "") -> str:
        return _cli("reanudar", raw.split()[0] if raw.split() else "todo") if _persona_sesion()[0] else "Solo una persona autorizada."

    ctx.register_telegram_handler(_wire)
    # args_hint siempre entre [ ]: Hermes deja fuera del menú las órdenes cuya ayuda empieza por «<»
    ctx.register_command("yt", _cmd_yt, description="Estado de tus canales de YouTube", args_hint="[canal]")
    ctx.register_command("yt_puertas", _cmd_puertas, description="Decisiones pendientes de tus canales")
    ctx.register_command("yt_pausar", _cmd_pausar, description="Pausa un canal (o todo)", args_hint="[canal|todo]")
    ctx.register_command("yt_reanudar", _cmd_reanudar, description="Reanuda un canal (o todo)", args_hint="[canal|todo]")
    if hasattr(ctx, "register_system_prompt_section"):
        ctx.register_system_prompt_section("hermes-youtube.canales", _foto, max_chars=4000)
