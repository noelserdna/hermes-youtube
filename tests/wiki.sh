#!/usr/bin/env bash
# Memoria del canal sin modelo: páginas fijas en sus momentos (configuración, puerta firmada con su corrección, voz
# aprobada), idempotentes, en index y log, con git propio; y cada etapa recibe lo que le toca.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros" HERMES_YT_DESHACER_S=0
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"; H="python3 $P/hyt_cli.py"
W=$HERMES_YT_HOME/canales/demo/wiki
mkdir -p "$HERMES_YT_HOME"
echo "{\"ana\":{\"nombre\":\"Ana\",\"medios\":{\"telegram\":\"111\",\"local\":\"$(id -un)\"},\"canales\":[\"*\"]}}" > "$HERMES_YT_HOME/aprobadores.json"

$H alta demo "Canal Demo" "Persona Ejemplo" | grep -q "Memoria sembrada" && ok "el alta siembra la memoria del canal" || bad "alta con memoria"
[ -d "$W/.git" ] && grep -q "Canal Demo" "$W/SCHEMA.md" && grep -q "## Fixed pages" "$W/SCHEMA.md" && [ -f "$W/index.md" ] && [ -f "$W/log.md" ] \
  && ok "wiki con git propio, índice, registro y un SCHEMA que conoce las páginas fijas" || bad "wiki inicial"
git -C "$W" log --format='%ae' | sort -u | grep -qx "hermes-youtube@localhost" && ok "los commits de la wiki son de hermes-youtube@localhost" || bad "autor de la wiki"
python3 - "$P" <<'PY' && ok "configuración → canal.md (sin enumerar los nombres vetados); puerta rechazada con motivo → decisiones y correcciones; idempotente; index, log y git" || bad "momentos"
import importlib.util, subprocess, sys
from pathlib import Path
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
def m(n):
    s = importlib.util.spec_from_file_location(n, P / f"{n}.py"); x = importlib.util.module_from_spec(s); sys.modules[n] = x; s.loader.exec_module(x); return x
