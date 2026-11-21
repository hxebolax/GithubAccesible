# Necesidades de las personas usuarias de un cliente de GitHub accesible

Investigación web realizada el 21 de noviembre de 2026 para la aplicación de escritorio (Python + wxPython, Windows, NVDA y JAWS, en español) que gestionará GitHub y git local.

## 1. Resumen

- La web de GitHub ha mejorado mucho (nueva vista «Files changed» por defecto desde enero de 2026, árbol de archivos con comportamiento de Explorador de Windows, comentarios multilínea con Mayúsculas+flechas desde septiembre de 2025), pero sigue dependiendo de cambiar entre modo exploración y modo foco, de tablas de diff, de regiones que cambian sin aviso y de muchos pasos con Tabulador.
- Las quejas que más se repiten son: revisar diffs y dejar comentarios por línea, saber qué líneas tienen comentarios, el foco que salta solo en listas (commits, proyectos, diálogos), listas sin semántica (no se puede saltar de un PR a otro), verbosidad (etiquetas leídas tres veces, tarjetas emergentes), Projects en vista tablero, logs de Actions largos y en directo, y orden de tabulación incorrecto al crear issues.
- La línea de órdenes (git y gh) funciona bien con lector de pantalla para lo básico (clonar, ramas, commit, push), y gh CLI incorporó en la versión 2.72.0 un modo accesible: preguntas sin redibujar la pantalla, indicador de progreso en texto en lugar de un spinner y colores ANSI de 4 bits. Lo que falla es la terminal MinTTY de Git Bash, los menús interactivos que redibujan, los spinners, los colores como única señal y la falta de una vista cómoda para diffs y revisiones.
- GitHub Desktop (Electron) ha corregido cosas (NVDA ya lee la lista de archivos cambiados, se anuncia el final del commit, marcas de verificación en el diff), pero siguen apareciendo fallos en el diálogo de conflictos de fusión, el foco al arrancar, los anuncios de posición en la lista de commits y los botones anidados.
- Las ideas que mejor funcionan en otras herramientas y conviene copiar: el visor de diff accesible de VS Code (F7, formato unificado, línea a línea) con señales sonoras distintas para línea añadida, eliminada o modificada; el árbol de archivos con escritura anticipada; atajos de una sola tecla que se pueden desactivar; anunciar el progreso con texto estable.
- Existe al menos un precedente directo: un front-end de GitHub en wxPython hecho por una persona ciega y comentado en AppleVis; los comentarios piden controles con etiqueta, que nada quede en silencio y aclarar qué dependencias necesita (git o gh).

## 2. Hallazgos por fuente

### 2.1 GitHub Community, categoría Accessibility

- Categoría general: https://github.com/orgs/community/discussions/categories/accessibility
  - Temas recientes vistos en la primera página: descripciones de etiquetas leídas tres veces por el lector (213004), desaparece el aviso «has comment» en la nueva vista de diff (212078), los botones «Comment», «Start a review» y «Reply» cambian de posición entre cajas (209652), no se puede navegar a encabezados dentro de elementos «details» cerrados en markdown (211160), atajos de respuestas guardadas que fallan la primera vez (77428), la web salta sola al final mientras se desplaza (210047), atajo punto que no abre el editor (211808).
- Comentarios multilínea para usuarios de lector de pantalla: https://github.com/orgs/community/discussions/7876
  - Petición de 2021: con ratón se seleccionan varias líneas del diff para un comentario o sugerencia, con teclado no se podía. GitHub lo dio por resuelto en septiembre de 2025 con Mayúsculas+flecha arriba/abajo en la nueva vista. Los usuarios siguen diciendo que revisar diffs fuera del modo foco es difícil y se quejan de que desapareció el atajo Ctrl+G para sugerencias.
  - Cita del equipo: «Our Accessibility team is actively working on this issue.»
- Aviso «has comment» perdido en la nueva vista de diff: https://github.com/orgs/community/discussions/212078
  - Antes, al recorrer el diff con flechas, NVDA anunciaba que una línea tenía comentario; ahora solo se descubre por casualidad pulsando Intro. Sin solución anunciada.
