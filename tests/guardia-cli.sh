#!/usr/bin/env bash
# El guardia de la coordinadora: qué puede hacer sola, qué pide aprobación y qué nunca. Y la CLI hyt.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HYT_SIN_PASOS=1 HERMES_YT_HOME="$T/home" HERMES_BIN="$ROOT/tests/dobles/hermes" HYT_EJECUTORES="$ROOT/tests/dobles" HOME="$T/casa"
export FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
H="$ROOT/hyt"; G="$ROOT/guardia/guardia.py"; A="$ROOT"
mkdir -p "$HOME"
$H alta demo "Canal Demo" "Persona Ejemplo" >/dev/null; $H alta otro "Otro Canal" "Otra Persona" >/dev/null
mkdir -p "$HERMES_YT_HOME/wiki"

# t <rc esperado> <evento> <nombre>   · aprueba <evento> <nombre> (rc 0 + {"action":"approve"})
t() { out=$(printf '%s' "$2" | python3 -I "$G" "$A" 2>/dev/null); rc=$?
      if [ "$rc" = "$1" ] && ! echo "$out" | grep -q '"approve"'; then ok "$3"; else bad "$3 (salió $rc: $out)"; fi; }
aprueba() { out=$(printf '%s' "$1" | python3 -I "$G" "$A" 2>/dev/null); rc=$?
      if [ "$rc" = 0 ] && echo "$out" | grep -q '"action": "approve"'; then ok "$2"; else bad "$2 (salió $rc: $out)"; fi; }
c() { jq -nc --arg c "$1" '{tool_name:"terminal",tool_input:{command:$c}}'; }
w() { jq -nc --arg t "$1" --arg p "$2" '{tool_name:$t,tool_input:{path:$p,content:"x"}}'; }
h() { jq -nc --arg t "$1" --argjson i "$2" '{tool_name:$t,tool_input:$i}'; }
CL="$HERMES_YT_HOME/canales"

# ── sola ──
t 0 "$(c 'hyt estado')" "sola: estado de todo"
t 0 "$(c 'hyt estado demo')" "sola: estado de un canal"
t 0 "$(c 'hyt canales')" "sola: canales"
t 0 "$(c 'hyt encargos demo --todos')" "sola: encargos"
t 0 "$(c 'hyt encargo demo guion-x-1a2b')" "sola: un encargo"
t 0 "$(c 'hyt puertas')" "sola: puertas"
t 0 "$(c 'hyt puerta g1234abcd')" "sola: ver una puerta"
t 0 "$(c 'hyt pipelines --canal demo')" "sola: pipelines"
t 0 "$(c 'hyt plan guion demo')" "sola: plan"
t 0 "$(c 'hyt lanzar demo propuesta')" "sola: lanzar una pipeline"
t 0 "$(c 'hyt lanzar demo guion --param tema=x --param pilar=p --brief "Con este enfoque"')" "sola: lanzar con parámetros y brief"
t 0 "$(c "bash $A/hyt encargos demo")" "sola: hyt por su ruta del arnés"
t 0 "$(c 'hyt reintentar demo guion-x-1a2b escribir')" "sola: reintentar"
t 0 "$(c 'hyt vueltas')" "sola: vueltas"
t 0 "$(c 'hyt leccion demo escribir "Regla general de prueba, bien larga" gabcdef12')" "sola: proponer una lección"
t 0 "$(c 'hyt lecciones --todas')" "sola: lecciones"
t 0 "$(c 'hyt wiki sembrar demo')" "sola: sembrar la memoria"
t 0 "$(c 'hyt modelos ver --canal demo')" "sola: ver modelos"
t 0 "$(c 'hyt modelos')" "sola: hyt modelos a secas es ver"
t 0 "$(c 'hyt -h')" "sola: la ayuda"
t 0 "$(c "cat $CL/demo/encargos.jsonl 2>/dev/null | tail -5")" "sola: leer datos del canal"
t 0 "$(c "ls $CL/demo/fuentes && grep -rn promesa $CL/demo/wiki")" "sola: mirar las fuentes y la wiki"
t 0 "$(c "find $CL/demo -name '*.md'")" "sola: find sin acciones"
t 0 "$(c "sed -n 1,20p $CL/demo/canal.json")" "sola: sed -n"
t 0 "$(c 'hyt video lista demo')" "sola: los vídeos del canal"
t 0 "$(c 'hyt video exportar demo guion-x-1a2b guion')" "sola: exportar un vídeo aprobado"
t 0 "$(c 'hyt publicados lista demo')" "sola: los publicados"

