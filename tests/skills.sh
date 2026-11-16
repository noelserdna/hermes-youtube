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
# agnóstico: el nombre de un canal o de una persona reales no puede aparecer en lo que viaja con el plugin
REALES='codecrypto|claudio|jorge'
if grep -rIilE "$REALES" "$ROOT/skills" "$ROOT/perfiles" "$ROOT/pipelines" "$ROOT/plantillas" "$ROOT/plugin" --exclude-dir=__pycache__; then
  bad "aparece el nombre de un canal o de una persona reales"
else ok "skills, cartas, pipelines, plantillas y código sin nombres de canales ni personas reales"; fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/skills/x"; echo "Como dice Jorge en CodeCrypto" > "$T/skills/x/SKILL.md"
grep -rIilE "$REALES" "$T/skills" >/dev/null && ok "la comprobación detecta un nombre real (sin distinguir mayúsculas)" || bad "la comprobación de nombres no detecta nada"
exit $fail