- Nueva vista de commits, el foco se mueve mal: https://github.com/orgs/community/discussions/78905
  - Con NVDA, al saltar por encabezados de nivel 4 el foco va al primer commit del día, NVDA pasa a modo foco y se releen botones. Se atribuye a JavaScript que cambia tabindex en contenedores. Seguía pasando en junio de 2025.
  - Cita: «The problem here is setting tabindex in the list.»
- Problemas con Projects: https://github.com/orgs/community/discussions/68005
  - Secciones del tablero sin encabezados, el foco sale del modal al cambiar un valor, desplegables que atrapan al usuario, sugerencias de búsqueda que no se pueden elegir. En 2024 GitHub añadió encabezados h2 y h3 a carriles y tarjetas; el resto quedó «en evaluación».
  - Cita: «The actual project view is not very screen reader friendly.»
- Queja genérica sobre falta de accesibilidad: https://github.com/orgs/community/discussions/113735
  - Solo enumera teclado, compatibilidad con lector de pantalla y contraste, sin detalles; el personal pidió casos concretos y se cerró sin respuesta. Poco útil, salvo para confirmar que esas tres áreas son la queja de fondo.
- Logs de Actions: en los resultados de búsqueda aparece un hilo (número 187331) sobre la dificultad de navegar logs e historial de ejecuciones y etiquetas incoherentes en controles de Actions, pero solo lo vi a través de un sitio secundario (devactivity.com); no lo pude verificar directamente. La guía Primer de GitHub cita las líneas de log que llegan en directo como un caso que requiere anuncios para tecnologías de apoyo: https://primer.style/accessibility/announcements

### 2.2 Guías oficiales de GitHub para lector de pantalla

- Pull requests con lector de pantalla: https://accessibility.github.com/documentation/guide/pull-requests
  - Pasos con NVDA: activar la vista previa «New Files Changed Experience», navegar por el árbol de archivos con flechas, filtrar archivos, recorrer la tabla del diff en modo foco, Ctrl+Alt+flechas entre bloques, Intro en una línea para comentar, Mayúsculas+flecha abajo para comentario multilínea, enviar revisión eligiendo Comentar, Aprobar o Solicitar cambios.
  - Limitaciones reconocidas: la lista de PR del repositorio no tiene semántica por elemento y no se puede saltar de un PR a otro; las tarjetas emergentes son verbosas; los botones de filtro no anuncian su estado; el lector no siempre cambia de modo solo.
- Repositorios con lector de pantalla: https://accessibility.github.com/documentation/guide/repos (vista en resultados; recomienda clonar desde símbolo del sistema o Git Bash).
- Atajos de teclado: https://docs.github.com/en/get-started/accessibility/keyboard-shortcuts
  - Notificaciones: E marcar como hecha, Mayúsculas+I leída, Mayúsculas+U no leída, Mayúsculas+M cancelar suscripción. Archivos: T buscador de archivos, L ir a línea, W cambiar rama, B blame. Issues: C crear, L etiquetas, A asignar, M hito. Los atajos de una sola letra se pueden desactivar en los ajustes de accesibilidad porque chocan con el lector.

### 2.3 Blog y changelog de accesibilidad de GitHub

- El próximo capítulo de accesibilidad: https://github.blog/open-source/building-githubs-next-chapter-in-accessibility/
  - Rediseño de «Files changed» con navegación por teclado coherente, puntos de referencia (landmarks), interlineado ajustable y menos recargas, por defecto desde enero de 2026; gh CLI con soporte de lector; Copilot CLI con modo lector de pantalla y menos anuncios redundantes; guía para git, gh y Copilot CLI con lector.
  - Cita: «screen reader users who lose their place when pages refresh».
- Nueva experiencia de archivos cambiados en vista previa: https://github.blog/changelog/2025-06-26-improved-pull-request-files-changed-experience-now-in-public-preview/ (vista en resultados: navegación coherente por teclado, landmarks, árbol redimensionable, filtros que afectan árbol y diff).
- Árbol de archivos accesible: https://github.blog/engineering/user-experience/considerations-for-making-a-tree-view-component-accessible/ (visto en resultados: árbol dentro de un landmark de navegación, tabindex itinerante, selección por escritura anticipada, comportamiento copiado del Explorador de Windows por ser la plataforma mayoritaria de usuarios de lector).
- Changelog de accesibilidad: https://github.blog/changelog/label/accessibility (índice; visto en resultados).

