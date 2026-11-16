---
name: generar-temas
description: "Genera muchos candidatos de vídeo por pilar a partir del inventario del canal."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Generar temas

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-estratega`). Tú generas; otro agente puntúa y un
programa selecciona. No te autocensures: aquí importa la cantidad con criterio.

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

Lee además `referencias/packaging.md` (el apartado «La idea»).

## Procedimiento

1. Lee `inventario.json` (las piezas del canal) y `banco.json` (las ideas ya propuestas, elegidas, descartadas y
   publicadas). No las repitas.
2. Por cada pilar genera **entre veinte y treinta candidatos**. Cada uno:
   - tiene un `titulo` redactado como un título de verdad, nunca «vídeo sobre X»;
   - una `linea` que diga qué se lleva quien lo ve;
   - cita las `piezas` del inventario que lo sostienen (por su `id`). Una idea buena junta piezas de varias fuentes:
     no conviertas un tramo en un vídeo;
   - encaja en un `formato` del canal si puede, y dice con qué otros candidatos forma `serie`;
   - `enlaza_con`: otros candidatos a los que llevaría el cierre de este vídeo;
   - `demanda`: qué prueba hay de que a alguien le interesa (`pregunta` si sale de una duda real de la audiencia,
     `repetida` si la duda aparece varias veces, `ninguna` si es intuición tuya), con la evidencia.
3. Ningún título presupone que el espectador conoce el canal, a quien presenta ni un evento.
4. Ningún título depende de dinero, empleo o salario, ni de nada excluido por el canal.
5. Si un pilar no da para veinte candidatos con material, genera los que haya y dilo en `avisos`. No lo rellenes con
   ideas de otro pilar.

## Formato de salida (`candidatos.json`)

```json
{"candidatos": [{"id": "c01", "pilar": "<id>", "titulo": "…", "linea": "…", "piezas": ["p012", "p044"],
                 "formato": "<id o vacío>", "serie": "<nombre o vacío>", "enlaza_con": ["c07"],
                 "demanda": {"tipo": "pregunta", "evidencia": "…"}}],
 "avisos": ["…"]}
```

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
