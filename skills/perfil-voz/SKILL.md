---
name: perfil-voz
description: "Construye el perfil de voz de quien presenta a partir de sus fuentes: ejemplos literales y medidas."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Perfil de voz

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-doble`).

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

1. Lee las fuentes del canal (carpeta `fuentes/`, con su `indice.json`) donde habla quien presenta. Distingue el registro: **guionizado** (vídeos cortos leídos)
   y **espontáneo** (directos). El objetivo de un guion es la estructura del primero con el léxico del segundo.
2. Si existe `voz-canal.md` en el encargo, es la guía de voz actual del canal y tu punto de partida: complétalo, no lo contradigas sin prueba.
3. Recoge **fragmentos literales** por función, con su fuente y su marca. De tres a seis por función:
   apertura, error común, analogía, definición por contraste, pregunta que se contesta, remate, transición,
   humor, crítica.
4. Haz el **banco de analogías y casos**: cada uno con su fuente y una línea de para qué sirve.
5. Lista sus **muletillas** con la frecuencia aproximada en cada registro, y las **fórmulas de apertura** que repite
   (si casi todos sus vídeos abren igual, dilo: habrá que variar).
6. Elige de dos a tres fuentes guionizadas enteras que sirvan de ejemplo completo y nómbralas.
7. No describas la voz con adjetivos sueltos. Cada rasgo va con su ejemplo.

## Formato de salida (`perfil-voz.md`)

Con estos apartados, en este orden y con estos títulos:

```
## A quién habla
## Cómo habla de verdad
## Fragmentos por función
### <función>
- «…literal…» (<colección>/<id> <marca>, guionizado|espontáneo)
## Banco de analogías y casos
## Palabras suyas
## Palabras que nunca usa
## Lo que no afirma
## Aperturas que repite
## Ejemplos completos
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