### 2.4 gh CLI

- Construyendo una gh CLI más accesible: https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/
  - Problemas: preguntas interactivas con símbolos y redibujados constantes que el lector no interpreta; spinner que redibuja caracteres braille; paleta de markdown que ignoraba el fondo y daba poco contraste. Cambios: nuevo sistema de preguntas basado en la biblioteca huh de Charm, indicador de progreso en texto («Working…» si no hay mensaje concreto), colores ANSI de 4 bits configurables desde la terminal. El artículo no habla del paginador y dice que estudian formatear tablas para que se lean mejor.
- Changelog de mayo de 2025: https://github.blog/changelog/2025-05-01-improved-accessibility-features-in-github-cli
  - Punto de entrada: ejecutar «gh a11y» (versión 2.72.0 o posterior). La página no da los nombres exactos de las opciones. Fuentes secundarias mencionan «gh config set accessible_prompter enabled», «gh config set spinner disabled» y variables como GH_ACCESSIBLE_PROMPTER y GH_SPINNER_DISABLED, pero con nombres contradictorios; hay que comprobarlo con «gh a11y» antes de usarlo.
- Informe de conformidad de gh CLI: https://accessibility.github.com/conformance/cli/ (visto en resultados, actualizado en marzo de 2026).
- Conclusión práctica para nuestra app: usar gh y git sin interacción (salida JSON con --json, sin paginador, sin color) y presentar todo en controles nativos de wxPython; nunca mostrar una terminal que redibuja.

### 2.5 GitHub Desktop

- Informe de conformidad de GitHub Desktop: https://accessibility.github.com/conformance/desktop-github-com
  - Al consultarlo, todas las filas aparecían como «Supports» sin observaciones, aunque el propio informe dice reflejar problemas de una auditoría. Los resultados de búsqueda citaban fallos que no vi en la página: no se anuncian mensajes de validación en la vista de cambios, ni la selección con Mayúsculas+flechas en el panel izquierdo del diff, pérdida de foco en el campo de coautores, tooltip no accesible por teclado en avisos de submódulos. Tómese como no verificado.
- Búsqueda de issues con «screen reader»: https://github.com/desktop/desktop/issues?q=is%3Aissue+%22screen+reader%22
  - 17048: NVDA no podía leer la lista de archivos cambiados (corregido en 2023). https://github.com/desktop/desktop/issues/17048
  - 22198: con lector, el botón «Resolve» del diálogo de conflictos de fusión no se activaba; otro colaborador vio que en el desplegable de opciones de resolución la flecha abajo sacaba el foco del menú con NVDA activo. Cerrado por falta de respuesta, sin arreglo. https://github.com/desktop/desktop/issues/22198
  - 19603: faltaban anuncios de posición en grupo («3 de 10») en la lista de commits (cerrado).
  - 20417: al arrancar, el cursor va a «Filtrar repositorios» y no al mensaje de commit (abierto).
  - 20443: la pista de longitud del commit no debería recibir el foco (cerrado).
  - 18514: botón dentro de un botón (abierto).
  - 6494: el icono «No newline at end of file» no se expone al lector (cerrado).
  - 17661: foco incoherente en diálogos de crear y renombrar rama en macOS (abierto).
- Búsqueda con etiqueta accessibility: https://github.com/desktop/desktop/issues?q=is%3Aissue+label%3Aaccessibility+screen+reader (mismos temas, 7 resultados).

### 2.6 git en Windows con lector de pantalla

- Hilo de git-for-windows: https://groups.google.com/g/git-for-windows/c/jgru0i0cDss
  - Un programador con discapacidad visual (NVDA, JAWS, Narrador) dice que «git commit» y otras órdenes no producen salida audible y no sabe cuántos archivos tiene preparados; usa GitHub Desktop y VS Code. El mantenedor sospecha de MinTTY (terminal de Git Bash), que no usa la consola de Windows y el lector no la interpreta.
