#!/usr/bin/env bash
# Estado real por turno (pre_llm_call): puertas con fecha y edad, en marcha, lo reciente y el último resultado sin
# puerta de cada tipo; claves tapadas; nada en cron; la coordinadora ve todos los canales.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
python3 "$P/hyt_canales.py" alta demo "Canal Demo" "Persona Ejemplo" >/dev/null
python3 "$P/hyt_canales.py" alta otro "Otro Canal" "Otra Persona" >/dev/null
echo "{\"ana\":{\"nombre\":\"Ana\",\"medios\":{\"local\":\"$(id -un)\"},\"canales\":[\"*\"]}}" > "$HERMES_YT_HOME/aprobadores.json"
mkdir -p "$HERMES_YT_HOME/canales/demo/extensiones/pipelines"
cat > "$HERMES_YT_HOME/canales/demo/extensiones/pipelines/suelta.json" <<'J'
{"id":"suelta","nombre":"Nota suelta","etapas":[{"id":"nota","titulo":"Nota","perfil":"yt-guionista","skill":"escaleta","salida":"nota.md"}]}
J
python3 - "$P" <<'PY' && ok "turno: puertas con fecha y edad, aviso grave, en marcha, lo reciente, resultado sin puerta con su titular, claves tapadas" || bad "turno"
import importlib.util, json, sys, time
from pathlib import Path
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
def m(n):
    s = importlib.util.spec_from_file_location(n, P / f"{n}.py"); x = importlib.util.module_from_spec(s); sys.modules[n] = x; s.loader.exec_module(x); return x
B, C, E, PU, ES = m("hyt_base"), m("hyt_canales"), m("hyt_encargos"), m("hyt_puertas"), m("hyt_estado")
vieja = PU.abrir("demo", tipo="decision", titulo="📊 Ya decidida", texto="x")["id"]
PU.decidir_local(vieja, "rechazo", "No procede")
g = PU.abrir("demo", tipo="decision", titulo="📊 Una decisión", texto="x")["id"]
p = PU.leer(g); p["creada"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 86400)); p["revision"] = {"graves": 1}
B.escribir(PU.indice(g), p)
en_marcha = E.lanzar("demo", "guion", {"tema": "Un tema en marcha", "pilar": "p"})
e = E.lanzar("demo", "suelta")
d = E.carpeta("demo", e["id"]); (d / "nota.md").write_text("# Nota: tres ideas y una clave ghp_" + "a" * 30 + "\n...")
e.update(estado="hecho", informe=True); E.guardar("demo", e)
t = ES.turno("demo")
assert "Estado real de Canal Demo" in t and "📊 Una decisión" in t and "hace 3 días" in t and "aviso grave" in t, t
assert "Ya decidida" not in t and "puerta decision: rechazo → descartado" in t, t           # lo firmado sale en lo reciente
assert f"- Guion · en-curso" in t and en_marcha["id"] in t, t
assert "Nota suelta" in t and "Nota: tres ideas" in t and "[clave tapada]" in t and "ghp_" not in t, t
assert len(t) <= ES.MAX_CANAL
assert "Puertas pendientes: ninguna." in ES.turno("otro")
c = ES.canales()
assert "Estado real de los canales" in c and "Disco" in c, c
assert "- Canal Demo (demo): 1 puerta(s), 1 en marcha" in c and "- Otro Canal (otro): 0 puerta(s), 0 en marcha" in c, c
C.config("otro", "politicas.pausado", True)
en_marcha.update(estado="parado"); E.guardar("demo", en_marcha)
(B.home() / "copia.json").write_text(json.dumps({"ok": False, "motivo": "no se pudo subir", "ts": "2026-11-16T03:00:00Z"}))
c = ES.canales()
assert "1 en marcha, 1 parado(s)" in c and "(otro): 0 puerta(s), 0 en marcha · ⏸ en pausa" in c and "Copia: FALLÓ: no se pudo subir" in c, c
assert "hyt estado <canal>" in c and "web" not in c
PY
python3 - "$P" <<'PY' && ok "el hook: solo en la coordinadora (perfil default); contexto en Telegram y CLI, nada en cron" || bad "hook"
import importlib.util, sys
from pathlib import Path
from types import SimpleNamespace as NS
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
s = importlib.util.spec_from_file_location("hermes_youtube_plugin", P / "__init__.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
hooks, secciones, ordenes = {}, {}, {}
def ctx(perfil):
    return NS(profile_name=perfil, register_hook=lambda n, f, **k: hooks.__setitem__(n, f),
              register_telegram_handler=lambda f: None, register_command=lambda n, f, **k: ordenes.__setitem__(n, k),
              register_system_prompt_section=lambda n, f, **k: secciones.__setitem__(n, f))
m.register(ctx("yt-guionista"))
assert hooks == {}, "un perfil de rol no recibe el estado en cada turno"
m.register(ctx("default"))
h = hooks["pre_llm_call"]
assert "Estado real de los canales" in h(platform="telegram")["context"]
assert "Canal Demo" in h(platform="cli")["context"]
assert h(platform="cron") is None
assert sorted(ordenes) == ["yt", "yt_pausar", "yt_puertas", "yt_reanudar"], sorted(ordenes)
assert list(secciones) == ["hermes-youtube.canales"]
resumen = secciones["hermes-youtube.canales"]({"profile_name": "default"})
assert resumen.startswith("## hermes-youtube: tus canales") and "Canal Demo (demo)" in resumen, resumen
assert secciones["hermes-youtube.canales"]({"profile_name": "yt-guionista"}) == ""
PY
exit $fail
