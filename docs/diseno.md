# Diseño de hermes-youtube

Este documento describe qué se va a construir y por qué. Es la referencia mientras no haya código; cuando lo haya, lo
que diga el código manda y este documento se corrige.

## 1. Objetivo

Que un canal de YouTube con material propio pueda preparar varios vídeos por semana sin que nadie tenga que escribir
el guion a mano, y que la persona que presenta apruebe la mayoría a la primera con retoques mínimos.

Entrega del sistema para cada tema, el **paquete**:

- título elegido,
- idea de miniatura elegida (descrita en texto),
- guion palabra por palabra, listo para el teleprompter,
- descripción de YouTube con capítulos,
- lista de datos a verificar, cada uno con su fuente.

Principios:

1. **Solo material propio.** Nada inventado. Lo que no está en las fuentes va a la lista de verificación.
2. **La promesa antes que el guion.** Sin título y miniatura elegidos no se escribe.
3. **Decide una persona, firma el notario.** Ningún agente aprueba, publica ni cambia la configuración.
4. **Lo que se puede comprobar por código no se deja a un modelo.**
5. **Agnóstico.** Lo particular de un canal es configuración y memoria, nunca código.

## 2. De dónde sale

El esqueleto es el de hermes-seo. Se copia y se renombra (`hseo_` → `hyt_`, CLI `hyt`, datos en
`~/.hermes/hermes-youtube`, perfiles `yt-*`).

| Se conserva | Se adapta | No se trae |
|---|---|---|
| Primitivas de datos, encargos, lecciones, modelos por etapa, estado, ejecutores, guardia, instalación, dobles de prueba | Pipelines (constantes), puertas (opciones, cadena, papeles), contexto de etapa, revisión mecánica, clientes → canales, wiki, correo, CLI, plugin y panel | Publicación, datos de buscadores, tandas, autoridad, visibilidad en IA, vigilancia, cliente MCP, autoactualización y el encargado con modelo |

Piezas de Hermes en las que se apoya: la skill `grounded-citations` (patrón de libro de citas con evidencia literal),
`humanizer` (catálogo de patrones de texto de IA), `youtube-content` (transcripción de un vídeo por su URL) y
`llm-wiki` (memoria).

## 3. Canal

Un canal es la unidad de trabajo: su configuración, sus fuentes, su memoria y sus vídeos. Vive en
`canales/<slug>/` dentro de la carpeta de datos, nunca en el repositorio.

`canal.json`:

| Bloque | Contenido |
|---|---|
| Identidad | `presentador`, `idioma`, `pilares[]` (con `tipo: pilar` o `prueba`), `formatos[]` (moldes de vídeo repetibles) |
| `reglas` | Longitud máxima de título, títulos internos y presentados, número de miniaturas, ritmo de lectura declarado y medido, minutos objetivo, máximo de palabras de la intro, rondas máximas, temas por pilar, cadencia de reenganches, umbrales de frase y de muletillas |
| Listas | `prohibidas[]`, `cierres_prohibidos[]`, `titulo_cliches[]`, `excluido[]`, `sin_promesas[]` (patrones) y `nombres_vetados[]` |
| `transcripcion` | Pistas de corrección para el reconocimiento automático y marcas de ruido |
| `marca` | Tipografía, colores y logo para las miniaturas. Si está vacío, el miniaturista no los inventa |
| `personas` | Quién es quién, con su correo y sus papeles (`marketing`, `datos`, `presentador`) |
| `permite` | Interruptores para decisiones de contenido del canal, todos apagados de partida |
| Operación | Modelos y ejecutores por etapa, pausa, topes |

Hay plantillas de partida por tipo de canal (educativo, marca personal, tutorial) con valores distintos.

## 4. Fuentes, inventario y voz

### Carga

`hyt fuentes cargar <canal> <carpeta|zip|url> --coleccion <nombre> --tipo <tipo>`, sin IA: descomprime, se queda con
el texto, usa los subtítulos con tiempos solo para medir el ritmo de lectura real, quita el ruido y trocea por marca
de tiempo.

### Inventario

Pipeline `inventario`. Un agente recorre cada tramo: corrige la transcripción con contexto (no por sustitución
ciega), marca lo excluido y quién habla, y extrae **piezas**:

