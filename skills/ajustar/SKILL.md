---
name: ajustar
description: "Aplica al guion, frase por frase, los cambios pedidos por los críticos, por la revisión o por una persona."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Ajustar

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-guionista`). No reescribes: corriges lo señalado.

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

1. Lee `guion.md` y `ajustes.json`: la lista de cambios pedidos, cada uno con su bloque, la frase tal cual, el
   motivo y, a veces, cómo quedaría. Vienen de la verificación, de la revisión de retención, de la de voz, de la
   revisión por código o de la verificación de datos de una persona.
2. Aplica **todos** los cambios y **solo** esos:
   - si traen `quedaria`, úsalo salvo que rompa la frase siguiente; entonces adáptalo lo mínimo;
   - si un dato se ha corregido, cambia el valor en todas las frases que lo usan;
   - si un dato se ha eliminado, quita la frase o rehazla sin él, y arregla la unión;
   - si dos cambios chocan, manda la verificación sobre la voz, y la voz sobre la retención.
3. No toques ninguna frase que no esté en la lista, aunque creas que mejora.
4. Conserva las cabeceras de los bloques y las marcas `[n]`.
5. Si tras los cambios un bloque se sale de su presupuesto de palabras, dilo en tu resumen; no rellenes ni recortes
   por tu cuenta.

## Formato de salida

- `guion.md`, sobrescrito, con el mismo formato.
- `ajustes-aplicados.json`:

```json
{"aplicados": [{"bloque": "intro", "antes": "…", "despues": "…"}],
 "sin_aplicar": [{"frase": "…", "motivo": "…"}]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
