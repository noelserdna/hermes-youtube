---
name: describir
description: "Escribe el resumen de la descripción y los títulos de los capítulos."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Describir

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-guionista`).

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

Lee además `referencias/descripcion.md`.

## Procedimiento

1. Lee `eleccion.json` y `guion.md`. Si existe `descripcion-anterior.json`, es una ronda nueva: **parte de ella** y
   cambia solo lo que haga falta porque el guion ha cambiado y lo que pida `cambios-descripcion.json`:
   - aplica todo lo de `pendientes` (usa `quedaria` si viene);
   - nada de lo que está en `ya_corregido` puede volver, ni tal cual ni con otras palabras: son cosas que una
     persona o el editor jefe ya quitaron.
2. Escribe el `resumen`: de dos a cuatro párrafos cortos, con la voz del canal. Las dos primeras líneas dicen de qué
   va el vídeo y llevan una palabra clave del título. No destripa el vídeo ni repite el guion.
3. Agrupa los bloques del guion en **entre cuatro y seis capítulos**. El primero incluye la intro. Los reenganches
   no son capítulos: van con el bloque que abren. Si un desarrollo es largo, puedes partirlo indicando la frase
   donde empieza la segunda parte.
4. Titula cada capítulo con **lo que se cuenta**, en pocas palabras del contenido. Nunca el nombre del bloque.
5. No pongas minutos: los calcula el sistema con las palabras de cada tramo.

## Formato de salida (`descripcion.json`)

```json
{"resumen": "…\n\n…",
 "capitulos": [{"titulo": "…", "desde": "intro"},
               {"titulo": "…", "desde": "desarrollo-1"},
               {"titulo": "…", "desde": "desarrollo-2", "frase": "…primera frase de esta parte, tal cual…"}]}
```

`desde` es el `id` del bloque donde empieza el capítulo.

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