- Incidencia de GitLab de un usuario ciego: https://gitlab.com/gitlab-org/gitlab/-/work_items/19073
  - Desde la línea de órdenes clona, cambia de rama, hace commit y push sin problema; en la web con JAWS el orden de tabulación para crear una issue es malo (15 tabulaciones) y comentar un rango de líneas exige seleccionar con ratón. Es de GitLab, pero los mismos problemas aparecen en GitHub.
  - Cita: «The tab order does not seem correct for making a new issue on a project.»
  - Nota: la página contenía instrucciones dirigidas a agentes automáticos que se ignoraron.

### 2.7 VS Code y Visual Studio como referencia

- Documentación de accesibilidad de VS Code: https://code.visualstudio.com/docs/configure/accessibility/accessibility
  - Visor de diff accesible con F7 y Mayúsculas+F7: diff unificado, flechas arriba/abajo recorren líneas sin cambios, insertadas y eliminadas, Intro vuelve al editor en esa línea (o la más cercana si estaba eliminada), Escape cierra. Vista accesible con Alt+F2 para leer carácter a carácter salidas, notificaciones, comentarios y terminal. F8 salta al siguiente error. Listas de señales sonoras y de anuncios configurables una a una.
- Notas de VS Code 1.74: https://code.visualstudio.com/updates/v1_74 (vistas en resultados: señal sonora distinta al ir a la siguiente diferencia según la línea sea insertada o eliminada). En 1.87 «audio cues» pasaron a llamarse «accessibility signals» (sonido y anuncio por separado) y en 1.88 funcionan en ambos lados del diff. Ajustes: accessibility.signals.diffLineInserted, diffLineDeleted y diffLineModified, con valores auto, on, off.
- Visual Studio también reproduce un sonido al llegar a una línea añadida o eliminada en la vista de diff: https://learn.microsoft.com/visualstudio/ide/reference/accessibility-tips-and-tricks (visto en resultados).

### 2.8 Herramientas de la comunidad

- AppleVis, hilo sobre un front-end de GitHub en wxPython hecho por una persona ciega (Windows, también funciona con VoiceOver en Mac): https://www.applevis.com/comment/190704
  - La página devolvió error 403; solo vi el resumen del buscador. Según ese resumen: los participantes dicen que la web de GitHub es tediosa con lector, la herramienta gestiona PR e issues y usa git normal (no requiere gh), y algunos controles estaban en silencio o sin etiqueta. Es el precedente más cercano a nuestra app y confirma la demanda.
- Precedente de Mudlet (cliente de MUD): https://www.github.com/Mudlet/Mudlet/issues/3342 (visto en resultados): recuerda que si un programa no se integra con el lector de pantalla y usa su propia voz, tiene que reimplementar todo; mejor usar controles nativos que el lector entienda.

### 2.9 Fuentes sin resultado

- nvda.groups.io: ninguna búsqueda devolvió hilos sobre git, GitHub Desktop o TortoiseGit.
- program-l (groups.io o freelists): sin resultados.
- forum.audiogames.net: sin hilos sobre git o GitHub; solo temas de juegos y Godot.
- Reddit (r/Blind, r/github, r/screenreaders): el buscador no devolvió ningún hilo.
- TortoiseGit con NVDA: sin información fiable.
- Blog personal de un programador ciego sobre terminal y navegador (mohamed-e-fayed.github.io): apareció en resultados pero la página dio error 404.

## 3. Problemas de accesibilidad principales que la app debe resolver

Lista priorizada. Cada punto incluye la propuesta concreta para la aplicación.