- afirmación rotunda, creencia rebatida, caso con nombre, analogía, pregunta de la audiencia, demo, cifra.

Cada pieza guarda fuente, minuto, pilar, palabras limpias, cita literal y `usado_en`. Las cifras que se contradicen
entre fuentes quedan señaladas. De los tramos de testimonio salen los `nombres_vetados`.

### Voz

Pipeline `perfil-voz`, una vez por presentador y con su puerta:

- `voz.md`: a quién habla, cómo habla de verdad, palabras suyas, palabras que nunca usa, lo que no afirma, su formato;
- `voz-ejemplos.md`: fragmentos literales por tipo de bloque, con procedencia y registro (guionizado o espontáneo);
- `banco-analogias.md`: analogías y casos, con dónde se han usado ya;
- métricas medidas: largo medio de frase, proporción de frases cortas, frecuencia de muletillas, palabras por minuto.

La voz evoluciona: cada guion aprobado se añade como ejemplo, y la transcripción del vídeo ya grabado se compara con
su guion.

## 5. Pipelines de producción

### `propuesta`

| Etapa | Quién | Qué hace |
|---|---|---|
| `generar` | estratega | Decenas de candidatos por pilar: título y una línea, las piezas del inventario que usa, formato, serie y con qué otros temas enlaza |
| `puntuar` | espectador, con otro modelo | Ve solo el título y la línea. Nota por criterio y vetos |
| `seleccionar` | código | Ordena, aplica vetos y cupo por pilar, exige material suficiente y calcula el parecido con lo ya propuesto y publicado |

Los candidatos viven en un banco de ideas con estado y puntuación; cada petición lo repuntúa y solo genera lo que
falta. Si un pilar no da para su cupo, se proponen menos y se avisa. Puerta `elegir-temas`.

### `titulo-miniatura`

| Etapa | Quién | Salida |
|---|---|---|
| `angulo` | estratega | Brief: audiencia, deseo, palabras clave, promesa y tres ángulos con respaldo en las fuentes. Puede devolver «idea débil» |
| `titular` | titulador | Treinta títulos por cuota entre palancas, cada uno con su ángulo y la pregunta que abre |
| `miniaturas` | miniaturista | Tres briefs, uno por ángulo: qué se ve, expresión y mirada, foto que hay que pedir, composición, texto, reparto de información con el título, qué debe leerse en móvil, qué evitar |
| `espectador` | espectador | Ve título y miniatura como en el feed y dice qué espera ver. Si no coincide con la promesa, se descarta |

El código filtra y elige los cinco títulos con variedad de palancas y ángulos. Puerta `elegir-titulo`: un solo
mensaje para todos los temas de una propuesta, con las parejas recomendadas; admite título propio (se valida y se
avisa, sin bloquear), una nota para la miniatura y el vídeo de destino del cierre.

### `guion`

| Etapa | Quién | Qué hace |
|---|---|---|
| `documentar` | investigador | Reúne el material limpio, con su cita. Puede concluir que no hay material suficiente: entonces no se escribe y se propone fusionar, acortar o pedir una fuente nueva |
| `escaleta` | guionista | Promesa, tesis de cada bloque en una frase, pregunta que sostiene cada reenganche, material y palabras por bloque |
| `escribir` | guionista | Por bloques: varias intros de fórmulas distintas, desarrollo, bloque de conexión, cierre y una pasada de costuras |
| `verificar` | verificador | Cada afirmación trazada al material; lista de datos externos o contradictorios |
| `retencion` | retención | Solo intro, reenganches y cierre |
| `voz` | doble de voz | Crítica frase a frase contra el corpus |
| `describir` | guionista | Resumen y capítulos; los minutos los calcula el código |
| `cierre` | editor jefe | Coherencia del paquete entero y cumplimiento de las exclusiones |

Las correcciones de los críticos se aplican **por bloque**, no reescribiendo el guion. El guion lleva marcas internas
de cita que se quitan al exportar. El cierre no anuncia el final ni vende nada: enlaza con otro vídeo.

Cadena de puertas por defecto: `revision` (marketing) → `datos` → `revision-final` (presentador). Cada canal puede
cambiarla.

## 6. Puertas

