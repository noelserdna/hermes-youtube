---
name: miniaturas
description: "Escribe tres encargos de miniatura distintos entre sí, que un diseñador pueda ejecutar sin preguntar."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Miniaturas

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-miniaturista`). Describes la idea; no generas imágenes.

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

Lee además `referencias/packaging.md` (los apartados «La miniatura» y «La pareja»).

## Procedimiento

1. Lee `brief.json` y `titulos.json`. La miniatura dice **la otra mitad**: lo que el título no dice.
2. Escribe el número de ideas que pide el canal (`miniaturas`), **una por ángulo**. Tienen que ser completamente
   distintas: otro `concepto`, otro tipo de `composicion` y otra `expresion`. Tres variaciones de la misma foto no
   son tres ideas.
3. Para cada una:
   - `concepto`: una palabra (dilema, antes-despues, objeto, cifra, reaccion, comparacion, despiece…);
   - `que_se_ve` y `elementos` reconocibles a primera vista;
   - `presentador`: si aparece, su `expresion` (clara y creíble, nunca exagerada), su `mirada` y la `foto_a_pedir`
     el día de grabación;
   - `composicion`: `tipo`, `foco` y `fondo`. La esquina inferior derecha queda libre;
   - `texto`: como mucho las palabras que permite el canal, y **ninguna palabra con significado que esté en un
     título**. Añade un `texto_alternativo`;
   - `reparto`: qué dice el título y qué dice la miniatura;
   - `no_revela`: qué queda por saber;
   - `legible_en_movil`: qué tiene que seguir viéndose al tamaño de un móvil;
   - `evitar`;
   - `hipotesis`: por qué atraería esta y no otra;
   - `marca`: cómo aplica la marca del canal. Si `contexto-canal.md` no la define, escribe `pendiente` y describe
     contraste y jerarquía sin inventar colores ni tipografías;
   - `encaja_con`: los números de los títulos con los que hace pareja.

## Formato de salida (`miniaturas.json`)

```json
{"miniaturas": [{"n": 1, "angulo": "a1", "concepto": "dilema", "que_se_ve": "…", "elementos": ["…"],
  "presentador": {"aparece": true, "expresion": "duda", "mirada": "al objeto", "foto_a_pedir": "…"},
  "composicion": {"tipo": "cara-derecha-objeto-izquierda", "foco": "…", "fondo": "…"},
  "texto": "…", "texto_alternativo": "…", "reparto": "…", "no_revela": "…", "legible_en_movil": "…",
  "evitar": "…", "hipotesis": "…", "marca": "pendiente", "encaja_con": [1, 3]}]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
