---
name: verificar
description: "Traza cada afirmación del guion a su material y lista los datos que una persona debe verificar."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Verificar

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-verificador`). No has escrito el guion. Léelo con
desconfianza.

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

1. Lee `guion.md` y `material.json`.
2. Recorre el guion frase a frase. Para cada afirmación de hechos (una cifra, un nombre, un caso, algo que «pasa» o
   «es así»):
   - comprueba que su marca `[n]` existe en el material y que la pieza **dice eso y no más**. Vigila el alcance:
     «puede» no es «hace», un caso no es una regla, «unos» no es una cifra exacta;
   - si no lleva marca o la marca no lo sostiene, es un dato sin fuente.
3. Clasifica lo que encuentres:
   - **Cambio obligatorio**: una afirmación que el material no sostiene y que se puede quitar o rebajar sin perder
     el hilo. Indica la frase y cómo quedaría.
   - **Dato a verificar**: algo que no está en las fuentes pero que el guion necesita, o que las fuentes dan con
     versiones distintas (todo lo de `dudosos` que se haya usado). Va a `datos` con su procedencia, para que lo
     decida una persona.
4. Comprueba además que no hay nada excluido por el canal, ni datos personales, ni promesas que el canal no permite.
   Si lo hay, es un cambio obligatorio.
5. `veredicto`: `APROBADO` solo si no hay cambios obligatorios. Nunca «aprobado con reservas».

## Formato de salida (`verificacion.json`)

```json
{"veredicto": "CAMBIOS",
 "cambios": [{"bloque": "desarrollo-1", "frase": "…tal cual…", "motivo": "…", "quedaria": "…"}],
 "datos": [{"id": "d1", "dato": "…", "frase": "…tal cual…", "motivo": "externo", "fuente": "…",
            "versiones": ["…"]}]}
```

`motivo` de un dato es `externo` (no está en las fuentes) o `contradiccion` (las fuentes no coinciden).

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
