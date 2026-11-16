#!/usr/bin/env bash
# Reglas de la revisión mecánica, sin modelo: una prueba por regla, con un canal inventado de cocina. Son los
# criterios «automáticos» de un paquete: lo que no puede llegar a una persona.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
caso() { python3 - "$ROOT/plugin/hermes-youtube" <<PY && ok "$1" || bad "$1"
import sys; sys.path.insert(0, sys.argv[1]); import hyt_reglas as R, hyt_texto as T
CFG = {"pilares": [{"id": "arroces"}, {"id": "guisos"}],
       "reglas": {"ppm": 150, "minutos": [1, 2], "intro_max_palabras": 30, "temas_por_pilar": 2, "titulos_presentados": 3,
                  "miniaturas": 2, "muletilla_max": 2, "muletillas_total": [1, 6], "gancho_min": 0, "frase_media": [3, 30]},
       "prohibidas": ["en conclusión", "sumérgete"], "cierres_prohibidos": ["en resumen", "gracias por ver"],
       "titulo_cliches": ["la guía definitiva"], "muletillas": ["¿vale?"],
       "excluido": [{"nombre": "precio", "patron": r"\d+\s?(€|euros)", "grave": True}, {"nombre": "oferta", "patron": r"\boferta\b"}],
       "sin_promesas": [{"nombre": "dinero", "patron": r"gana(r)? dinero"}, {"nombre": "empleo", "patron": r"consigue trabajo"}],
       "nombres_vetados": ["Marta Ruiz"], "permite": {}}
def cod(avisos, grave=None): return sorted({a["codigo"] for a in avisos if grave is None or a["grave"] == grave})
def relleno(n): return " ".join("El grano se abre despacio y suelta su almidón, ¿vale?" if i % 40 == 0 else "El agua manda sobre el tiempo en cualquier cazuela." for i in range(n))
def guion(intro="El arroz no se pasa por el tiempo. Se pasa por el agua.", cierre="Eso es el agua.\nLa otra mitad es el fuego.\nY el fuego tiene su propia regla.", d1=None):
    return ("## intro\n" + intro + "\n## desarrollo-1\n" + (d1 or relleno(8)) + "\n## reenganche-1\nY ahora viene el fallo que casi todos cometen.\n"
            "## conexion\n" + relleno(4) + "\n## reenganche-2\nQueda lo que nadie mira: el reposo.\n## desarrollo-2\n" + relleno(8) + "\n## cierre\n" + cierre + "\n")
$2
PY
}
caso "un guion correcto no tiene avisos graves" '
a = R.guion(guion(), CFG, material={1, 2}); assert cod(a, True) == [], [x for x in a if x["grave"]]
assert R.nota(a) >= 80'
caso "duración: fuera del rango de palabras del canal es grave" '
assert "duracion" in cod(R.guion(guion(d1=relleno(60)), CFG), True)
assert "duracion" in cod(R.guion(guion(d1="Corto."), {**CFG, "reglas": {**CFG["reglas"], "minutos": [13, 15]}}), True)'
caso "intro: más palabras que el máximo del canal es grave" '
assert "intro-larga" in cod(R.guion(guion(intro=relleno(5)), CFG), True)'
caso "bloques: los que faltan, los que sobran y el orden" '
g = guion().replace("## conexion", "## relleno")
c = cod(R.guion(g, CFG), True); assert "bloque-falta" in c and "bloque-sobra" in c, c
h = guion().replace("## reenganche-1", "## X").replace("## conexion", "## reenganche-1").replace("## X", "## conexion")
assert "bloque-orden" in cod(R.guion(h, CFG), True)'
caso "expresiones vetadas, sin distinguir tildes ni mayúsculas" '
assert "vetada" in cod(R.guion(guion(d1=relleno(8) + " En Conclusion, mide el agua."), CFG), True)'
caso "el cierre no anuncia el final ni pide nada" '
assert "cierre-anuncia" in cod(R.guion(guion(cierre="En resumen, mide el agua.\nGracias por ver."), CFG), True)'
caso "lo que no se lee en voz alta y las cifras en dígitos" '
c = cod(R.guion(guion(d1=relleno(8) + " Usa 2 partes (más o menos) y mira https://ejemplo.com."), CFG), True)
assert "no-se-lee" in c and "cifra-digitos" in c, c'
caso "trazabilidad: una marca que no existe en el material y una cifra sin marca" '
g = guion(d1=relleno(8) + "\nSe tiran tres millones de kilos al año.\nY mil restaurantes lo saben.[9]")
c = cod(R.guion(g, CFG, material={1, 2}), True); assert "marca-inexistente" in c and "cifra-sin-marca" in c, c
bien = guion(d1=relleno(8) + "\nSe tiran tres millones de kilos al año.[1]")
assert not {"marca-inexistente", "cifra-sin-marca"} & set(cod(R.guion(bien, CFG, material={1, 2}), True))'
caso "frases: una demasiado larga es grave" '
larga = " ".join(["palabra"] * 40) + "."
assert "frase-larga" in cod(R.guion(guion(d1=relleno(6) + " " + larga), CFG), True)'
caso "avisos que no bloquean: muletilla repetida, presupuesto de bloque y apertura parecida a otra" '
g = guion(d1=relleno(8) + " ¿Vale? ¿Vale? ¿Vale?")
a = R.guion(g, CFG, escaleta={"bloques": [{"id": "conexion", "palabras": 400}]}, recientes=["El arroz no se pasa por el tiempo, sino por el agua"])
c = cod(a, False); assert {"muletilla", "presupuesto", "apertura-repetida"} <= set(c), c
assert not {"muletilla", "presupuesto", "apertura-repetida"} & set(cod(a, True))'
caso "contenido excluido, nombres vetados, promesas y emojis valen para todo el paquete" '
c = cod(R.comunes("Solo 997 € y gana dinero. Lo dijo Marta Ruiz 🚀", CFG), True)
assert c == ["emoji", "excluido", "nombre-vetado", "promesa"], c
a = R.comunes("Hay una oferta", CFG); assert a[0]["codigo"] == "excluido"
assert R.comunes("consigue trabajo", {**CFG, "permite": {"promesas_empleo": True}}) == []
assert "excluido" in cod(R.guion(guion(d1=relleno(8) + " Cuesta 20 euros."), CFG), True)'
caso "temas: campos completos, cupo por pilar y aviso de pilar corto" '
t = lambda p, n: {"pilar": p, "titulo": f"Tema {n}", "resumen": "Qué se lleva", "origen": "charlas/v01"}
a = R.temas([t("arroces", 1), t("arroces", 2), t("arroces", 3), t("guisos", 4)], CFG)
assert "pilar-lleno" in cod(a, True) and "pilar-corto" in cod(a, False), cod(a)
assert "tema-incompleto" in cod(R.temas([{"pilar": "arroces", "titulo": "Sin resumen"}], CFG), True)
assert "pilar-desconocido" in cod(R.temas([t("postres", 1)], CFG), True)'
caso "títulos: número, largo, cliché y variedad de palancas" '
T3 = [{"texto": "Arroz suelto: la regla del agua", "palanca": "afirmacion"}, {"texto": "Por qué se te pasa el arroz", "palanca": "misterio"},
      {"texto": "Arroz: no es el tiempo, es el agua", "palanca": "contraste"}]
