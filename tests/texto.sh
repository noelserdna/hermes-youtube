#!/usr/bin/env bash
# Medidas de texto sin modelo: frases, bloques, expresiones vetadas, título y miniatura como pareja, nota de la
# apertura y reglas de YouTube para los capítulos. Todo con textos inventados.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }
caso() { python3 - "$ROOT/plugin/hermes-youtube" <<PY && ok "$1" || bad "$1"
import sys; sys.path.insert(0, sys.argv[1]); import hyt_texto as T
$2
PY
}
caso "frases: parte por punto, pregunta y salto de línea; no parte en un decimal" '
f = T.frases("El arroz no se pasa por el tiempo. ¿Entonces por qué? Por el agua.\nSon 2,5 partes.")
assert len(f) == 4, f'
caso "medidas: palabras, media, frases cortas y minutos al ritmo dado" '
m = T.medidas("Uno dos tres. Cuatro cinco seis siete ocho nueve diez once doce.", 150)
assert m["palabras"] == 12 and m["frases"] == 2 and m["media"] == 6.0 and m["pct_cortas"] == 50, m
assert T.medidas("palabra " * 300, 150)["minutos"] == 2.0'
caso "las cabeceras y las marcas de cita no cuentan como texto leído" '
g = "## intro\nEl dato es cierto.[4] Sigue.\n\n## cierre\nNos vemos en el siguiente."
assert T.medidas(g)["palabras"] == 10, T.medidas(g)
b = T.bloques(g); assert [x[0] for x in b] == ["intro", "cierre"], b
n = T.numerar(g); assert n[0] == (1, "intro", "El dato es cierto.") and n[-1][0] == 3, n'
caso "buscar: palabra entera, sin tildes ni mayúsculas, y con puntos suspensivos al final" '
assert T.buscar("En Conclusión, sumergete en esto", ["en conclusión", "sumérgete"]) == ["en conclusión", "sumérgete"]
assert T.buscar("En el vertiginoso mundo de la cocina", ["en el vertiginoso mundo de…"])
assert T.buscar("ustedes saben", ["usted"]) == [] and T.buscar("Usted sabe", ["usted"])'
caso "patrones del canal: devuelve el nombre de la regla y lo encontrado; un patrón roto no rompe" '
r = T.patrones("Solo hoy por 997 € con plazas limitadas", [{"patron": r"\d+\s?€", "nombre": "precio"}, "plazas limitadas", "(roto"])
assert r == [("precio", "997 €"), ("plazas limitadas", "plazas limitadas")], r'
caso "lo que no se lee en un teleprompter: emojis, URL, paréntesis y cifras en dígitos" '
assert T.emojis("Vamos 🚀") and not T.emojis("Vamos ya")
assert "(" in T.no_se_lee("Mira (esto) en https://ejemplo.com") and T.cifras_en_digitos("Son 26 millones") == ["26"]
assert T.cifras_en_digitos("Son veintiséis millones") == []'
caso "repeticiones: trigramas con significado y arranques de frase seguidos" '
t = "La regla del agua funciona. " * 5
assert T.repetidos(t)[0][0] == "regla agua funciona"
assert T.arranques_repetidos("Y ahora uno. Y ahora dos. Y ahora tres. Y ahora cuatro.") == ["y ahora"]'
caso "parecido entre títulos sin las palabras propias del canal" '
assert T.similitud("Blockchain para programadores web", "Blockchain en la banca", {"blockchain"}) == 0.0
assert T.similitud("Cómo cocer arroz suelto", "El arroz suelto se cuece así") > 0.3'
caso "cambios entre dos versiones: solo las frases tocadas" '
a = "## intro\nUno dos. Tres cuatro. Cinco seis."
d = "## intro\nUno dos. Tres CAMBIADO. Cinco seis."
c = T.cambios(a, d); assert c["pct"] == 33 and c["nuevas"] == [(2, "Tres CAMBIADO.")] and c["quitadas"] == ["Tres cuatro."], c'
caso "título: largo, cliché y emoji son fallos; se enseña cómo queda cortado en el móvil" '
r = T.titulo("La guía definitiva para cocer arroz sin que se te pase nunca jamás", cliches=["la guía definitiva"], reglas={"titulo_max": 55})
assert {x[0] for x in r["fallos"]} == {"largo", "cliche"} and r["movil"].endswith("…") and len(r["movil"]) <= 41, r
assert T.titulo("Arroz suelto: la regla del agua")["fallos"] == []'
caso "título: palabra clave al principio y que sobreviva al corte del móvil" '
assert ("clave", ) == tuple(x[0] for x in T.titulo("Lo que nadie te ha contado sobre el arroz", claves=["arroz"])["avisos"])
assert T.titulo("Arroz suelto: la regla del agua", claves=["arroz"])["avisos"] == []'
caso "pareja: la miniatura no repite palabras del título ni pasa de cuatro palabras" '
r = T.titulo("Arroz suelto: la regla del agua", miniatura="LA REGLA")
assert r["fallos"][0][0] == "repite", r
assert T.titulo("Arroz suelto: la regla del agua", miniatura="¿POR QUÉ SE PASA?")["fallos"] == []
assert T.titulo("Arroz suelto", miniatura="esto es lo que pasa siempre")["fallos"][0][0] == "miniatura-larga"'
caso "apertura: la nota pesa el punto más débil y propone el arreglo" '
flojo = T.gancho("Hola, bienvenidos a un nuevo vídeo del canal")
fuerte = T.gancho("Pierdes dos horas cada semana por un error que no sabes que cometes, ¿por qué?")
assert fuerte["nota"] > flojo["nota"] + 20, (fuerte, flojo)
assert flojo["debil"] in flojo["partes"] and flojo["arreglo"]
assert T.gancho("")["nota"] == 0'
caso "capítulos: minutos calculados desde las palabras de cada bloque" '
c = T.capitulos_de_bloques([("Intro", 75), ("La regla", 450), ("Los fallos", 600)], 150)
assert c == [(0, "Intro"), (30, "La regla"), (210, "Los fallos")], c
assert T.mmss(210) == "03:30"'
caso "capítulos: las reglas de YouTube (00:00, al menos tres, diez segundos, en orden)" '
d = "Resumen.\n\n00:00 Intro\n00:30 La regla\n03:30 Los fallos\n"
assert T.leer_capitulos(d) == [(0, "Intro"), (30, "La regla"), (210, "Los fallos")]
assert T.capitulos_validos(T.leer_capitulos(d), 800) == []
assert len(T.capitulos_validos([(5, "A"), (9, "B")])) == 3
assert T.capitulos_validos([(0, "A"), (30, "B"), (20, "C")])[0].startswith("los capítulos no van")'
caso "arreglos de lectura: cifras y signos pasan a como se leen; cabeceras y marcas de cita no se tocan" '
g = "## intro\nTiene 2 opciones; la primera es mejor.[3]\nEl 21 % (según la fuente) cuesta 70 €.\n## desarrollo-1\nHay 26.000 nodos, 2,5 millones y 1 vez.[12]"
t, c = T.arreglar_lectura(g)
assert t.splitlines() == ["## intro", "Tiene dos opciones. La primera es mejor.[3]", "El veintiuno por ciento, según la fuente, cuesta setenta euros.",
                          "## desarrollo-1", "Hay veintiséis mil nodos, dos coma cinco millones y una vez.[12]"], t
assert len(c) == 3 and c[0]["antes"].endswith("[3]") and T.no_se_lee(t) == [] and T.cifras_en_digitos(t) == []
assert T.numero_en_letra(2024) == "dos mil veinticuatro" and T.numero_en_letra(21_000_000) == "veintiún millones"
assert T.arreglar_lectura("Visita https://ejemplo.com hoy")[0] == "Visita https://ejemplo.com hoy"     # lo que no tiene lectura única, se queda
assert T.arreglar_lectura(t) == (t, [])'
exit $fail
