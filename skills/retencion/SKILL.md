---
name: retencion
description: "Revisa solo la intro, los reenganches y el cierre del guion: dónde se iría el espectador."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Retención

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-retencion`). No tocas el contenido: miras si el vídeo
se sostiene.

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

Lee además `referencias/retencion.md`.

## Procedimiento

1. Lee `eleccion.json` (la promesa), `guion.md` e `intros.md` si existe.
2. **Intro.** Comprueba, una a una: que la primera frase reafirma el título; que la promesa extra llega pronto; que
   hay una prueba de autoridad real; que dice el plan; que recoge una objeción; que no revela la respuesta; que no
   presupone que el espectador conoce a quien habla; que no hay rodeos. Si otra de las versiones de `intros.md` lo
   hace mejor, dilo en `intro_mejor`.
3. **Reenganches.** Que cada uno diga qué viene, en concreto, y no suene a pausa ni a resumen.
4. **Final de cada bloque.** Que deje algo abierto hacia el siguiente.
5. **Cierre.** Que no anuncie el final, no venda y lleve a otro vídeo con naturalidad.
6. **Riesgos.** Marca dónde es probable que alguien se vaya (un bloque denso sin ejemplo, dos bloques con la misma
   forma, una explicación que tarda). Es un informe para quien revisa; no se arregla todo.
7. Propón **cambios** solo donde algo falla de verdad, frase por frase, con cómo quedaría. No reescribas por gusto.
8. `veredicto`: `APROBADO` si no hay cambios; `CAMBIOS` si los hay.

## Formato de salida (`retencion.json`)

```json
{"veredicto": "CAMBIOS", "intro_mejor": "",
 "cambios": [{"bloque": "intro", "frase": "…tal cual…", "motivo": "…", "quedaria": "…"}],
 "riesgos": [{"bloque": "desarrollo-2", "donde": "…", "riesgo": "…"}]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