# ── con aprobación ──
aprueba "$(c 'hyt video grabado demo guion-x-1a2b')" "aprobación: marcar un vídeo como grabado"
aprueba "$(c 'hyt video publicado demo guion-x-1a2b --url https://ejemplo.com/v')" "aprobación: marcar un vídeo como publicado"
aprueba "$(c 'hyt publicados poner demo --titulo "Un vídeo"')" "aprobación: apuntar un publicado"
aprueba "$(c 'hyt publicados quitar demo v-un-video')" "aprobación: quitar un publicado"
aprueba "$(c 'hyt correo ciclo')" "aprobación: el ciclo del correo"
aprueba "$(c 'hyt correo resumen')" "aprobación: el resumen diario"
aprueba "$(c 'hyt correo prueba demo')" "aprobación: el correo de prueba"
aprueba "$(c 'hyt video')" "aprobación: «hyt video» a secas no es una consulta"
aprueba "$(c 'hyt alta nuevo "Canal Nuevo" "Persona Nueva"')" "aprobación: el alta"
aprueba "$(c 'hyt config demo reglas.titulo_max 60')" "aprobación: config"
aprueba "$(c 'hyt pausar todo')" "aprobación: pausar"
aprueba "$(c 'hyt reanudar demo')" "aprobación: reanudar"
aprueba "$(c 'hyt modelos perfil calidad')" "aprobación: cambiar el perfil de modelos"
aprueba "$(c 'hyt modelos poner escribir sonnet --canal demo')" "aprobación: cambiar el modelo de una etapa"
aprueba "$(c 'hyt lanzar demo guion --param tema=x --param pilar=p --excepcion')" "aprobación: saltarse el tope semanal"
out=$(printf '%s' "$(c 'hyt lanzar demo guion --param tema=x --excepcion')" | python3 -I "$G" "$A")
echo "$out" | jq -e '(.message | test("«guion» para demo")) and (.rule_key | startswith("hermes-youtube:"))' >/dev/null && ok "la aprobación dice qué se pide, con su clave de regla" || bad "mensaje de aprobación ($out)"

# ── nunca ──
t 2 "$(c 'hyt decidir g123 acepto')" "nunca: decidir una puerta (no existe)"
t 2 "$(c 'hyt secreto guardar demo UNA_CLAVE')" "nunca: guardar claves (es de la persona, en su terminal)"
for vieja in publicar preguntar ordenar parte propuesta datos tanda gestion mcp novedad mejora cuaderno ia aterrizaje vigilancia contacto; do
  t 2 "$(c "hyt $vieja demo")" "nunca: «hyt ${vieja}» ya no existe"
done
t 2 "$(c 'hyt')" "nunca: hyt sin orden"
t 2 "$(c "python3 $A/plugin/hermes-youtube/hyt_puertas.py decidir-local g1 acepto")" "nunca: llamar al notario directamente"
t 2 "$(c "python3 $A/plugin/hermes-youtube/hyt_fuentes.py cargar demo /tmp/x")" "nunca: llamar a un módulo del arnés (cualquiera)"
t 2 "$(c "bash $A/etapa.sh demo x y")" "nunca: ejecutar etapas a mano"
t 2 "$(c "cat $CL/demo/secretos.env")" "nunca: leer secretos"
t 2 "$(c "cat $HERMES_YT_HOME/aprobadores.json")" "nunca: leer aprobadores"
t 2 "$(c "cat $HERMES_YT_HOME/yt.json")" "nunca: leer la configuración global"
t 2 "$(c 'cat ~/.hermes/.env')" "nunca: leer el .env de Hermes"
t 2 "$(c 'cat ~/.hermes/config.yaml')" "nunca: leer el resto de Hermes"
t 2 "$(c 'echo x > /tmp/a')" "nunca: redirigir a un fichero"
t 2 "$(c 'cat $(echo x)')" "nunca: sustituciones"
t 2 "$(c 'rm -rf /tmp/a')" "nunca: rm"
t 2 "$(c 'curl -sI https://ejemplo.com/')" "nunca: salir a la red"
t 2 "$(c 'ls /tmp; python3 -c 1')" "nunca: un intérprete, aunque vaya detrás de una lectura"
t 2 "$(c "find $CL -name x -delete")" "nunca: find con acciones"
t 2 "$(c "sed -i s/a/b/ $CL/demo/wiki/index.md")" "nunca: sed que escribe"
t 2 "$(c 'cat "sin cerrar')" "nunca: una orden que no se puede analizar"
t 2 "$(printf 'esto no es JSON')" "nunca: un evento ilegible (falla cerrado)"
for x in execute_code delegate_task cronjob; do t 2 "$(h $x '{}')" "nunca: $x"; done

