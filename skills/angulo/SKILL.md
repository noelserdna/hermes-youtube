---
name: angulo
description: "Prepara el encargo de packaging de un tema: audiencia, promesa y tres ángulos con respaldo en las fuentes."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Ángulo

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-estratega`).

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

Lee además `referencias/packaging.md`.

## Procedimiento

1. Lee el tema del encargo y las piezas del inventario que lo sostienen. Si el tema lo escribió una persona y no cita
   piezas, búscalas tú en `inventario.json`.
2. Define:
   - `audiencia`: una persona concreta, no una categoría;
   - `deseo`: qué quiere conseguir o qué teme;
   - `palabras_clave`: las dos o tres palabras con las que buscaría esto;
   - `promesa`: qué sabrá o podrá hacer al acabar el vídeo, en una frase que el vídeo pueda cumplir **con el material
     que hay**.
3. Propón **tres ángulos** distintos de entrar al tema. Cada uno con su `respaldo`: los `id` de las piezas que
   permiten cumplirlo. Un ángulo sin respaldo no existe.
4. Suma las `palabras` de las piezas de respaldo. Si no llegan a la mitad de lo que pide un guion del canal, o si al
   escribir la promesa la idea pierde fuerza, el veredicto es `IDEA DEBIL` y explicas por qué. Descartar aquí es más
   barato que después del guion.

## Formato de salida (`brief.json`)

```json
{"veredicto": "ADELANTE", "motivo": "",
 "audiencia": "…", "deseo": "…", "palabras_clave": ["…", "…"], "promesa": "…",
 "angulos": [{"id": "a1", "texto": "…", "respaldo": ["p012", "p044"]}],
 "material_palabras": 2400}
```

`veredicto` es `ADELANTE` o `IDEA DEBIL`.

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