- **Opciones**: aprobar, rehacer (con comentario) o rechazar (con comentario). Los revisores no editan el texto.
- **Papeles**: cada puerta declara qué papel decide; solo vale la decisión de una persona con ese papel.
- **Rondas**: cada rehacer cuenta; al superar el máximo, el tema se descarta. Tras rehacer, el paquete vuelve a la
  primera revisión y el mensaje muestra qué frases han cambiado.
- **Cambio mínimo**: al rehacer se aplica lo pedido y no se toca lo demás. Se admiten comentarios anclados a una frase.
- **Datos**: se verifican uno a uno (verificado, corregido, eliminado). Si alguno cambia, se ajustan solo sus frases,
  se marcan, y vuelve a la primera revisión sin contar ronda.
- **Notario**: firma, registra quién decidió qué y lanza lo siguiente. Aprobar es inmediato; rehacer y rechazar
  tienen una ventana para deshacer.
- **Aprendizaje**: cada comentario se convierte en una regla con su ejemplo; las valida una persona y caducan.

## 7. Revisión mecánica

Corre sobre cada artefacto antes de que llegue a una persona, y otra vez tras cada ajuste. Un aviso grave impide la
entrega: se corrige el bloque afectado una vez y, si persiste, queda como incidencia visible.

| Artefacto | Reglas |
|---|---|
| Todo | Exclusiones, nombres vetados, promesas no permitidas, emojis |
| Temas | Campos completos, cupo por pilar, material suficiente, parecido |
| Títulos | Longitud, corte en móvil, palabra clave al principio, clichés, palancas distintas |
| Miniaturas | Campos completos, texto breve sin palabras del título, tres ideas distintas en ángulo, concepto, composición y expresión |
| Guion | Rango de palabras; intro y promesa en sus límites; bloques presentes y dentro de su presupuesto; expresiones y cierres vetados; tratamiento; largo de frases; muletillas; repeticiones; cifras escritas como se leen; sin paréntesis, URL ni símbolos; aperturas, remates y analogías no repetidos respecto a guiones recientes |
| Datos | Toda cifra y nombre propio está en el material o en la lista de verificación |
| Descripción | Resumen y capítulos válidos (primero en 00:00, al menos tres, mínimo 10 segundos), palabra clave al principio |

La apertura recibe además una nota orientativa (concreción, apelación directa, lo que está en juego, curiosidad y
brevedad). Es un aviso, nunca un bloqueo.

## 8. Canales de trabajo

- **Correo**: cada puerta llega a quien tiene su papel, con el contenido completo, las frases numeradas y botones de
  respuesta con código de un solo uso. Una respuesta sin instrucción no cuenta. Un resumen diario agrupa lo
  pendiente. Las peticiones por correo son tres: nueva propuesta, tema propio y rehacer un vídeo.
- **Panel**: vídeos con su estado y su ronda, verificación de datos, lista de publicados y acciones (pedir propuesta,
  tema propio, marcar grabado o publicado, exportar).
- **Mensajería**: solo para quien administra.

Estados de un vídeo: elegido, título y miniatura elegidos, en revisión, en verificación de datos, en revisión final,
rehaciendo, aprobado, grabado, publicado o descartado; con un subestado visible cuando se está preparando o hay una
incidencia.

## 9. Métricas

Desde el primer día: reloj y coste por etapa, regla que falló, espera humana por puerta, aprobados a la primera por
cada papel, rondas y motivo, porcentaje de frases cambiadas por ronda y datos corregidos por guion.

## 10. Pruebas

Todo el núcleo se prueba sin IA ni red, con ejecutores y un Hermes de mentira: una prueba por regla de la revisión
mecánica, la cadena de puertas, los papeles, el tope de rondas, el correo y la API del panel. Una prueba impide que
aparezca el nombre de un canal real en skills y perfiles.

`local.sh` ejecuta una pipeline con Claude Code en una sola máquina, sin Hermes, para juzgar la calidad de los
guiones antes de instalar.

## 11. Fuera de alcance

Publicar, generar imágenes o vídeo, calendario de publicación, analítica de resultados, investigación de otros
canales y contenido para otras redes. Quedan anotados para más adelante: leer la curva de retención para aprender
dónde se va la audiencia, los comentarios como fuente de temas y la investigación de demanda como capacidad opcional.