# ── ficheros ──
t 0 "$(w write_file "$HERMES_YT_HOME/wiki/concepts/x.md")" "escribe en la wiki global"
t 0 "$(w write_file "$CL/demo/wiki/concepts/nota.md")" "escribe en la wiki de un canal"
t 0 "$(w patch "$CL/otro/wiki/index.md")" "y en la de otro: los ve todos"
t 2 "$(w write_file "$CL/demo/canal.json")" "nunca: escribir la configuración a mano"
t 2 "$(w write_file "$CL/demo/fuentes/nueva.txt")" "nunca: escribir en las fuentes"
t 2 "$(w write_file "$CL/demo/inventario.json")" "nunca: escribir el inventario"
t 2 "$(w write_file "$CL/demo/encargos/guion-x-1a2b/guion.md")" "nunca: tocar el resultado de un encargo"
t 2 "$(w write_file "$HERMES_YT_HOME/puertas/g1234abcd.json")" "nunca: escribir una puerta"
t 2 "$(w patch "$CL/demo/wiki/.git/config")" "nunca: tocar el .git de la wiki"
t 2 "$(w write_file "$CL/demo/wiki/../canal.json")" "nunca: salir de la wiki con «..»"
t 0 "$(jq -nc --arg p "$CL/demo/canal.json" '{tool_name:"read_file",tool_input:{path:$p}}')" "lee la configuración de un canal"
t 2 "$(jq -nc --arg p "$CL/demo/secretos.env" '{tool_name:"read_file",tool_input:{path:$p}}')" "nunca: read_file de los secretos"
t 0 "$(h search_files "{\"path\":\"$CL/demo\"}")" "busca en un canal"
t 2 "$(h search_files "{\"path\":\"$CL/demo/secretos.env\"}")" "nunca: buscar en los secretos"
t 0 "$(c "git -C $HERMES_YT_HOME/wiki commit -am x")" "commit en la wiki global"
t 0 "$(c "git -C $CL/demo/wiki log --oneline")" "git en la wiki de un canal"
t 2 "$(c "git -C $HERMES_YT_HOME/wiki push")" "nunca: push de la wiki"
t 2 "$(c "git -C $A commit -am x")" "nunca: commit fuera de las wikis"
t 0 "$(c "git -C $A log --oneline")" "git de lectura en el arnés"
t 0 "$(h clarify '{}')" "otras herramientas (clarify) no pasan por el guardia"

