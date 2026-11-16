---
name: documentar
description: "Reúne el material de un tema, con su cita literal, y dice si da para un vídeo."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Documentar

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-investigador`). Eres el filtro: el guionista solo verá
lo que tú dejes pasar.

## Antes de empezar (siempre)

- Estás en la carpeta del encargo. Lee `brief.md` (qué se pidió), `contexto-canal.md` (el canal: quién presenta, pilares,
  reglas, listas de lo vetado y lo excluido, y las rutas de sus fuentes, su inventario, su wiki y las referencias de
  oficio) y las salidas de las etapas anteriores que te indique el encargo.
- Las reglas y las listas de `contexto-canal.md` mandan sobre cualquier costumbre tuya. Si una regla del canal choca
  con esta skill, gana el canal.
- Solo existe lo que está en las fuentes del canal. No añadas cifras, casos, nombres ni anécdotas de tu cosecha.
- Lo que el canal marca como excluido no aparece en nada de lo que escribas, ni citado ni parafraseado.
- Escribe tu resultado en el fichero que te pide el encargo, en el idioma del canal y con el formato exacto que se
  indica abajo: lo lee un programa. Nada de publicar, escribir a nadie ni tocar la configuración.

## Procedimiento

1. Lee `eleccion.json` (el título y la miniatura elegidos, y la promesa) y `brief.json`. El material sirve a esa
   promesa; lo demás, aunque sea bueno, no entra.
2. Parte de las piezas del inventario que respaldan el tema y **vuelve a la fuente** (`fuentes/<colección>/<id>.txt`, dentro del encargo)
   para leer lo que hay alrededor de cada una. Busca además en el resto del inventario lo que sirva a la promesa.
3. Filtra **frase a frase**:
   - fuera todo lo que el canal excluye, aunque esté en mitad de una explicación;
   - fuera lo que dicen otras personas, salvo que el canal permita usarlo; nunca como voz de quien presenta;
   - los casos de personas se cuentan sin nombre, empresa ni ningún dato personal;
   - de la vida de quien presenta, solo lo que la guía de voz del canal permite afirmar.
4. Escribe cada pieza de material con:
   - `cita`: de 12 a 40 palabras copiadas **tal cual** de la fuente. Un programa comprobará que aparece literalmente;
   - `dicho`: lo mismo en limpio;
   - `para`: para qué sirve en el guion (`gancho`, `problema`, `explicacion`, `analogia`, `caso`, `conexion`,
     `dato`, `objecion`).
5. Las cifras y los datos que se contradicen entre fuentes van a `dudosos`, con todas sus versiones. No elijas tú.
6. Cuenta las `palabras_utiles`: las palabras de material limpio que se pueden contar sin repetirse. Cuenta con
   honradez; no redondees hacia arriba. Si el material da para un vídeo lo decide después un programa con esa cifra
   y las reglas del canal.
7. `veredicto`: `SUFICIENTE` si crees que hay vídeo; `MATERIAL INSUFICIENTE` si no. En los dos casos, cuando el
   material vaya justo, escribe una `propuesta` concreta: con qué otro tema se podría fusionar (di cuál), o qué
   habría que pedirle a quien presenta para completarlo (qué preguntas debería responder). Es preferible no escribir
   un guion a rellenarlo o inventar.

## Formato de salida (`material.json`)

```json
{"veredicto": "SUFICIENTE", "propuesta": "", "palabras_utiles": 2600,
 "material": [{"n": 1, "fuente": "<colección>/<id>", "marca": "0:12:40", "tipo": "analogia", "para": "explicacion",
               "cita": "…literal…", "dicho": "…en limpio…"}],
 "dudosos": [{"dato": "…", "versiones": [{"valor": "…", "fuente": "<colección>/<id>", "marca": "…"}]}]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
