#!/usr/bin/env bash
# Pasos de código alrededor de las etapas, sin modelo: lo que se prepara antes y lo que se comprueba después.
# Con un canal inventado de cocina y salidas de agente escritas a mano.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HERMES_YT_HOME="$T/home" HOME="$T/casa" HERMES_BIN="$ROOT/tests/dobles/hermes" FALSO_LLAMADAS="$T/llamadas" FALSO_TABLEROS="$T/tableros"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
P="$ROOT/plugin/hermes-youtube"
python3 "$P/hyt_canales.py" alta cocina "Cocina clara" Marta >/dev/null 2>&1 || python3 "$P/hyt_cli.py" alta cocina "Cocina clara" Marta >/dev/null
O="$T/origen"; mkdir -p "$O"
printf '# V01 - Arroz suelto\n\n[0:00:00]\nEl arroz no se pasa por el tiempo, se pasa por el agua que le pones al principio. Siete de cada diez arroces se pasan por la misma razón y casi nadie mide el agua.\n\n[0:05:00]\nEn un restaurante de cuarenta mesas dejamos de tirar arroz el día que cambiamos una sola cosa en la cocina.\n' > "$O/V01 - Arroz suelto.txt"
printf 'WEBVTT\n\n00:00:00.000 --> 00:00:20.000\nx\n' > "$O/V01 - Arroz suelto.es.vtt"
python3 "$P/hyt_fuentes.py" cargar cocina "$O" --coleccion charlas --tipo guionizado >/dev/null
caso() { python3 - "$P" "$ROOT" "$T" <<PY && ok "$1" || bad "$1"
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); ROOT, T = Path(sys.argv[2]), Path(sys.argv[3])
import hyt_pasos as S, hyt_canales as C, hyt_base as B
d = T / "enc" / "$1"[:12].replace(" ", "-"); d.mkdir(parents=True, exist_ok=True); (d / ".estado").mkdir(exist_ok=True)
def deja(nombre, datos): (d / nombre).write_text(datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False))
def lee(nombre): return json.loads((d / nombre).read_text())
CITA1 = "El arroz no se pasa por el tiempo, se pasa por el agua que le pones al principio"
CITA2 = "En un restaurante de cuarenta mesas dejamos de tirar arroz el día que cambiamos una sola cosa"
$2
PY
}
caso "antes: la fuente del encargo y las pistas del canal quedan en la carpeta" '
S.p_fuente("cocina", d, {"params": {"fuente": "charlas/v01"}})
assert "se pasa por el agua" in (d / "fuente.txt").read_text() and lee("pistas.json")["fuente"] == "charlas/v01"
try: S.p_fuente("cocina", d, {"params": {"fuente": "charlas/nada"}}); raise SystemExit(1)
except B.Rechazo: pass'
caso "tras el inventario: solo entra la pieza cuya cita está tal cual en la fuente" '
deja("piezas.json", {"fuente": "charlas/v01", "piezas": [
  {"tipo": "afirmacion", "pilar": "arroces", "cita": CITA1, "dicho": "El arroz se pasa por el agua.", "palabras": 900},
  {"tipo": "caso", "pilar": "arroces", "cita": CITA2, "dicho": "Un restaurante dejó de tirar arroz.", "palabras": 700},
  {"tipo": "cifra", "pilar": "arroces", "cita": "nueve de cada diez cocineros lo recomiendan sin dudarlo nunca", "dicho": "Inventada.", "palabras": 50}],
  "nombres_vetados": ["Pepa Gil"], "contradicciones": []})
