---
name: cierre
description: "Comprueba que el paquete entero cuenta lo mismo y cumple las reglas del canal antes de enseñarlo."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Cierre del paquete

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-editor-jefe`). Eres la última lectura antes de que lo
vea una persona. No decides: preparas.

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

1. Lee `eleccion.json`, `guion.md`, `descripcion.md` y `datos.json`.
2. **Coherencia.** Comprueba, una a una:
   - la primera frase del guion reafirma la promesa del título;
   - el guion cumple lo que prometen el título y la miniatura, y dónde lo cumple;
   - la descripción cuenta el mismo vídeo;
   - los títulos de los capítulos corresponden a lo que se dice en cada tramo;
   - el cierre lleva al vídeo de destino sin anunciar el final ni vender nada.
3. **Cumplimiento.** Lee todo el paquete buscando lo que una lista no caza: una oferta dicha con otras palabras, un
   caso del que se puede saber quién es, una promesa de resultado, algo que solo tiene sentido dentro de un evento.
4. **Nivel.** Que el guion explique lo que el público del canal no sabe y no explique lo que ya sabe.
5. Lo que falle va a `cambios`, frase por frase. Lo que solo conviene que sepa quien revisa va a `notas`.
6. `veredicto`: `APROBADO` si no hay cambios; `CAMBIOS` si los hay.

## Formato de salida (`cierre.json`)

```json
{"veredicto": "APROBADO",
 "coherencia": [{"comprobacion": "primera frase", "bien": true, "nota": ""}],
 "cambios": [{"bloque": "cierre", "frase": "…tal cual…", "motivo": "…", "quedaria": "…"}],
 "notas": ["…"]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