B, C, PU, WK = m("hyt_base"), m("hyt_canales"), m("hyt_puertas"), m("hyt_wiki")
W = C.carpeta("demo") / "wiki"
canal = (W / "concepts/canal.md").read_text()
assert "Canal: Canal Demo (nombre corto: demo)" in canal and "Presenta: Persona Ejemplo" in canal and "title: El canal" in canal, canal
C.config("demo", "pilares", [{"id": "oficio", "nombre": "El oficio de cada día", "tipo": "pilar"}])
C.config("demo", "excluido", ["precios y ofertas"])
C.config("demo", "nombres_vetados", ["Nombre Reservado Uno", "Nombre Reservado Dos"])
canal = (W / "concepts/canal.md").read_text()
assert "El oficio de cada día (oficio, pilar)" in canal and "Contenido excluido: precios y ofertas" in canal, canal
assert "Nombres vetados: 2" in canal and "Nombre Reservado" not in canal, canal
g = PU.abrir("demo", tipo="decision", titulo="📊 X", texto="x")["id"]
PU.decidir_local(g, "rechazo", "Menos tecnicismos en el título")
assert "Menos tecnicismos" in (W / "concepts/correcciones.md").read_text()
assert "rechazo" in (W / "concepts/decisiones.md").read_text() and "Ana (local)" in (W / "concepts/decisiones.md").read_text()
idx = (W / "index.md").read_text(); assert "[[canal]]" in idx and "[[correcciones]]" in idx and idx.count("[[decisiones]]") == 1
antes = (W / "log.md").read_text(); WK.regenerar_decisiones("demo"); WK.regenerar_canal("demo"); assert (W / "log.md").read_text() == antes   # sin cambios, nada
g2 = PU.abrir("demo", tipo="decision", titulo="📊 Y", texto="y")["id"]
PU.decidir_local(g2, "acepto")
assert (W / "concepts/decisiones.md").read_text().count("\n- ") == 2 and "📊" not in (W / "concepts/correcciones.md").read_text()
assert (W / "concepts/correcciones.md").read_text().count("\n- ") == 1                              # aprobar no es una corrección
log = subprocess.run(["git", "-C", str(W), "log", "--oneline"], capture_output=True, text=True).stdout
assert "hermes-youtube: canal" in log and "hermes-youtube: correcciones" in log, log
assert subprocess.run(["git", "-C", str(W), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
assert WK.escribir("demo", "inventada", "x") is False                                              # solo las páginas fijas
PY
python3 - "$P" <<'PY' && ok "cada etapa recibe su memoria: canal y correcciones; escribir, voz y retención, además la voz" || bad "lectura por etapa"
import importlib.util, sys
from pathlib import Path
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
def m(n):
    s = importlib.util.spec_from_file_location(n, P / f"{n}.py"); x = importlib.util.module_from_spec(s); sys.modules[n] = x; s.loader.exec_module(x); return x
C, WK, ET = m("hyt_canales"), m("hyt_wiki"), m("hyt_etapa")
assert WK.LEE_DEFECTO == ["canal", "correcciones"]
assert all(v == ["canal", "voz", "correcciones"] for v in WK.LEE.values()) and {"escribir", "voz", "retencion"} <= set(WK.LEE)
assert WK.escribir("demo", "voz", "Habla de tú, con frases cortas y sin anglicismos.", ["encargo de prueba"], "prueba")
for etapa in ("escribir", "voz", "retencion"):
    mem = WK.para_etapa("demo", etapa)
    assert "Habla de tú" in mem and "Presenta: Persona Ejemplo" in mem and "Menos tecnicismos" in mem, (etapa, mem)
    assert "_Página que escribe" not in mem and "title:" not in mem
for etapa in ("verificar", "titular", "documentar", "una-etapa-nueva"):
    assert etapa not in WK.LEE
    mem = WK.para_etapa("demo", etapa)
    assert "Habla de tú" not in mem and "Presenta: Persona Ejemplo" in mem and "Menos tecnicismos" in mem, (etapa, mem)
assert len(WK.para_etapa("demo", "escribir")) <= WK.MAX_LEER
ctx = ET.contexto("demo", "escribir"); assert "## Memoria que te toca" in ctx and "Habla de tú" in ctx and "Menos tecnicismos" in ctx, ctx
assert "Habla de tú" not in ET.contexto("demo", "verificar") and "Memoria que te toca" not in ET.contexto("demo")
(C.carpeta("demo") / "extensiones/pipelines").mkdir(parents=True)
(C.carpeta("demo") / "extensiones/pipelines/propia.json").write_text('{"id":"propia","nombre":"Propia","etapas":[{"id":"repaso","titulo":"Repaso","perfil":"yt-doble","skill":"voz","lee":["voz"]}]}')
mem = WK.para_etapa("demo", "repaso", ET._lee("demo", "repaso"))
assert "Habla de tú" in mem and "Presenta:" not in mem                    # la etapa que declara «lee» recibe solo eso
assert WK.ultimas("demo", 2)[-1].endswith("[[voz]]")
PY
rm "$W/concepts/voz.md"
python3 - "$P" "$ROOT" <<'PY' && ok "voz.md nace cuando una persona aprueba el perfil de voz, no antes; rehacer o rechazar no la escriben" || bad "memoria al aprobar"
import importlib.util, subprocess, sys
from pathlib import Path
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
def m(n):
    s = importlib.util.spec_from_file_location(n, P / f"{n}.py"); x = importlib.util.module_from_spec(s); sys.modules[n] = x; s.loader.exec_module(x); return x
C, E, PU = m("hyt_canales"), m("hyt_encargos"), m("hyt_puertas")
voz = C.carpeta("demo") / "wiki/concepts/voz.md"
def correr(eid):
    r = subprocess.run(["bash", f"{sys.argv[2]}/etapa.sh", "demo", eid, "perfil"], capture_output=True, text=True)
    return __import__("json").loads(r.stdout.strip().splitlines()[-1])
e = E.lanzar("demo", "perfil-voz")
res = correr(e["id"])
assert res["outcome"] == "done" and res.get("puerta"), res
assert PU.leer(res["puerta"])["tipo"] == "voz" and not voz.exists() and "voz" not in C.capacidades(C.leer("demo"))
PU.decidir_local(res["puerta"], "cambios", "Faltan sus muletillas")
assert not voz.exists()
res = correr(e["id"])
(E.carpeta("demo", e["id"]) / "perfil-voz.md").write_text("# Perfil de voz\n\nHabla despacio y remata con una pregunta.\n")
PU.decidir_local(res["puerta"], "acepto")
assert "remata con una pregunta" in voz.read_text() and f"encargo `{e['id']}`" in voz.read_text(), voz.read_text()
assert "voz" in C.capacidades(C.leer("demo"))                          # el canal ya tiene voz
assert "[[voz]]" in (C.carpeta("demo") / "wiki/index.md").read_text()
PY
python3 - "$P" <<'PY' && ok "de_salida: copia la sección pedida de una salida, enlazada a su encargo" || bad "de_salida"
import importlib.util, sys
from pathlib import Path
P = Path(sys.argv[1]); sys.path.insert(0, str(P))
def m(n):
    s = importlib.util.spec_from_file_location(n, P / f"{n}.py"); x = importlib.util.module_from_spec(s); sys.modules[n] = x; s.loader.exec_module(x); return x
C, E, WK = m("hyt_canales"), m("hyt_encargos"), m("hyt_wiki")
e = E.listar("demo")[0]
d = E.carpeta("demo", e["id"]); (d / "perfil-voz.md").write_text("# Perfil\n\n## Resumen\nx\n\n## Cómo habla: lo esencial\n- frases cortas\n\n## Métricas\n- otra cosa\n")
WK.de_salida("demo", e["id"], {"pagina": "voz", "de": "perfil-voz.md", "seccion": "Cómo habla"})
v = (C.carpeta("demo") / "wiki/concepts/voz.md").read_text()
assert "frases cortas" in v and "otra cosa" not in v and e["id"] in v, v
WK.de_salida("demo", e["id"], {"pagina": "voz", "de": "no-existe.md"})      # nunca lanza
PY
rm -rf "$W/.git"; sed -i.bak '/## Fixed pages/,$d' "$W/SCHEMA.md"
$H wiki sembrar demo | grep -q "Memoria sembrada: canal, decisiones/correcciones" && grep -q "## Fixed pages" "$W/SCHEMA.md" && [ -d "$W/.git" ] \
  && ok "sembrar: idempotente; repone el git y las páginas fijas del SCHEMA" || bad "sembrar"
$H wiki sembrar no-existe >/dev/null 2>&1 && bad "sembrar un canal que no existe" || ok "sembrar un canal que no existe se rechaza"
exit $fail
