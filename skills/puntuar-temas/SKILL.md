---
name: puntuar-temas
description: "Puntúa candidatos de vídeo como los vería alguien que no conoce el canal."
version: 0.1.0
metadata:
  hermes:
    tags: [YouTube, hermes-youtube]
    category: hermes-youtube
---

# Puntuar temas

Etapa de una pipeline de hermes-youtube (perfil habitual: `yt-espectador`). No has generado estas ideas y no tienes
que defenderlas.

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

1. Lee `candidatos.json`. De cada candidato mira **solo el título y la línea**, como lo vería alguien en su página de
   inicio. No mires de qué piezas sale ni de qué fuente: el espectador no lo sabe.
2. Ponte en la piel de quien describe `contexto-canal.md` como público, pero que **no conoce el canal**.
3. Puntúa de 1 a 5 cada criterio:
   - `tres_publicos`: ¿interesa a quien sigue el canal, a quien lo conoce de pasada y a quien no lo conoce?
   - `atemporal`: ¿seguirá interesando dentro de dos años?
   - `curiosidad`: ¿hay distancia entre lo que sé y lo que quiero saber?
   - `diferente`: ¿aporta algo que no he visto ya en diez vídeos?
   - `repetible`: ¿da para más vídeos parecidos?
4. Pon un `veto` (con el motivo en una frase) si se cumple alguno:
   - solo interesa a quien ya iba a comprar algo;
   - el gancho depende de dinero, empleo o salario;
   - la respuesta se adivina sin ver el vídeo;
   - cualquier otro canal haría exactamente el mismo vídeo;
   - presupone conocer el canal, a quien presenta o un evento;
   - lleva un año, una versión o un producto que lo hará caducar.
5. Escribe una `frase` por candidato: por qué pulsarías o por qué no. Sé duro; lo cómodo es poner cuatros.

## Formato de salida (`puntuacion.json`)

```json
{"notas": [{"id": "c01", "tres_publicos": 4, "atemporal": 5, "curiosidad": 3, "diferente": 2, "repetible": 4,
            "veto": "", "frase": "…"}]}
```

Una nota por cada candidato, sin saltarte ninguno.

## Al terminar

Termina tu respuesta con una sola línea que resuma el resultado.
