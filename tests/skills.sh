#!/usr/bin/env bash
# Cada skill que usa una pipeline existe, con su frontmatter; las cartas de los perfiles existen; y nada de lo que
# viaja con el plugin (skills, cartas, pipelines, plantillas, código) nombra un canal o una persona reales.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
for s in $(jq -r '.etapas[].skill' "$ROOT"/pipelines/*.json | sort -u); do
  f="$ROOT/skills/$s/SKILL.md"
  if [ -f "$f" ] && [ "$(head -1 "$f")" = "---" ] && grep -q "^name: $s$" "$f" && grep -q '^description: "..*"$' "$f" && grep -q '^version: [0-9]' "$f" \
     && grep -q '^    tags: \[YouTube, hermes-youtube\]$' "$f" && grep -q '^    category: hermes-youtube$' "$f"; then ok "skill $s"; else bad "falta o está mal la skill $s"; fi
done
for p in $(jq -r '.etapas[].perfil' "$ROOT"/pipelines/*.json | sort -u) yt-estacion comun coordinadora; do
  [ -s "$ROOT/perfiles/$p.md" ] && ok "carta $p" || bad "falta la carta $p"
done
for s in "$ROOT"/skills/*/SKILL.md; do
  n=$(basename "$(dirname "$s")")
  jq -r '.etapas[].skill' "$ROOT"/pipelines/*.json | grep -qx "$n" || bad "skill $n sin pipeline que la use"
done
for c in "$ROOT"/perfiles/yt-*.md; do
  n=$(basename "$c" .md)
  [ "$n" = yt-estacion ] || python3 -c "import sys; sys.path.insert(0, '$ROOT/plugin/hermes-youtube'); import hyt_pipelines as m; sys.exit(0 if '$n' in m.PERFILES_ROL else 1)" \
    || bad "la carta $n no es de ningún perfil de rol"
done
python3 -c "import sys; sys.path.insert(0, '$ROOT/plugin/hermes-youtube'); import hyt_pipelines as m, os; sys.exit(0 if all(os.path.getsize('$ROOT/perfiles/' + p + '.md') for p in m.PERFILES_ROL) else 1)" \
  && ok "todos los perfiles de rol tienen carta" || bad "hay perfiles de rol sin carta"
# agnóstico: el nombre de un canal o de una persona reales no puede aparecer en lo que viaja con el plugin. Los nombres
# a vigilar son privados: uno por línea en privado/nombres-reales.txt (fuera de git). Sin ese fichero no hay qué buscar.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
buscar() { grep -rIilE "$1" "${@:2}" --exclude-dir=__pycache__; }
LISTA="$ROOT/privado/nombres-reales.txt"
if [ -s "$LISTA" ]; then
  REALES=$(grep -v '^\s*$' "$LISTA" | paste -sd'|' -)
  if buscar "$REALES" "$ROOT/skills" "$ROOT/perfiles" "$ROOT/pipelines" "$ROOT/plantillas" "$ROOT/plugin" "$ROOT/referencias" "$ROOT/tests" "$ROOT/docs" "$ROOT/README.md"; then
    bad "aparece el nombre de un canal o de una persona reales"
  else ok "nada de lo que viaja con el plugin nombra un canal ni a una persona reales"; fi
else ok "sin lista privada de nombres reales: nada que buscar"; fi
mkdir -p "$T/skills/x"; echo "Como dice Marta en Cocina Clara" > "$T/skills/x/SKILL.md"
buscar 'cocina clara|marta' "$T/skills" >/dev/null && ok "la comprobación detecta un nombre (sin distinguir mayúsculas)" || bad "la comprobación de nombres no detecta nada"
exit $fail
