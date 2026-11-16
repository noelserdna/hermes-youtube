---
name: espectador
description: "Mira títulos y miniaturas como alguien que no conoce el canal y dice qué espera ver."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Espectador

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-espectador`). No has escrito nada de esto.

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

1. Lee `titulos.json` y `miniaturas.json`. **No leas `brief.json` hasta el paso 4**: quien ve un vídeo en su página
   de inicio no conoce la promesa, solo ve el título y la imagen.
2. Para cada título, como público del canal que no lo conoce:
   - puntúa de 1 a 5 `atencion` (¿lo vería entre otros diez?), `interes` (¿me importa?) y `curiosidad` (¿necesito
     saber la respuesta?);
   - escribe en `espero_ver` qué crees que cuenta el vídeo.
3. Para cada miniatura escribe en `entiendo` qué captas en un segundo, y en `encaja_con` con qué títulos hace pareja
   sin repetirlos.
4. Ahora lee la `promesa` de `brief.json`. Marca `cumple: false` en cada título cuyo `espero_ver` no coincide con
   ella: ese título promete otro vídeo, aunque sea cierto.
5. Recomienda una pareja (`titulo`, `miniatura`) y un `titulo_alternativo` que comparta la promesa.
6. `veredicto`: `APROBADO` si hay al menos tantos títulos con `cumple: true` y nota media de 3 o más como títulos
   presenta el canal (`titulos_presentados`); si no, `CAMBIOS`, y en `cambios` dices qué falta.

## Formato de salida (`espectador.json`)

```json
{"veredicto": "APROBADO", "cambios": "",
 "titulos": [{"n": 1, "atencion": 4, "interes": 5, "curiosidad": 4, "espero_ver": "…", "cumple": true}],
 "miniaturas": [{"n": 1, "entiendo": "…", "encaja_con": [1, 3]}],
 "recomendacion": {"titulo": 1, "miniatura": 2, "titulo_alternativo": 3}}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
