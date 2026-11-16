#!/usr/bin/env bash
# Todas las pruebas de hermes-youtube, sin LLM ni red. Úsalo antes de dar por buena cualquier actualización de Hermes,
# de Claude Code o del propio plugin: cada incidente real acaba aquí como un caso.
# Cada prueba es un tests/*.sh que imprime «ok   …» por caso y «FAIL …» si algo falla (y sale con 1).
cd "$(dirname "$0")/.."
fail=0; n=0
for t in tests/*.sh; do
  [ "$t" = tests/todo.sh ] && continue
  n=$((n + 1))
  printf '%-30s ' "$t"
  if out=$(bash "$t" 2>&1); then echo "ok ($(echo "$out" | grep -c '^ok') casos)"
  else echo FALLA; echo "$out" | grep -E 'FAIL|Error|Traceback' | head -5; fail=1; fi
done
[ "$n" -gt 0 ] || echo "(aún no hay pruebas)"
exit $fail