1. Leer y revisar diffs.
   - Problema: la tabla de diff exige modo foco, Ctrl+Alt+flechas, saber leer columnas; el color es la única pista en muchas vistas; se pierde el sitio al recargar.
   - Propuesta: vista de diff propia, línea a línea, en un control de texto o lista virtual. Cada línea se anuncia como «añadida», «eliminada» o «sin cambios» (palabra configurable o prefijo corto) seguido de su número de línea antiguo y nuevo y el texto. Atajos para siguiente o anterior bloque, siguiente o anterior archivo, siguiente cambio, siguiente comentario. Sonidos opcionales distintos para añadida, eliminada y modificada (como VS Code). Modo unificado por defecto y modo «lado a lado» leído como «antes» y «después» del mismo bloque. Resumen al abrir: «archivo X, 12 líneas añadidas, 3 eliminadas, 4 bloques».
2. Comentarios por línea y revisión de PR.
   - Problema: comentar un rango era imposible sin ratón hasta 2025; botones que cambian de sitio; no se anuncia que una línea tiene comentario.
   - Propuesta: en la vista de diff, Intro en una línea abre «Comentar línea»; Mayúsculas+flechas selecciona rango; casilla «Sugerir cambio» que rellena el bloque de sugerencia; botones siempre en el mismo orden («Añadir a la revisión», «Comentar ahora», «Cancelar»). Anunciar «tiene 2 comentarios» al llegar a la línea y permitir leerlos con una tecla. Diálogo «Enviar revisión» con resumen y opciones Comentar, Aprobar, Solicitar cambios. Lista de revisiones pendientes antes de enviar.
3. Conversaciones e hilos.
   - Problema: los hilos se recorren por encabezados, hay mucha verbosidad (tarjetas emergentes, etiquetas leídas tres veces), y markdown con secciones plegadas no navegables.
   - Propuesta: lista de comentarios en orden cronológico con autor, fecha relativa y estado (resuelto, desactualizado); el cuerpo se muestra en un visor de solo lectura con markdown convertido a texto con encabezados navegables; acciones «Responder», «Resolver hilo», «Reaccionar», «Citar», «Editar». Nada de tarjetas emergentes.
4. Contenido que cambia sin aviso y foco que salta.
   - Problema: la web recarga, reordena listas y mueve el foco (vista de commits, modales de Projects, foco al arrancar Desktop).
   - Propuesta: la app nunca mueve el foco sin acción del usuario; las actualizaciones automáticas se anuncian con un mensaje breve («3 notificaciones nuevas») y se aplican conservando el elemento seleccionado; opción para desactivar el refresco automático; al arrancar, el foco va a un lugar predecible y configurable.
5. Listas con semántica completa.
   - Problema: la lista de PR del repositorio no tiene semántica por elemento; faltan anuncios «3 de 10» en la lista de commits de Desktop.
   - Propuesta: todas las listas (PR, issues, commits, ramas, notificaciones, ejecuciones de Actions) en ListCtrl con columnas, anuncio de posición, orden de columnas leídas configurable, búsqueda incremental por letra y filtro con Ctrl+F.
6. Notificaciones legibles y marcables.
   - Problema: bandeja web con controles de estado poco claros; atajos E, Mayúsculas+I, Mayúsculas+U que chocan con el lector si no se desactivan.
   - Propuesta: bandeja de notificaciones nativa con columnas (repositorio, tipo, título, motivo, fecha, leída), atajos equivalentes sin depender del modo del lector (Supr marcar como hecha, Ctrl+I leída, Ctrl+U no leída, cancelar suscripción), filtros por motivo (mención, revisión solicitada, asignación) y aviso sonoro y de texto opcional al llegar nuevas.
7. Logs de GitHub Actions.
   - Problema: logs enormes, que llegan en directo, con grupos plegables y colores ANSI.
   - Propuesta: árbol ejecución, trabajo, paso con estado anunciado («fallido», «correcto», «en curso»); log del paso en visor de texto sin códigos de color; atajos «siguiente error», «siguiente advertencia», «siguiente grupo»; ir directamente al primer paso fallido; anuncio único al terminar la ejecución; volver a ejecutar trabajos fallidos.
8. Navegador de archivos del repositorio.
   - Propuesta: TreeCtrl nativo con escritura anticipada, tamaño y tipo, buscador de archivos (como la tecla T de la web), ver archivo con números de línea, blame e historial del archivo, cambiar de rama o etiqueta.
