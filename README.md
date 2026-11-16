# hermes-youtube

**De tu material propio a un vídeo listo para grabar, con agentes de IA y sin perder el control.** A partir de lo que
tu canal ya tiene (directos, cursos, pódcast, guiones antiguos), un equipo de agentes propone temas y prepara para
cada uno un **paquete**: título, idea de miniatura, guion palabra por palabra con la voz de quien presenta,
descripción con capítulos y la lista de datos a verificar. Las personas no escriben: deciden en unas pocas **puertas**
con un botón, y cada decisión queda registrada.

Es un plugin para [Hermes Agent](https://github.com/NousResearch/hermes-agent), hermano de
[hermes-sdd](https://github.com/noelserdna/hermes-sdd) y [hermes-seo](https://github.com/noelserdna/hermes-seo): el
mismo esqueleto (pipelines como datos, puertas, notario sin IA, revisión mecánica, memoria en una wiki), aplicado a la
creación de contenido para YouTube.

> **Estado: en diseño.** Todavía no hay código instalable. El diseño completo está en
> [docs/diseno.md](docs/diseno.md) y la [hoja de ruta](#hoja-de-ruta) dice en qué orden se construye.

---

## Índice

1. [Para qué sirve](#para-qué-sirve)
2. [La idea en una tabla](#la-idea-en-una-tabla)
3. [El recorrido](#el-recorrido)
4. [El equipo de agentes](#el-equipo-de-agentes)
5. [Cómo decide la persona](#cómo-decide-la-persona)
6. [Por qué suena a la persona y no a una IA](#por-qué-suena-a-la-persona-y-no-a-una-ia)
7. [Lo que se comprueba sin IA](#lo-que-se-comprueba-sin-ia)
8. [Qué pone el plugin y qué pone cada canal](#qué-pone-el-plugin-y-qué-pone-cada-canal)
9. [Qué no hace](#qué-no-hace)
10. [Hoja de ruta](#hoja-de-ruta) · [Estructura](#estructura-prevista) · [Créditos](#créditos) · [Licencia](#licencia)

---

## Para qué sirve

Un canal que publica varias veces por semana se atasca casi siempre en el mismo sitio: el guion. Los guiones
generados con IA suenan a IA, no van al grano y quien presenta acaba reescribiéndolos. Tampoco suele haber un método
para elegir temas con potencial ni para preparar el título y la miniatura antes de escribir.

hermes-youtube ataca ese atasco con tres reglas:

- **Solo material propio.** El sistema no inventa cifras, casos ni anécdotas. Todo lo que afirma el guion sale de las
  fuentes del canal o va a una lista de datos que una persona verifica uno a uno.
- **Primero la promesa, después el guion.** No se escribe una línea hasta que alguien ha elegido el título y la idea
  de miniatura: esa pareja es la promesa que el guion tiene que cumplir.
- **La voz se aprende de cómo habla la persona**, con fragmentos reales suyos, y se comprueba frase a frase.

## La idea en una tabla

| Papel | Quién | Qué hace |
|---|---|---|
| **Propone** | los agentes, uno por oficio | hacen cada etapa entera: inventario, temas, títulos, miniaturas, guion, descripción |
| **Critica** | agentes que no han escrito nada | el «espectador» puntúa ideas y títulos como los vería en su página de inicio; el verificador, el de retención y el doble de voz buscan fallos en el guion |
| **Comprueba** | la revisión mecánica (sin IA) | longitudes, estructura, expresiones vetadas, exclusiones y trazabilidad de cada dato |
| **Pregunta** | la puerta | enseña el resultado y pide una decisión con botones |
| **Decide** | las personas, cada una en su papel | aprobar, rehacer con un comentario o rechazar |
| **Firma** | el notario (sin IA) | comprueba quién decidió y qué, lo registra y lanza lo siguiente |
| **Orquesta** | el kanban de Hermes (sin IA) | encadena las etapas: un tablero por canal |

## El recorrido

🚪 = puerta, donde todo se para hasta que una persona decide.

```
 fuentes ─▶ inventario y voz ─▶ temas ─▶ 🚪 elegir temas ─▶ título y miniatura ─▶ 🚪 elegir la pareja
                                                                                        │
     ┌──────────────────────────────────────────────────────────────────────────────────┘
     ▼
   guion ─▶ 🚪 revisión ─▶ 🚪 datos ─▶ 🚪 revisión final ─▶ aprobado ─▶ grabado ─▶ publicado
     ▲           │                          │
     └───────────┴──── rehacer (máx. 3) ────┘
```

1. **Fuentes.** Se cargan las transcripciones del canal. Un agente las limpia y saca un **inventario de piezas**:
   afirmaciones rotundas, creencias que se rebaten, casos con nombre, analogías, preguntas de la audiencia, demos y
   cifras, cada una con su fuente y su minuto. Lo que el canal marque como excluido (precios, ofertas, datos
   personales) se queda fuera aquí, frase a frase.
2. **Voz.** Una vez por presentador se construye un corpus con fragmentos literales suyos por tipo de bloque, su banco
   de analogías y las métricas de cómo habla (largo de frase, muletillas, ritmo de lectura real).
3. **Temas.** Un embudo: se generan decenas de candidatos por pilar, otro agente los puntúa viendo solo el título, y
   el código selecciona los mejores exigiendo que haya material suficiente y que no se parezcan a lo ya publicado.
4. **Título y miniatura.** Brief con audiencia, promesa y tres ángulos; treinta títulos repartidos por palancas, de
   los que se presentan cinco; tres ideas de miniatura distintas entre sí. El sistema describe la miniatura, no la
   dibuja.
5. **Guion.** Se reúne el material, se fija la escaleta, se escribe por bloques, se verifica cada afirmación y se
   critica la retención y la voz. Sale el guion limpio para el teleprompter, la descripción con capítulos y la lista de
   datos.
6. **Revisiones.** En el orden que configure el canal. Por defecto: marketing, verificación de datos y presentador.

## El equipo de agentes

| Agente | Qué hace | Qué no hace |
|---|---|---|
| Analista | Limpia las fuentes y extrae el inventario de piezas | No decide de qué se hacen vídeos |
| Estratega | Genera candidatos de tema y el brief de cada uno | No se puntúa a sí mismo |
| Espectador | Puntúa ideas, títulos y miniaturas como alguien que no conoce el canal | No ve el resumen ni el origen: solo lo que vería en el feed |
| Titulador | Treinta títulos por tema, repartidos entre palancas | No elige los cinco finales: lo hace el código con las notas |
| Miniaturista | Tres briefs que un diseñador puede ejecutar sin preguntar | No genera imágenes ni inventa la marca |
| Investigador | Reúne el material de un tema con su cita literal | No pasa nada excluido al guionista |
| Guionista | Escaleta, guion por bloques y descripción | No añade datos que no estén en el material |
| Verificador | Traza cada afirmación a su fuente y lista lo que hay que verificar | No aprueba «con reservas» |
| Retención | Revisa solo la intro, los reenganches y el cierre | No toca el contenido |
| Doble de voz | Dice, frase a frase, si la persona lo diría así y cómo lo diría | No reescribe |
| Editor jefe | Comprueba que título, miniatura, primera frase, descripción y cierre cuentan lo mismo | No decide: prepara lo que llega a la puerta |

## Cómo decide la persona

Cada puerta llega por correo, con el contenido completo y tres botones. El comentario se escribe en la propia
respuesta.

| Botón | Qué pasa |
|---|---|
| **Aprobar** | El paquete avanza a la siguiente puerta. Es inmediato. |
| **Rehacer** | El sistema lo rehace aplicando el comentario y tocando solo lo pedido. Cuenta una ronda; a la cuarta, el tema se descarta. |
| **Rechazar** | El tema se descarta y el comentario se guarda para no repetir el fallo. |

Las frases del guion van numeradas, así que el comentario puede ser tan concreto como «frase 14: yo diría…». Solo
decide quien tiene el papel de esa puerta, y solo con el código de un solo uso de su botón: ningún agente puede
aprobar en nombre de nadie. Los datos se verifican en el panel web, uno a uno: verificado, corregido o eliminado.

## Por qué suena a la persona y no a una IA

- **Corpus, no adjetivos.** El guionista recibe fragmentos reales del presentador y guiones suyos enteros, no una
  descripción de su tono.
- **Un crítico que no escribe.** El doble de voz revisa cada frase contra ese corpus.
- **Métricas calibradas con la propia persona.** El largo de frase, la proporción de frases cortas y el tope de
  muletillas salen de medir cómo habla, no de una regla general.
- **Aprende.** Cada guion aprobado pasa a ser ejemplo. Cada comentario se convierte en una regla con su antes y
  después. La transcripción del vídeo ya grabado, comparada con el guion, enseña qué cambió al decirlo.

## Lo que se comprueba sin IA

Antes de que algo llegue a una persona pasa una revisión por código. Si hay un fallo grave, no sale.

| Sobre | Se comprueba |
|---|---|
| Todo el paquete | Contenido excluido, nombres vetados, promesas no permitidas |
| Títulos | Longitud, cómo queda cortado en móvil, palabra clave al principio, clichés, palancas distintas |
| Miniaturas | Campos completos, texto breve que no repite el título, las tres distintas entre sí |
| Guion | Duración leída, intro, bloques y su tamaño, expresiones vetadas, largo de frases, repeticiones, cifras escritas como se leen, aperturas y remates no repetidos respecto a guiones anteriores |
| Datos | Toda cifra y todo nombre propio aparece en el material con su cita literal o en la lista de verificación |
| Descripción | Resumen y capítulos válidos para YouTube: el primero en 00:00, al menos tres, ninguno de menos de 10 segundos |

## Qué pone el plugin y qué pone cada canal

El plugin es agnóstico: nada de un canal concreto vive en el código, las skills ni los perfiles.

| Es del plugin | Es del canal |
|---|---|
| El recorrido y sus pipelines | Presentador, idioma, pilares y formatos repetibles |
| Los agentes y el oficio de YouTube | Sus fuentes y qué partes se excluyen |
| Los tipos de regla de la revisión mecánica | Los valores: duración, longitudes, ritmo, expresiones vetadas |
| Puertas, papeles, rondas y notario | Quién tiene cada papel, cuántas puertas y en qué orden |
| Correo, panel, métricas y exportación | Guía de voz, corpus, marca y lista de vídeos publicados |

Un canal de una sola persona puede dejar una única puerta. Los datos de cada canal viven solo en la máquina de
Hermes, nunca en este repositorio.

## Qué no hace

- No publica en YouTube ni en ninguna otra plataforma.
- No genera imágenes, vídeo ni voz.
- No inventa datos, casos ni anécdotas.
- No decide por nadie.

## Hoja de ruta

| Paso | Qué | Estado |
|---|---|---|
| 0 | Diseño y repositorio | hecho |
| 1 | Esqueleto del plugin a partir de hermes-seo, con sus pruebas sin IA | pendiente |
| 2 | Canal, carga de fuentes, inventario y perfil de voz | pendiente |
| 3 | Pipeline de guion y revisión mecánica, con ejecución local | pendiente |
| 4 | Propuesta de temas, títulos y miniaturas | pendiente |
| 5 | Cadena de puertas, papeles, rondas y estados | pendiente |
| 6 | Correo | pendiente |
| 7 | Panel | pendiente |

## Estructura prevista

| Ruta | Qué es |
|---|---|
| `plugin/hermes-youtube/` | El plugin: canales, pipelines, encargos, etapas, puertas, revisión, correo, CLI y pestaña del panel |
| `pipelines/` | El recorrido como datos (JSON) |
| `skills/` | Lo que hace cada etapa |
| `referencias/` | Oficio compartido entre skills: retención, packaging, descripción y fórmulas de gancho |
| `perfiles/` | La carta de cada agente |
| `plantillas/` | Configuración de partida por tipo de canal |
| `executors/` | Claude Code y Hermes |
| `tests/` | Todas las pruebas, sin IA ni red |

## Créditos

- El esqueleto viene de [hermes-seo](https://github.com/noelserdna/hermes-seo) y
  [hermes-sdd](https://github.com/noelserdna/hermes-sdd).
- El esquema de fórmulas de gancho, la puntuación de la apertura y las comprobaciones de título y miniatura como
  pareja se inspiran en [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill) (MIT).
- La separación en skills, guías de referencia y plantillas por tipo de canal se inspira en
  [claude-youtube](https://github.com/AgriciDaniel/claude-youtube) (MIT).
- El libro de citas con evidencia literal sigue el patrón de la skill `grounded-citations` de Hermes Agent.

## Licencia

MIT.
