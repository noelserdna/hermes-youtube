#!/usr/bin/env bash
# Copia cifrada de los datos de hermes-youtube y de la configuración de Hermes a un bucket R2 de Cloudflare.
#
#   copia.sh            hace la copia, la sube, la vuelve a bajar y comprueba que se descifra y se lee
#   copia.sh preparar   crea la clave de cifrado (si no existe), el bucket y la regla que borra lo de más de N días
#
# Configuración en ~/.config/hermes-youtube/copia.env (600), o en la ruta de HYT_COPIA_CONF:
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID   token con permiso de R2 (edición)
#   HYT_COPIA_BUCKET                             p. ej. hermes-copias
#   HYT_COPIA_DIAS                               días que se guardan (por defecto 30)
# La clave de cifrado está en ~/.config/hermes-youtube/copia.key: guarda otra copia FUERA del servidor (sin ella no se
# puede restaurar). El resultado queda en $HERMES_YT_HOME/copia.json, que se enseña en el estado.
# Restaurar: bajar el objeto y `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:copia.key -in X | tar xz`.
set -euo pipefail
CONF=${HYT_COPIA_CONF:-$HOME/.config/hermes-youtube/copia.env}
CLAVE=${HYT_COPIA_CLAVE:-$HOME/.config/hermes-youtube/copia.key}
HH=${HERMES_HOME:-$HOME/.hermes}
HS=${HERMES_YT_HOME:-$HH/hermes-youtube}
API=${HYT_COPIA_API:-https://api.cloudflare.com/client/v4}
[ -f "$CONF" ] || { echo "Falta $CONF (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, HYT_COPIA_BUCKET)" >&2; exit 2; }
set -a; . "$CONF"; set +a
: "${CLOUDFLARE_API_TOKEN:?}" "${CLOUDFLARE_ACCOUNT_ID:?}" "${HYT_COPIA_BUCKET:?}"
DIAS=${HYT_COPIA_DIAS:-30}
BASE="$API/accounts/$CLOUDFLARE_ACCOUNT_ID/r2/buckets"
cf() { curl -sS --fail-with-body -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$@"; }

if [ "${1:-}" = preparar ]; then
  mkdir -p "$(dirname "$CLAVE")"
  if [ ! -f "$CLAVE" ]; then
    (umask 077; openssl rand -base64 48 > "$CLAVE")
    echo "Clave nueva en $CLAVE: guarda una copia fuera del servidor."
  fi
  if cf "$BASE/$HYT_COPIA_BUCKET" >/dev/null 2>&1; then
    echo "El bucket $HYT_COPIA_BUCKET ya existe."
  else
    cf -X POST -H "Content-Type: application/json" -d "{\"name\":\"$HYT_COPIA_BUCKET\"}" "$BASE" >/dev/null
    echo "Bucket $HYT_COPIA_BUCKET creado."
  fi
  cf -X PUT -H "Content-Type: application/json" "$BASE/$HYT_COPIA_BUCKET/lifecycle" -d "{\"rules\":[{\"id\":\"borrar-$DIAS-dias\",
    \"enabled\":true,\"conditions\":{\"prefix\":\"\"},\"deleteObjectsTransition\":{\"condition\":{\"type\":\"Age\",
    \"maxAge\":$((DIAS * 86400))}}}]}" >/dev/null
  echo "Se guardan $DIAS días."
  exit 0
fi

[ -f "$CLAVE" ] || { echo "Falta la clave $CLAVE: ejecuta «copia.sh preparar»" >&2; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
resultado() {   # ok bytes objeto motivo
  python3 - "$HS/copia.json" "$@" <<'PY'
import json, sys, datetime
f, ok, n, obj, motivo = sys.argv[1:6]
json.dump({"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": ok == "1",
           "bytes": int(n or 0), "objeto": obj, "motivo": motivo}, open(f, "w"), ensure_ascii=False)
PY
}
falla() { resultado 0 0 "" "$1"; echo "COPIA_ERROR $1" >&2; exit 1; }

# Qué se guarda (rutas relativas a $HOME): los datos de los canales (con sus fuentes) y la configuración. El código
# está en GitHub.
cd "$HOME"
{
  find "${HS#$HOME/}" -mindepth 1 -maxdepth 1 ! -name 'actual' ! -regex '.*/[0-9]+\.[0-9]+\.[0-9]+' ! -name 'copia.json'
  for f in config.yaml SOUL.md .env auth.json cron; do [ -e "${HH#$HOME/}/$f" ] && echo "${HH#$HOME/}/$f"; done
  for p in "${HH#$HOME/}"/profiles/*/; do
    for f in config.yaml SOUL.md .env cron scripts; do [ -e "$p$f" ] && echo "$p$f"; done
  done
  for d in .config/*/; do [ "$d" = ".config/hermes-youtube/" ] || { [ -n "$(ls -A "$d" 2>/dev/null | grep -E '\.(env|pem|json|ya?ml)$')" ] && echo "${d%/}"; }; done
} > "$T/lista" 2>/dev/null || true
grep -q . "$T/lista" || falla "no hay nada que copiar"
tar czf "$T/c.tgz" --ignore-failed-read --exclude='*.lock' --exclude='node_modules' --exclude='.git/objects' \
  -T "$T/lista" 2>"$T/tar.err" || { [ -s "$T/c.tgz" ] || falla "tar: $(tail -1 "$T/tar.err")"; }
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$CLAVE" -in "$T/c.tgz" -out "$T/c.enc" \
  || falla "no se pudo cifrar"
OBJ="hermes/$(hostname -s)-$(date -u +%Y%m%d-%H%M%S).tgz.enc"
cf -X PUT -H "Content-Type: application/octet-stream" --data-binary "@$T/c.enc" "$BASE/$HYT_COPIA_BUCKET/objects/$OBJ" \
  >/dev/null 2>"$T/put.err" || falla "no se pudo subir a R2: $(tail -c 200 "$T/put.err")"
# comprobar: se baja, se descifra y se lee
cf -o "$T/v.enc" "$BASE/$HYT_COPIA_BUCKET/objects/$OBJ" 2>/dev/null || falla "subida, pero no se pudo volver a bajar"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$CLAVE" -in "$T/v.enc" | tar tzf - > "$T/v.lista" 2>/dev/null \
  || falla "la copia subida no se descifra o no se lee"
n=$(wc -l < "$T/v.lista"); bytes=$(wc -c < "$T/c.enc")
resultado 1 "$bytes" "$OBJ" ""
echo "COPIA_OK $OBJ · $((bytes / 1024)) KB · $n ficheros comprobados"