assert cod(R.titulos(T3, CFG, ["arroz"]), True) == []
malos = [{"texto": "La guía definitiva del arroz", "palanca": "afirmacion"}, {"texto": "x" * 60, "palanca": "afirmacion"}]
c = cod(R.titulos(malos, CFG), True); assert {"titulos-numero", "titulo-cliche", "titulo-largo", "titulos-palancas"} <= set(c), c'
caso "miniaturas: completas, texto breve, sin repetir el título y distintas entre sí" '
T3 = [{"texto": "Arroz suelto: la regla del agua"}]
m = lambda n, concepto, tipo, expr, texto: {"n": n, "angulo": f"a{n}", "concepto": concepto, "que_se_ve": "una cazuela", "composicion": {"tipo": tipo},
     "presentador": {"expresion": expr}, "texto": texto, "reparto": "x", "no_revela": "x", "legible_en_movil": "x", "hipotesis": "x"}
assert cod(R.miniaturas([m(1, "dilema", "cara-derecha", "duda", "¿POR QUÉ?"), m(2, "objeto", "plano-cenital", "sorpresa", "100 ML")], CFG, T3), True) == []
c = cod(R.miniaturas([m(1, "dilema", "cara-derecha", "duda", "LA REGLA"), m(2, "dilema", "cara-derecha", "duda", "esto es lo que pasa siempre")], CFG, T3), True)
assert {"miniatura-repite", "miniatura-larga", "miniaturas-iguales"} <= set(c), c
assert "miniatura-incompleta" in cod(R.miniaturas([{"n": 1}], CFG), True)'
caso "descripción: resumen, capítulos válidos para YouTube y con título de contenido" '
bien = "El arroz se pasa por el agua, no por el tiempo.\n\n00:00 La regla del agua\n00:40 El fallo más común\n03:10 El reposo\n"
assert cod(R.descripcion(bien, CFG, ["arroz"], 400), True) == []
c = cod(R.descripcion("00:05 Intro\n00:09 Desarrollo 1\n", CFG), True)
assert {"sin-resumen", "capitulos", "capitulo-generico"} <= set(c), c
assert "descripcion-clave" in cod(R.descripcion(bien, CFG, ["sofrito"], 400), False)'
caso "la nota baja mucho más con un grave que con un aviso" '
assert R.nota([]) == 100 and R.nota([R.aviso(True, "x", "x")]) == 86 and R.nota([R.aviso(False, "x", "x")]) == 96'
exit $fail