r = S.t_piezas("cocina", d, {"params": {"fuente": "charlas/v01"}})
inv = S.inventario("cocina"); assert [p["id"] for p in inv["piezas"]] == ["p0001", "p0002"], inv
assert inv["piezas"][1]["marca"] == "0:05:00" and "1 descartadas" in r["resumen"]
assert "Pepa Gil" in C.leer("cocina")["nombres_vetados"]
S.t_piezas("cocina", d, {"params": {"fuente": "charlas/v01"}}); assert len(S.inventario("cocina")["piezas"]) == 2   # recargar no duplica'
caso "tras el inventario: si la mayoría de las citas no existe, la etapa falla" '
deja("piezas.json", {"piezas": [{"tipo": "x", "cita": "esto no lo dijo nadie en ninguna parte del vídeo", "dicho": "x"}] * 3})
assert "fallo" in S.t_piezas("cocina", d, {"params": {"fuente": "charlas/v01"}})'
caso "antes de idear: inventario sin citas y banco de ideas ya vistas" '
B.anotar(C.carpeta("cocina") / "temas.jsonl", {"titulo": "Arroz suelto: la regla del agua", "estado": "elegida"})
S.p_inventario("cocina", d, {})
assert "cita" not in lee("inventario.json")["piezas"][0] and lee("banco.json")["ideas"][0]["estado"] == "elegida"'
caso "seleccionar: veta, exige material, respeta el cupo por pilar y avisa de parecidos y pilares cortos" '
C.config("cocina", "pilares", [{"id": "arroces", "nombre": "Arroces", "tipo": "pilar"}, {"id": "guisos", "nombre": "Guisos", "tipo": "pilar"}])
C.config("cocina", "reglas.temas_por_pilar", 1); C.config("cocina", "reglas.material_min", 800); C.config("cocina", "reglas.material_piezas_min", 1)
c = lambda i, t, p, pz: {"id": i, "pilar": p, "titulo": t, "linea": "Qué te llevas", "piezas": pz}
deja("candidatos.json", {"candidatos": [c("c1", "Arroz suelto: la regla del agua", "arroces", ["p0001"]), c("c2", "Por qué tiras arroz cada domingo", "arroces", ["p0001", "p0002"]),
  c("c3", "El truco del caldo", "arroces", ["p0002"]), c("c4", "Sofrito sin prisa", "guisos", [])]})
n = lambda i, v, veto="": {"id": i, "tres_publicos": v, "atemporal": v, "curiosidad": v, "diferente": v, "repetible": v, "veto": veto, "frase": "x"}
deja("puntuacion.json", {"notas": [n("c1", 4), n("c2", 5), n("c3", 5, "se adivina sin verlo"), n("c4", 5)]})
r = S.t_seleccionar("cocina", d, {"id": "e1"}); t = lee("temas.json")
assert [x["id"] for x in t["temas"]] == ["c2"] and t["temas"][0]["nota"] == 25 and t["temas"][0]["origen"] == ["charlas/v01"], t
assert [x["id"] for x in t["suplentes"]] == ["c1"] and t["suplentes"][0]["parecido_a"], t["suplentes"]
motivos = " ".join(x["motivo"] for x in t["descartados"]); assert "veto" in motivos and "material insuficiente" in motivos
assert any("guisos" in a for a in t["avisos"])'
caso "brief: una idea débil para la pipeline antes de gastar un guion" '
deja("brief.json", {"veredicto": "IDEA DEBIL", "motivo": "no hay material", "promesa": "x", "angulos": [{"id": "a1"}]})
assert "idea débil" in S.t_brief("cocina", d, {})["fallo"]
deja("brief.json", {"veredicto": "ADELANTE", "promesa": "x", "angulos": [{"id": "a1"}]}); assert S.t_brief("cocina", d, {}) == {}'
caso "opciones: filtra por código, ordena por las notas y reparte palancas y ángulos" '
C.config("cocina", "reglas.titulos_presentados", 3); C.config("cocina", "titulo_cliches", ["la guía definitiva"])
deja("brief.json", {"promesa": "Sabrás medir el agua", "palabras_clave": ["arroz"], "angulos": [{"id": "a1"}, {"id": "a2"}]})
t = lambda n, x, pal, ang: {"n": n, "texto": x, "palanca": pal, "angulo": ang}
deja("titulos.json", {"titulos": [t(1, "Arroz suelto: la regla del agua", "afirmacion", "a1"), t(2, "Arroz: no es el tiempo, es el agua", "contraste", "a1"),
  t(3, "La guía definitiva del arroz", "afirmacion", "a1"), t(4, "Arroz pasado: el fallo que no ves", "misterio", "a2"),
  t(5, "Arroz: mide esto y no falla", "afirmacion", "a2"), t(6, "Arroz y dinero", "revelacion", "a2")]})
e = lambda n, v, cumple=True: {"n": n, "atencion": v, "interes": v, "curiosidad": v, "espero_ver": "x", "cumple": cumple}
deja("espectador.json", {"veredicto": "APROBADO", "titulos": [e(1, 5), e(2, 3), e(3, 5), e(4, 2), e(5, 4), e(6, 5, False)], "recomendacion": {"titulo": 1, "miniatura": 2}})
deja("miniaturas.json", {"miniaturas": [{"n": 1}, {"n": 2}]})
S.t_opciones("cocina", d, {}); o = lee("opciones.json")
assert [x["original"] for x in o["titulos"]] == [1, 2, 4], [x["original"] for x in o["titulos"]]   # el mejor de cada palanca, no los tres más altos
assert o["titulos"][0]["n"] == 1 and o["titulos"][0]["movil"] and o["recomendacion"] == {"titulo": 1, "miniatura": 2, "titulo_alternativo": None}
m = {x["texto"]: x["motivo"] for x in o["titulos_descartados"]}
assert "fórmula" in m["La guía definitiva del arroz"] and "no promete" in m["Arroz y dinero"] and "nota" in m["Arroz: mide esto y no falla"], m'
caso "elección: número, título propio con avisos, nota para la miniatura y destino" '
deja("opciones.json", {"brief": {"promesa": "Sabrás medir el agua", "palabras_clave": ["arroz"]}, "titulos": [{"n": 1, "texto": "Arroz suelto: la regla del agua"}, {"n": 2, "texto": "Arroz: no es el tiempo"}],
  "miniaturas": [{"n": 1, "texto": "100 ML"}, {"n": 2, "texto": "¿POR QUÉ?"}], "recomendacion": {"titulo": 1, "miniatura": 2}})