# ── la CLI ──
si() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
no() { if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi; }
si "hyt canales" "$H canales | grep -q 'Canal Demo (demo) · presenta: Persona Ejemplo'"
si "hyt alta crea el canal y siembra su memoria" "[ -f $CL/demo/canal.json ] && [ -f $CL/demo/wiki/concepts/canal.md ]"
no "hyt alta sin presentador" "$H alta tres 'Canal Tres'"
si "hyt pipelines" "[ \$($H pipelines | wc -l) = 5 ] && $H pipelines | grep -q '^guion .*Guion: '"
si "hyt plan dice quién hace cada etapa, con qué modelo, y la puerta" "$H plan guion demo | grep -q '▶ Escribir el guion: {tema} (Claude Code, opus)' && $H plan guion demo | grep -q '(yt-verificador, sonnet)' && $H plan titulo-miniatura demo | grep -q '🚪 elegir-titulo (marketing) → pipeline:guion'"
si "hyt plan enseña la cadena de puertas con sus papeles" "[ \"\$($H plan guion demo | grep '^🚪' | tr '\n' '|')\" = '🚪 revision (marketing)|🚪 datos (datos) · se salta si no hay datos pendientes|🚪 revision-final (presentador)|' ]"
no "hyt lanzar con un --param mal escrito" "$H lanzar demo guion --param tema"
EID=$($H lanzar demo guion --param tema='Qué es X' --param pilar=p --brief 'Con este enfoque' | sed -nE 's/.*\((guion-[a-z0-9-]+)\).*/\1/p')
si "hyt lanzar devuelve el encargo" "[ -n '$EID' ]"
si "el brief de quien lo pide queda en el encargo" "grep -q 'Con este enfoque' $CL/demo/encargos/$EID/brief.md"
si "lanzar lo mismo otra vez no duplica" "$H lanzar demo guion --param tema='Qué es X' --param pilar=p | grep -q 'ya está en marcha'"
si "hyt estado lo enseña con sus etapas" "$H estado demo | grep -q "$EID.*0/$(jq '.etapas | length' $ROOT/pipelines/guion.json) etapas""
si "hyt encargos y hyt encargo" "$H encargos demo | grep -q '^$EID .*en-curso' && $H encargo demo $EID | jq -e '.pipeline == \"guion\"'"
si "reintentar una vez" "$H reintentar demo $EID escribir"
no "reintentar dos veces, no" "$H reintentar demo $EID escribir"
si "pausar y reanudar un canal" "$H pausar demo && $H estado demo | grep -q 'en pausa' && $H canales | grep -q 'en pausa' && $H reanudar demo && ! $H estado demo | grep -q 'en pausa'"
si "pausar y reanudar todo" "$H pausar todo && $H estado | grep -q 'Todo en pausa' && $H reanudar todo && ! $H estado | grep -q 'Todo en pausa'"
si "hyt config cambia y lo deja a nombre de quien lo pide" "HYT_QUIEN=ana $H config demo reglas.rondas_max 4 && tail -1 $CL/demo/config.jsonl | jq -e '.quien == \"ana\" and .despues == 4'"
no "hyt config no deja un valor fuera de rango" "$H config demo reglas.rondas_max 99"
si "hyt modelos: ver, perfil y poner" "$H modelos ver | grep -q 'Escribir el guion .*opus' && $H modelos perfil rapido && $H modelos poner escribir opus --canal demo && $H modelos ver --canal demo | grep -q 'Escribir el guion .*opus .*(canal)'"
G1=$(python3 "$ROOT/plugin/hermes-youtube/hyt_puertas.py" abrir demo "$EID" 2>/dev/null)
si "hyt puertas y hyt puerta" "$H puertas demo | grep -q '$G1 .*abierta .*Guion · Canal Demo' && [ -z \"\$($H puertas otro)\" ] && $H puerta $G1 | grep -q 'tema: Qué es X'"
no "hyt secreto guardar no funciona sin terminal (ni por una tubería)" "echo valor | $H secreto guardar demo UNA_CLAVE"
si "y no deja nada escrito" "! grep -q UNA_CLAVE $CL/demo/secretos.env"
# vídeos y publicados
si "hyt video lista: cada vídeo con su estado" "$H video lista demo | grep -q 'Qué es X.* · .*($EID)'"
no "hyt video exportar: solo un vídeo aprobado" "$H video exportar demo $EID guion"
no "hyt video grabado: solo un vídeo aprobado" "$H video grabado demo $EID"
no "hyt video exportar sin decir la parte" "$H video exportar demo $EID"
si "hyt publicados: poner, lista, editar por id y quitar" "$H publicados poner demo --titulo 'El arroz que no se pasa' --pilar p --url https://ejemplo.com/v/1 --fecha 2026-10-01 | grep -q 'v-el-arroz-que-no-se-pasa' && $H publicados lista demo | grep -q '2026-10-01 El arroz que no se pasa \[p\] · https://ejemplo.com/v/1' && $H publicados poner demo --id v-el-arroz-que-no-se-pasa --titulo 'El arroz que nunca se pasa' && [ \$($H publicados lista demo | wc -l) = 1 ] && $H publicados quitar demo v-el-arroz-que-no-se-pasa && [ -z \"\$($H publicados lista demo)\" ]"
no "hyt publicados quitar uno que no está" "$H publicados quitar demo no-esta"
no "hyt correo ciclo sin configurar el correo lo dice" "HYT_CORREO_URL= HYT_CORREO_CONF=$T/no.env $H correo ciclo"
si "hyt correo prueba sin nadie de marketing con correo lo dice" "HYT_CORREO_CONF=$T/no.env $H correo prueba demo | grep -q 'Nadie con el papel «marketing» tiene correo'"
no "hyt no tiene orden para decidir" "$H decidir x acepto"
no "ni para publicar" "$H publicar demo"
no "ni las órdenes que no se han portado" "$H preguntar demo hola || $H datos resumen demo || $H tanda lista demo || $H parte demo"
si "la ayuda de hyt habla de canales" "$H -h | grep -q canales && ! $H -h | grep -qi 'web'"
exit $fail
