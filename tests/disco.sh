#!/usr/bin/env bash
# Disco: lo primero que se ve en el estado y en el panel, con aviso a partir de un umbral; y desacoplar procesos largos.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HOME="$T/casa"; mkdir -p "$HOME"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }

python3 "$P/hyt_canales.py" alta demo "Canal Demo" "Persona Ejemplo" >/dev/null

python3 - "$P" <<'PY' && ok "disco: línea con % y GB, aviso según umbral; solo mira la carpeta de datos" || bad "disco"
import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_base", Path(sys.argv[1]) / "hyt_base.py")
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
assert B._rutas_disco() == [B.home()]
d = B.disco()
assert len(d) == 1 and 0 <= d[0]["usado_pct"] <= 100, d
assert B.disco_linea().startswith(("💾 Disco: ", "⚠️ Disco: ")) and "GB libres" in B.disco_linea()
os.environ["HYT_AVISO_DISCO"] = "0"; assert B.disco()[0]["aviso"] and B.disco_linea().startswith("⚠️")
os.environ["HYT_AVISO_DISCO"] = "101"; assert not B.disco()[0]["aviso"]
assert B.disco([]) == [] and B.disco_linea([]) == ""
assert len(B.disco([B.home(), B.home() / "aun-no-existe" / "dentro"])) == 1     # una ruta que no existe cuenta por su padre
dos = [{"punto": "/a", "usado_pct": 10, "libres_gb": 4.8, "total_gb": 10, "aviso": False}, {"punto": "/b", "usado_pct": 90, "libres_gb": 1.0, "total_gb": 10, "aviso": True}]
assert B.disco_linea(dos) == "💾 Disco en /a: 10 % usado, 4,8 GB libres · ⚠️ Disco en /b: 90 % usado, 1,0 GB libres"
PY

si "estado empieza por el disco" "python3 $P/hyt_cli.py estado | head -1 | grep -q 'Disco: .* % usado'"
si "el estado de un canal solo enseña el disco si hay aviso" "! HYT_AVISO_DISCO=101 python3 $P/hyt_cli.py estado demo | grep -q Disco && HYT_AVISO_DISCO=0 python3 $P/hyt_cli.py estado demo | head -1 | grep -q '⚠️ Disco'"
mkdir -p "$T/bin" "$T/run"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/systemd-run"; chmod +x "$T/bin/systemd-run"
python3 - "$P" "$T" <<'PY' && ok "desacoplar: con systemd-run, en su propio scope; sin él o con HYT_SIN_SCOPE, tal cual" || bad "desacoplar"
import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_base", Path(sys.argv[1]) / "hyt_base.py")
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
T = sys.argv[2]
os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]; os.environ["XDG_RUNTIME_DIR"] = T + "/run"
c = B.desacoplar(["bash", "x.sh"])
assert c[:6] == ["env", f"XDG_RUNTIME_DIR={T}/run", "systemd-run", "--user", "--scope", "--quiet"] and c[-2:] == ["bash", "x.sh"], c
os.environ["HYT_SIN_SCOPE"] = "1"; assert B.desacoplar(["bash", "x.sh"]) == ["bash", "x.sh"]
PY
python3 - "$P" <<'PY' && ok "base: escritura atómica, registros que solo crecen, slugs y carpeta de datos por HERMES_YT_HOME" || bad "base"
import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hyt_base", Path(sys.argv[1]) / "hyt_base.py")
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
assert B.home() == Path(os.environ["HERMES_YT_HOME"])
del os.environ["HERMES_YT_HOME"]; assert B.home() == Path.home() / ".hermes" / "hermes-youtube"
os.environ["HERMES_YT_HOME"] = sys.argv[1] + "/../../no-se-usa"
f = Path(os.environ["HOME"]) / "a" / "b.json"
B.escribir(f, {"ñ": "sí"}, 0o600); assert B.leer(f) == {"ñ": "sí"} and "sí" in f.read_text() and oct(f.stat().st_mode & 0o777) == "0o600"
assert not list(f.parent.glob("*.tmp")) and B.leer(f.parent / "no.json", 7) == 7
B.anotar(f.parent / "r.jsonl", {"a": 1}); B.anotar(f.parent / "r.jsonl", {"a": 2}); assert (f.parent / "r.jsonl").read_text().count("\n") == 2
for mal in ("Mayus", "a", "con--doble", "-guion", "todo", "cartera", "con espacio", 3):
    try:
        B.validar_slug(mal); raise SystemExit(f"aceptó {mal}")
    except B.Rechazo as x:
        assert "web" not in str(x)
assert B.validar_slug("canal-1") == "canal-1"
PY
exit $fail