9. Edición de archivos y commit.
   - Problema: el editor web y el diálogo de commit de Desktop tienen pistas que roban el foco.
   - Propuesta: editor de texto plano con número de línea y columna en barra de estado (leíble con un atajo), commit con resumen y descripción separados, contador de caracteres solo bajo demanda, coautores, firma, «commit y push» en un paso.
10. Conflictos de fusión.
    - Problema: en Desktop el botón «Resolve» y el desplegable de opciones fallan con NVDA; en la web el editor de conflictos depende de marcas visuales.
    - Propuesta: lista de archivos en conflicto; para cada archivo, recorrer los bloques en conflicto uno a uno anunciando «conflicto 2 de 5», leer «versión actual», «versión entrante» y base, y elegir con botones o teclas: quedarse con la actual, con la entrante, con ambas, o editar a mano. Marcar el archivo como resuelto y continuar la fusión o el rebase.
11. Projects (tablero y tabla).
    - Propuesta: mostrar los proyectos como tabla de elementos con columnas de campos; el tablero se presenta como lista de columnas (estados) y dentro sus tarjetas; mover una tarjeta con un menú «Mover a…» en lugar de arrastrar; editar campos en un diálogo propio.
12. Anuncios de progreso y estado.
    - Problema: spinners y redibujados confunden al sintetizador.
    - Propuesta: barra de progreso nativa más un único anuncio de inicio y de fin («Clonando…», «Clonado completo»); progreso porcentual solo cuando se pide con un atajo; sonido opcional al terminar; errores en diálogo legible con el texto completo copiable.
13. Atajos de teclado y modos.
    - Problema: los atajos de una letra de la web chocan con el modo exploración del lector.
    - Propuesta: atajos con modificadores, coherentes en todas las ventanas, sin choques con los menús, documentados en una lista de teclas y en ayuda contextual; letras de acceso en todos los controles.
14. Verbosidad y etiquetas.
    - Problema: etiquetas leídas varias veces, botones dentro de botones, iconos sin texto («No newline at end of file»).
    - Propuesta: cada control con una sola etiqueta en español; iconos sustituidos por texto; nivel de detalle configurable (por ejemplo, leer o no las etiquetas y la fecha en las listas).
15. Uso de git y gh por debajo.
    - Problema: MinTTY silencioso, paginador, colores, menús interactivos.
    - Propuesta: invocar git y gh sin terminal, con GIT_PAGER y GH_PAGER vacíos, sin color, con salida JSON cuando exista, y mostrar los resultados en controles nativos; registro de órdenes ejecutadas consultable para quien quiera aprender la orden equivalente.

## 4. Funciones más pedidas, priorizadas

Prioridad alta

1. Visor de diff accesible línea a línea con tipo de línea y número de línea anunciados (alta).
2. Navegación por bloques, archivos y cambios dentro del diff con atajos (alta).
3. Sonidos opcionales para línea añadida, eliminada y modificada (alta).
4. Comentar una línea o un rango de líneas del diff desde el teclado (alta).
5. Anunciar qué líneas tienen comentarios y leerlos sin salir del diff (alta).
6. Revisión completa de PR: revisión pendiente, sugerencias de cambio, enviar Comentar, Aprobar o Solicitar cambios (alta).
7. Listas de PR e issues con columnas, filtros y posición anunciada (alta).
8. Leer y responder conversaciones de PR e issues, resolver hilos (alta).
9. Crear y editar issues y PR con formulario de orden lógico (título, cuerpo, etiquetas, responsables, hito, revisores) (alta).
10. Bandeja de notificaciones nativa con marcar como leída, no leída, hecha y cancelar suscripción (alta).
11. Estado de checks y logs de Actions con salto al paso fallido y al siguiente error (alta).
12. git local: estado, preparar y quitar archivos, commit, push, pull, fetch con mensajes de resultado claros (alta).
13. Ramas: crear, cambiar, renombrar, borrar, comparar, con foco coherente en los diálogos (alta).
14. Resolución de conflictos de fusión bloque a bloque (alta).
15. Foco estable y actualizaciones sin mover al usuario; anuncios breves de cambios (alta).
16. Progreso con texto y sonido, sin spinners (alta).

