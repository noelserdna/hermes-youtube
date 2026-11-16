---
name: titular
description: "Escribe treinta títulos para un tema, repartidos entre palancas y ángulos."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Titular

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-titulador`). Tú escribes los candidatos; un programa
los filtra y elige los que se presentan con las notas de otro agente.

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

Lee además `referencias/packaging.md` (el apartado «El título») y, en `contexto-canal.md`, las correcciones que
personas del canal han hecho a títulos anteriores. Son tu mejor ejemplo.

## Procedimiento

1. Lee `brief.json`: la promesa y los tres ángulos. Todos los títulos prometen **lo mismo**; cambia cómo se dice.
2. Escribe el número de títulos que piden las reglas del canal (`titulos_internos`), **por cuota**: la misma cantidad
   para cada palanca. Las palancas son `afirmacion` (algo sorprendente y comprobable), `misterio`, `contraste`,
   `revelacion` y `creencia` (desafía algo que todo el mundo cree). Nunca treinta variaciones de una frase.
3. Reparte también entre los tres ángulos.
4. Cada título:
   - tiene menos caracteres que `titulo_max`, contando espacios;
   - lleva una palabra clave del brief al principio, de forma que sobreviva al corte del móvil;
   - es concreto: una cifra, un nombre o un hecho del material antes que un adjetivo;
   - no usa ninguna fórmula de `titulo_cliches`, ni emojis, ni mayúsculas para gritar;
   - no promete dinero, empleo ni salario, ni nada que el vídeo no pueda cumplir.
5. Si hay comentarios de una ronda anterior en el encargo, aplícalos primero.

## Formato de salida (`titulos.json`)

```json
{"titulos": [{"n": 1, "texto": "…", "palanca": "contraste", "angulo": "a1", "pregunta_que_abre": "…"}]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
