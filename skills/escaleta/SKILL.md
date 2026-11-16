---
name: escaleta
description: "Fija el esqueleto del guion: promesa, tesis de cada bloque, reenganches y material asignado."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Escaleta

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-guionista`). Aquí se decide el vídeo; escribirlo viene
después.

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

Lee además `referencias/retencion.md` y `referencias/ganchos.json`.

## Procedimiento

1. Lee `eleccion.json` (título, miniatura y promesa) y `material.json`. Solo cuentas con ese material.
   Si `material.json` dice `material_justo`, hay menos material que palabras tiene el guion: desarrolla cada pieza
   (el problema que resuelve, la objeción, el ejemplo) en lugar de añadir afirmaciones nuevas, y no repitas una
   pieza para llenar.
2. Calcula el presupuesto: las palabras totales salen de los minutos y del ritmo de lectura de las reglas del canal;
   la intro no pasa de `intro_max_palabras`.
3. Define la **intro**: la promesa (reafirma el título), la promesa extra, la prueba de autoridad (un hecho del
   material o de lo que la guía de voz permite afirmar), el plan y las objeciones del espectador. Elige tres fórmulas
   de `ganchos.json` distintas para las tres versiones de la intro, evitando las que el canal ya ha usado en sus
   últimos guiones (`aperturas-recientes.json`).
4. Define los **bloques**, en este orden y con estos `id`:
   `desarrollo-1`, `reenganche-1`, `conexion`, `reenganche-2`, `desarrollo-2`, `cierre`.
   - Cada bloque tiene una `tesis`: una frase rotunda que lo resume. Si no sale, el bloque no está pensado.
   - Lo más fuerte del material va al principio y al final; lo más flojo, en medio.
   - `desarrollo-1` empieza planteando un problema.
   - `conexion` es un caso real o una experiencia de quien presenta, del material.
   - Cada reenganche tiene su `pregunta_abierta`: qué queda por saber, dicho en concreto.
   - Cada bloque termina tirando del siguiente (`tira_de`).
   - Si el desarrollo es largo, pártelo en `partes` con su propia tesis.
5. Asigna el `material` a cada bloque por su número `n`. Ninguna pieza va en dos bloques. Ningún bloque de
   desarrollo se queda con menos de tres piezas: si pasa, sobra bloque o falta material.
6. Reparte las `palabras` por bloque. Tienen que sumar el total.
7. El **cierre**: no anuncia el final ni vende nada. Lleva al vídeo que indica `destino` en `eleccion.json` (lo eligió una persona, o es
   otro tema del canal ya elegido); nunca prometas cuándo sale. Si está vacío, lleva a los próximos vídeos del
   canal sin nombrar ninguno; di
   en `gancho_idea` qué pregunta abre hacia él.

## Formato de salida (`escaleta.json`)

```json
{"palabras_total": 2100,
 "intro": {"promesa": "…", "promesa_extra": "…", "autoridad": "…", "plan": "…", "objeciones": ["…"],
           "ganchos": ["cifra", "error", "contra"], "palabras": 70},
 "bloques": [{"id": "desarrollo-1", "tesis": "…", "material": [1, 4, 7], "palabras": 450, "tira_de": "…",
              "partes": [{"tesis": "…", "material": [1]}]},
             {"id": "reenganche-1", "pregunta_abierta": "…", "palabras": 40}],
 "cierre": {"destino": "…", "gancho_idea": "…"}}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