Prioridad media

17. Explorador de archivos del repositorio en árbol con escritura anticipada y buscador de archivos (media).
18. Ver archivo con números de línea, ir a línea, blame e historial del archivo (media).
19. Editar un archivo y hacer commit desde la app (media).
20. Historial de commits con detalle y diff de cada commit (media).
21. Fusionar PR (merge, squash, rebase), actualizar la rama, borrar la rama tras fusionar (media).
22. Projects en vista de tabla y tablero como listas, con «Mover a…» en lugar de arrastrar (media).
23. Visor de markdown legible: encabezados navegables, secciones plegadas accesibles, bloques de código (media).
24. Búsqueda global en GitHub (repositorios, código, issues, PR) con resultados en lista (media).
25. Volver a ejecutar flujos de trabajo y trabajos fallidos, ver artefactos (media).
26. Releases y etiquetas: crear, editar, subir archivos (media).
27. Atajos configurables y lista de teclas, sin atajos de una sola letra que choquen con el lector (media).
28. Nivel de detalle configurable de lo que se lee en listas y anuncios (media).
29. Clonar, crear y bifurcar repositorios con progreso anunciado (media).
30. Stash, cherry-pick, revert y rebase guiados con explicaciones (media).
31. Gestión de etiquetas, hitos y plantillas de issues (media).
32. Discusiones del repositorio (leer, responder, marcar respuesta) (media).

Prioridad baja

33. Integración con Copilot (resúmenes de PR, explicación de cambios) con salida en texto plano (baja).
34. Gists (baja).
35. Ajustes del repositorio: colaboradores, protección de ramas, secretos, webhooks (baja).
36. Codespaces: listar, crear, abrir (baja).
37. Gráficos e Insights presentados como datos tabulares en texto (baja).
38. Registro de órdenes git y gh equivalentes para aprender la línea de órdenes (baja).
39. Varias cuentas y GitHub Enterprise (baja).
40. Exportar un PR o una issue completa a texto o HTML para leerla sin conexión (baja).

## 5. Fuentes

Visitadas y leídas:

- https://accessibility.github.com/documentation/guide/pull-requests
- https://github.com/orgs/community/discussions/categories/accessibility
- https://github.com/orgs/community/discussions/7876
- https://github.com/orgs/community/discussions/212078
- https://github.com/orgs/community/discussions/78905
- https://github.com/orgs/community/discussions/68005
- https://github.com/orgs/community/discussions/113735
- https://github.blog/open-source/building-githubs-next-chapter-in-accessibility/
- https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/
- https://github.blog/changelog/2025-05-01-improved-accessibility-features-in-github-cli
- https://accessibility.github.com/conformance/desktop-github-com
- https://github.com/desktop/desktop/issues?q=is%3Aissue+%22screen+reader%22
- https://github.com/desktop/desktop/issues?q=is%3Aissue+label%3Aaccessibility+screen+reader
- https://github.com/desktop/desktop/issues/17048
- https://github.com/desktop/desktop/issues/22198
- https://groups.google.com/g/git-for-windows/c/jgru0i0cDss
- https://gitlab.com/gitlab-org/gitlab/-/work_items/19073
- https://code.visualstudio.com/docs/configure/accessibility/accessibility
- https://docs.github.com/en/get-started/accessibility/keyboard-shortcuts

Vistas solo en resultados de búsqueda (no abiertas o con error):

- https://accessibility.github.com/documentation/guide/repos
- https://accessibility.github.com/conformance/cli/
- https://github.blog/changelog/2025-06-26-improved-pull-request-files-changed-experience-now-in-public-preview/
- https://github.blog/engineering/user-experience/considerations-for-making-a-tree-view-component-accessible/
- https://github.blog/changelog/label/accessibility
- https://primer.style/accessibility/announcements
- https://code.visualstudio.com/updates/v1_74
- https://learn.microsoft.com/visualstudio/ide/reference/accessibility-tips-and-tricks
- https://www.applevis.com/comment/190704 (error 403)
- https://www.github.com/Mudlet/Mudlet/issues/3342