S.p_eleccion("cocina", d, {"eleccion": "titulo: 2\nminiatura: 1\nnota: sin cara\ndestino: El sofrito sin prisa"}); el = lee("eleccion.json")
assert el["titulo"] == "Arroz: no es el tiempo" and el["miniatura"]["texto"] == "100 ML" and el["miniatura"]["nota_de_la_persona"] == "sin cara"
assert el["destino"] == "El sofrito sin prisa" and el["promesa"] == "Sabrás medir el agua" and not el["propio"]
(d / "eleccion.json").unlink(); S.p_eleccion("cocina", d, {"eleccion": ""}); assert lee("eleccion.json")["titulo"] == "Arroz suelto: la regla del agua" and lee("eleccion.json")["miniatura"]["n"] == 2
(d / "eleccion.json").unlink(); S.p_eleccion("cocina", d, {"eleccion": "título: La guía definitiva para cocer un arroz suelto como en un restaurante"}); el = lee("eleccion.json")
assert el["propio"] and len(el["avisos"]) >= 2, el'
caso "elección sin opciones previas: el título es el tema del encargo" '
S.p_eleccion("cocina", d, {"params": {"tema": "Arroz suelto en casa"}}); assert lee("eleccion.json")["titulo"] == "Arroz suelto en casa"'
caso "material: se quedan las piezas con cita comprobada; pocas o insuficiente, falla" '
pz = lambda n, cita: {"n": n, "fuente": "charlas/v01", "tipo": "caso", "para": "explicacion", "cita": cita, "dicho": "x"}
deja("material.json", {"veredicto": "SUFICIENTE", "material": [pz(i, CITA1 if i % 2 else CITA2) for i in range(1, 8)] + [pz(9, "esto no está en la fuente por ningún lado, de verdad")]})
r = S.t_material("cocina", d, {}); m = lee("material.json"); assert len(m["material"]) == 7 and m["sin_cita"] == 1 and "1 descartadas" in r["resumen"], r
deja("material.json", {"veredicto": "SUFICIENTE", "material": [pz(1, CITA1)]}); assert "no da para un guion" in S.t_material("cocina", d, {})["fallo"]
deja("material.json", {"veredicto": "MATERIAL INSUFICIENTE", "propuesta": "fusionar con el del sofrito", "material": [pz(i, CITA1) for i in range(1, 8)]})
assert "fusionar" in S.t_material("cocina", d, {})["fallo"]'
GUION='## intro\nEl arroz no se pasa por el tiempo. Se pasa por el agua.\n## desarrollo-1\nPrimero mides el agua.[1] Después esperas.\nSiete de cada diez se pasan.[2]\n## reenganche-1\nY ahora el fallo.\n## conexion\nEn un restaurante dejamos de tirar arroz.[2]\n## reenganche-2\nQueda el reposo.\n## desarrollo-2\nEl reposo cierra el grano. Diez minutos tapado. Y no levantes la tapa antes de tiempo.\n## cierre\nEso es el agua.\nLa otra mitad es el fuego.\n'
caso "datos: la lista a verificar sale de la verificación y conserva lo ya decidido" '
deja("verificacion.json", {"veredicto": "CAMBIOS", "cambios": [{"bloque": "intro", "frase": "x", "motivo": "y", "quedaria": "z"}], "datos": [{"dato": "siete de cada diez", "frase": "Siete de cada diez se pasan.", "motivo": "contradiccion", "versiones": ["siete", "ocho"]}]})
S.t_datos("cocina", d, {}); x = lee("datos.json")["datos"]; assert x[0]["id"] == "d1" and x[0]["estado"] == "pendiente"
x[0].update(estado="corregido", valor="ocho de cada diez"); deja("datos.json", {"datos": x}); S.t_datos("cocina", d, {})
assert lee("datos.json")["datos"][0]["estado"] == "corregido"'
caso "ajustes: los críticos solo la primera vez; después, lo de la revisión, los datos y la persona, sin repetir" "
deja('guion.md', '''$GUION''')
deja('verificacion.json', {'cambios': [{'bloque': 'intro', 'frase': 'Se pasa por el agua.', 'motivo': 'alcance', 'quedaria': 'Casi siempre, por el agua.'}]})
deja('voz.json', {'cambios': [{'bloque': 'cierre', 'frase': 'Eso es el agua.', 'motivo': 'redonda', 'quedaria': 'Eso es el agua, punto.'}]})
r = S.p_ajustes('cocina', d, {}); a = lee('ajustes.json')['ajustes']
assert r == {} and [x['origen'] for x in a][:2] == ['verificacion', 'voz'] and any(x['origen'] == 'revision' for x in a), a
deja('datos.json', {'datos': [{'id': 'd1', 'dato': 'siete de cada diez', 'frase': 'Siete de cada diez se pasan.', 'estado': 'corregido', 'valor': 'ocho de cada diez'}]})
(d / '.estado' / 'feedback-ajustar.txt').write_text('frase 2: yo diría otra cosa')
S.p_ajustes('cocina', d, {}); o = [x['origen'] for x in lee('ajustes.json')['ajustes']]
assert 'datos' in o and 'persona' in o and 'voz' not in o and 'verificacion' not in o, o
S.p_ajustes('cocina', d, {}); o = [x['origen'] for x in lee('ajustes.json')['ajustes']]; assert 'datos' not in o and 'persona' not in o, o
assert (d / '.estado' / 'guion-antes-1.md').exists()"
caso "ajustes: sin nada que cambiar, la etapa se salta" "
C.config('cocina', 'reglas.minutos', [1, 2]); C.config('cocina', 'reglas.ppm', 60)
deja('guion.md', '''$GUION''')
deja('material.json', {'material': [{'n': 1}, {'n': 2}]})
assert S.p_ajustes('cocina', d, {}) == {'saltar': 'no hay nada que ajustar'}, lee('ajustes.json')"
caso "descripción: los minutos de cada capítulo se calculan con las palabras del guion" "
deja('guion.md', '''$GUION''')
deja('descripcion.json', {'resumen': 'El arroz se pasa por el agua.', 'capitulos': [{'titulo': 'La regla del agua', 'desde': 'intro'}, {'titulo': 'El fallo', 'desde': 'reenganche-1'}, {'titulo': 'El reposo', 'desde': 'desarrollo-2', 'frase': 'Diez minutos tapado.'}]})
C.config('cocina', 'descripcion_pie', 'Cocina clara, cada semana.')
S.t_descripcion('cocina', d, {}); t = (d / 'descripcion.md').read_text().splitlines()
assert t[0] == 'El arroz se pasa por el agua.' and t[2].startswith('00:00 La regla') and t[-1] == 'Cocina clara, cada semana.', t
import hyt_texto as X; c = X.leer_capitulos((d / 'descripcion.md').read_text()); assert c[1][0] == 25 and c[2][0] == 44, c"
caso "paquete: guion limpio para el teleprompter, guion numerado y la nota de la revisión" "
deja('guion.md', '''$GUION''')
deja('eleccion.json', {'titulo': 'Arroz suelto: la regla del agua', 'miniatura': {'texto': '100 ML'}, 'promesa': 'x', 'palabras_clave': ['arroz']})
deja('descripcion.md', 'El arroz y su agua.\n\n00:00 La regla\n00:24 El fallo\n00:43 El reposo\n')
deja('cierre.json', {'veredicto': 'APROBADO', 'notas': ['ojo al reposo']})
deja('datos.json', {'datos': [{'id': 'd1', 'dato': 'x', 'estado': 'pendiente'}]}); deja('material.json', {'material': [{'n': 1}, {'n': 2}]})
S.t_paquete('cocina', d, {}); p = lee('paquete.json'); limpio = (d / 'guion-limpio.txt').read_text()
assert '[1]' not in limpio and '##' not in limpio and limpio.splitlines()[0] == 'El arroz no se pasa por el tiempo.', limpio[:80]
assert (d / 'guion-numerado.md').read_text().startswith('## intro\n\n1. El arroz no se pasa por el tiempo.')
assert p['guion']['palabras'] == 65 and p['revision']['graves'] == 0 and p['editor']['notas'] == ['ojo al reposo'], p['revision']
assert any(a['codigo'] == 'datos-pendientes' for a in p['revision']['avisos'])"
exit $fail
