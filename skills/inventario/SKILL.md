---
name: inventario
description: "Extrae de una fuente del canal las piezas aprovechables para vídeos, con su cita literal."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Inventario de una fuente

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-analista`).

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

1. Lee `fuente.txt`, entera, tramo a tramo: es la fuente de este encargo. `pistas.json` trae las palabras que el
   reconocimiento suele confundir en este canal. Es una transcripción
   automática: tiene palabras mal reconocidas, titubeos y repeticiones, y no dice quién habla.
2. Por cada tramo decide:
   - **Quién habla.** Solo cuenta como voz de quien presenta lo que dice esa persona. Lo de alumnos, invitados o
     compañeros se marca con su papel, sin nombre.
   - **Si es contenido o es otra cosa.** Venta, logística del evento, testimonios con datos personales y repeticiones
     de otro tramo no dan piezas.
3. Extrae **piezas**. Una pieza es una unidad que puede sostener parte de un vídeo:
   `afirmacion` (una frase rotunda), `creencia` (algo que la gente cree y que se rebate), `caso` (un ejemplo real),
   `analogia`, `pregunta` (una duda real de la audiencia), `demo` (algo que se enseña), `cifra`, `experiencia` (algo
   que quien presenta cuenta de sí mismo).
4. Para cada pieza escribe:
   - `cita`: de 12 a 40 palabras copiadas **tal cual** de la transcripción, errores incluidos. Es la prueba de que la
     pieza existe: un programa comprobará que aparece literalmente en la fuente, y la pieza se descarta si no.
   - `dicho`: lo mismo en limpio, corrigiendo el reconocimiento con el contexto y las pistas.
     Una pista no es una sustitución ciega: «staff» puede ser «stack» o puede ser «staff».
   - `pilar`: el pilar del canal al que sirve, o `ninguno`.
   - `palabras`: cuántas palabras de material útil hay alrededor de la pieza (lo que se podría contar con ella).
5. Apunta aparte:
   - `nombres_vetados`: nombres de personas y de empresas que aparecen en testimonios o casos de alumnos.
   - `contradicciones`: cifras que no coinciden dentro de la fuente o con lo que ya dice el inventario del canal.
   - `correcciones`: palabras mal transcritas que has resuelto y que no estaban en las pistas.

## Formato de salida (`piezas.json`)

```json
{"fuente": "<colección>/<id>",
 "piezas": [{"tipo": "afirmacion", "pilar": "<id de pilar>", "marca": "0:12:40", "habla": "presentador",
             "cita": "…literal…", "dicho": "…en limpio…", "palabras": 180}],
 "nombres_vetados": ["…"],
 "contradicciones": [{"dato": "…", "versiones": ["…", "…"], "marcas": ["0:10:00", "1:02:00"]}],
 "correcciones": {"mal": "bien"},
 "descartado": [{"marca": "1:15:00", "motivo": "venta"}]}
```

No hay tope de piezas: una hora de directo suele dar entre veinte y sesenta. Si un tramo no da ninguna, no la fuerces.

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
