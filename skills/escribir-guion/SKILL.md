---
name: escribir-guion
description: "Escribe el guion palabra por palabra, por bloques y con la voz de quien presenta."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Escribir el guion

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-guionista`). El guion se lee en voz alta en un
teleprompter: si quien presenta tropieza o piensa «esto no lo diría yo», no sirve.

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

Lee además `referencias/retencion.md`, la guía de voz del canal (`voz-canal.md`) y **los ejemplos completos** de la
carpeta `ejemplos/`: son fuentes donde esa persona habla tal cual. Léelos enteros antes de escribir una palabra. Imita cómo
construye las frases, no solo su vocabulario.

## Procedimiento

1. Lee `escaleta.json` y `material.json`. La escaleta manda: no cambies el orden ni añadas bloques.
2. Si en el encargo hay comentarios de una persona sobre una versión anterior, **aplícalos todos y no toques nada
   más**. Un comentario puede señalar una frase por su número. Parte de `guion.md` tal como está y cambia solo lo
   pedido.
3. Escribe **bloque a bloque**, no de un tirón:
   - **Intro**: escribe las tres versiones (una por fórmula de la escaleta) en `intros.md`. Pon en el guion la que
     mejor reafirme el título en su primera frase. La promesa extra llega dentro de las primeras
     `promesa_extra_palabras` palabras. No revela la respuesta. No saluda ni presenta el canal.
   - **Desarrollo**: cada parte empieza por su problema y acaba con su tesis dicha con rotundidad.
   - **Reenganches**: breves; dicen qué viene, en concreto.
   - **Conexión**: el caso o la experiencia, contado como lo contaría esa persona.
   - **Cierre**: de dos a seis líneas que llevan al vídeo de destino. Sin despedidas, sin resumen, sin vender nada.
4. Después, una pasada de **costuras**: lee el guion entero y arregla solo las uniones entre bloques.
5. Reglas de escritura para leer en voz alta:
   - frases cortas; la idea clave se repite con otras palabras, no con las mismas;
   - de tú, y con el tratamiento que marque la guía de voz;
   - las cifras se escriben como se leen («veintiséis millones»); las siglas, como se pronuncian la primera vez;
   - nada de paréntesis, punto y coma, URL, símbolos ni emojis;
   - nada de «como veis aquí» o «esta diapositiva»: no hay pantalla que mirar;
   - las muletillas de esa persona, con medida: ni ausentes ni en cada frase;
   - ninguna expresión de las listas vetadas del canal.
6. **Cada dato lleva su marca.** Después de la frase que usa una pieza del material pon `[n]`, con su número. Una
   cifra, un nombre propio o un caso sin marca es un dato inventado. Si necesitas algo que no está en el material,
   no lo escribas.
7. Respeta el presupuesto de palabras de cada bloque. Si te faltan palabras, no rellenes: avisa en tu resumen.

## Formato de salida (`guion.md`)

Solo el texto que se lee, bajo estas cabeceras exactas y en este orden:

```
## intro
…
## desarrollo-1
…
## reenganche-1
…
## conexion
…
## reenganche-2
…
## desarrollo-2
…
## cierre
…
```

Una frase o dos por línea, para que se lea bien. Sin indicaciones de cámara, de edición ni de pantalla.

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
