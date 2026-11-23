# Manual de GitHub Accesible

GitHub Accesible es una aplicación para Windows con la que se maneja GitHub entero y git local desde el teclado y con lector de pantalla (NVDA, JAWS o Narrador). Este manual explica cómo empezar y cómo se usa cada parte. La lista completa de teclas está en «Lista de teclas» (Mayúsculas+F1).

## Primeros pasos

### Instalación

1. Descargue `GithubAccesible_vX.Y.Z.zip` de las releases de GitHub o del servidor del autor.
2. Descomprímalo en la carpeta que quiera.
3. Ejecute `GithubAccesible.exe`.

La aplicación es portable: todo lo que guarda queda en su carpeta `data`. Para desinstalarla, borre la carpeta. Para trabajar con repositorios locales necesita [Git for Windows](https://git-scm.com).

### Iniciar sesión

La primera vez la aplicación le pregunta si quiere iniciar sesión. También puede hacerlo desde Archivo, «Iniciar sesión con otra cuenta» (Control+Mayúsculas+L). Hay cuatro formas:

- **Con el navegador y un código** (recomendada). Pulse «Iniciar sesión»: la aplicación copia un código de 8 caracteres, se lo deletrea y abre la página de GitHub en su navegador. Pegue allí el código, pulse «Continue» y autorice la aplicación. La ventana se completa sola. Su contraseña, su doble factor o su llave de acceso se usan en la web, nunca en la aplicación.
- **Con un token de acceso personal**. Pegue el token en su campo. Si no tiene uno, los botones «Crear un token clásico en la web» y «Crear un token de grano fino» abren GitHub con los permisos ya marcados.
- **Importar la sesión de GitHub CLI**, si usa `gh` en este equipo.
- **Usar las credenciales guardadas de Git** (Git Credential Manager).

Para GitHub Enterprise Server escriba la dirección de su servidor en el campo «Servidor». Puede tener varias cuentas y cambiar entre ellas con Control+Mayúsculas+U. Los tokens se guardan cifrados con su usuario de Windows: si copia la carpeta a otro equipo, tendrá que volver a iniciar sesión.

El inicio con el navegador funciona sin configurar nada. Si el token que da GitHub caduca, la aplicación lo renueva sola. En GitHub Enterprise Server hay que registrar una aplicación OAuth en el propio servidor y escribir su identificador (Client ID) en Preferencias, Cuentas; los pasos están en [Activar el inicio de sesión con el navegador](https://github.com/hxebolax/GithubAccesible/blob/main/docs/oauth.md).

### Idioma

La aplicación está en español y en inglés. La primera vez que se abre usa el idioma de Windows: español si Windows está en cualquier variante de español (de España, de México, de Estados Unidos…) e inglés en cualquier otro caso. Se cambia en Preferencias, General, «Idioma de la interfaz»: «Automático (el idioma de Windows)», «Español» o «English». El idioma nuevo se aplica al reiniciar; la aplicación ofrece reiniciarla en ese momento.

El idioma elegido vale para todo: menús, mensajes, avisos por voz, este manual (F1), la lista de teclas y las novedades, tanto las que salen tras actualizar como las de la ventana «Actualización disponible».

## El foco lo mueve usted

En toda la aplicación, elegir algo no le cambia de sitio. Al moverse por una lista de secciones, al elegir en un desplegable (por ejemplo, «Buscar» en la búsqueda) o al cambiar unos botones de opción, lo que se ve a la derecha o debajo cambia al momento, pero el foco se queda en el control donde está. Usted decide cuándo ir al contenido: con Tabulador, con Intro en las listas de secciones o con F6.

El foco solo cambia cuando usted lo pide: al abrir algo (Intro, una tecla de una sección como Alt+1), al pulsar Aceptar con un dato que falta (va a ese campo para corregirlo) o al abrir una ventana nueva.

## La ventana principal

A la izquierda está la lista de **secciones**; a la derecha, la lista con el contenido de la sección elegida.

- Al moverse por las secciones con las flechas, la sección se muestra a la derecha, pero el foco **se queda en la lista de secciones**. Para entrar en el contenido pulse Tabulador, Intro o F6.
- Desde la lista de secciones también funcionan las teclas de la sección que no necesitan un elemento elegido: por ejemplo, Control+Mayúsculas+A marca todas las notificaciones como leídas y Control+N crea una issue nueva. Las que actúan sobre un elemento (Suprimir, F2…) solo funcionan dentro de la lista, donde se ve cuál está elegido; si se pulsan en las secciones, la aplicación lo explica.
- F6 alterna entre las secciones y el contenido.
- Alt+1 a Alt+9 y Alt+0 van directamente a las diez primeras secciones (y ponen el foco en su contenido).
- En Preferencias, **Secciones**, se ocultan las que no use y se ordenan como quiera, en esta ventana y en la de los repositorios; Alt más un número sigue ese orden.
- El menú **Acciones** cambia según la sección y el elemento elegido; es el mismo menú que aparece con la tecla Aplicaciones o Mayúsculas+F10 sobre un elemento.

Secciones:

- **Inicio**: lo que hacen las personas y los repositorios que sigue.
- **Notificaciones**: Intro abre lo que la motivó (issue, pull request, Actions, release…) y la marca como leída. Control+L la marca como leída, Suprimir la marca como hecha, Control+Mayúsculas+S silencia la conversación y F4 cambia entre ver solo las no leídas o todas.
- **Mis repositorios**, **Repositorios con estrella** y **Repositorios vigilados**: Intro abre el repositorio, Control+K lo clona, Control+S pone o quita la estrella, Control+N crea un repositorio y F4 cambia el filtro. En sus acciones también están «Descargar el código en zip», «Ver la wiki» y «Ver el propietario» (Control+Mayúsculas+P).
- **Mis issues** y **Mis pull requests**: F4 elige qué ver (asignadas, creadas, menciones, revisión pedida…) y su estado.
- **Gists**, **Organizaciones**, **Proyectos**, **Codespaces**, **Seguidores** y **Personas que sigo**.
- **Repositorios locales**: carpetas de git de este equipo. Control+N añade una carpeta y Control+K clona un repositorio.
- **Resultados de la búsqueda**: los de la última búsqueda (Control+E).

Control+U (ver un perfil) propone ya escrita la persona de la fila elegida: quien hizo la actividad, la persona de la lista, quien escribió la issue o el commit, o el dueño del repositorio. Pulse Intro para abrirlo o escriba otro nombre encima.

### Notificaciones en segundo plano

La aplicación comprueba sola las notificaciones (cada minuto o lo que pida GitHub). Cuando llega alguna nueva la anuncia por voz y con un sonido, distinto si le mencionan o le piden una revisión. El número de no leídas aparece junto a la sección. Se configura en Preferencias, Notificaciones (también un aviso de Windows y la bandeja del sistema).

En la sección Notificaciones, Control+L marca como leída la elegida y Control+Mayúsculas+A marca todas como leídas. Para oír las que hay sin leer desde cualquier programa, use la tecla global Control+Alt+Mayúsculas+N (ver «Teclas globales»).

Los avisos que llegan solos (notificaciones nuevas y el final de las ejecuciones de Actions vigiladas) los dice el lector de pantalla, que los corta en cuanto se pulsa una tecla. Si prefiere oírlos enteros mientras escribe, en Preferencias, Notificaciones, «Leer los avisos en segundo plano con», elija «Una voz SAPI 5 propia» y, si quiere, la voz, la velocidad y el volumen; «Probar la voz SAPI 5» le deja oírla antes de aceptar. Esa voz puede sonar a la vez que el lector. Lo que pide con el teclado (columnas, Control+H, Control+Alt+Mayúsculas+N) lo sigue diciendo el lector.

### La bandeja del sistema

La aplicación puede seguir funcionando con la ventana oculta, con un icono junto al reloj (Windows+B lleva a la bandeja; las flechas, al icono). Archivo, «Ocultar en la bandeja del sistema», la oculta. En Preferencias, General, se elige:

- **Minimizar a la bandeja del sistema**: al minimizar, se oculta en la bandeja.
- **Al cerrar la ventana, dejarla en la bandeja**: Alt+F4 o el botón Cerrar la ocultan en vez de salir. Para salir de verdad: Archivo, Salir (Control+Q) o «Salir» en el menú del icono.
- **Iniciar oculta en la bandeja**.
- **Icono en la bandeja todo el tiempo**: el icono se queda también con la ventana a la vista.

El texto del icono dice cuántas notificaciones hay sin leer. Intro o un clic muestran la ventana; la tecla Aplicaciones abre su menú: ocultar o mostrar la ventana, ir a las notificaciones, decir las no leídas, comprobar ahora, buscar en GitHub, Preferencias y Salir.

### Teclas globales

Funcionan desde cualquier programa, aunque la aplicación esté en la bandeja. De fábrica:

- **Control+Alt+Mayúsculas+G**: mostrar u ocultar la aplicación. Si está a la vista y delante, la oculta en la bandeja; si no, la trae al frente.
- **Control+Alt+Mayúsculas+N**: decir cuántas notificaciones hay sin leer y las tres más recientes, sin dejar lo que esté haciendo.

En Preferencias, **Teclas globales**, se cambian estas y se pueden activar otras tres: abrir la sección Notificaciones, buscar en GitHub y comprobar ahora si hay notificaciones nuevas. En cada campo se pulsa la combinación que se quiera (Control, Alt o Windows, y si quiere Mayúsculas, con una letra, un número o de F1 a F24) y el lector la dice; Retroceso o Suprimir la quitan. Si otro programa ya tiene una combinación, Windows no la deja usar: la aplicación lo dice al arrancar o al aplicar, para que elija otra. También se pueden desactivar todas.

### Paleta de órdenes

Control+Mayúsculas+O, en cualquier ventana, abre la **paleta de órdenes**: escriba parte del nombre de lo que quiere hacer («defecto», «wiki», «clonar») y la lista muestra las órdenes de esa ventana que lo contienen, con su tecla y su menú; también las acciones del elemento elegido en la lista. Intro ejecuta la orden. Sirve para encontrar cualquier cosa sin recorrer los menús y para aprender sus teclas.

## Las listas

Todas las listas de la aplicación funcionan igual:

- Arriba y abajo: el lector lee la fila entera.
- Izquierda y derecha: recorren las columnas de la fila y las leen una a una. Control+1 a Control+9 leen directamente esa columna.
- Intro abre el elemento. Aplicaciones o Mayúsculas+F10 muestra todas sus acciones con sus teclas.
- F5 actualiza. Al llegar al final se cargan más elementos solos; Control+M los pide a mano.
- Control+F filtra la lista por un texto y Control+Mayúsculas+F quita el filtro.
- Control+C copia la fila, Control+Mayúsculas+C copia el enlace, Control+B abre el elemento en el navegador y Control+I muestra todos sus detalles en un texto que se puede leer con calma.
- Control+J ordena la lista por la columna que se está leyendo: la primera vez de forma ascendente, la segunda descendente y la tercera vuelve al orden original, el que da GitHub. Control+Mayúsculas+J (o Acciones, «Ordenar por columna y sentido») elige la columna y el sentido de una lista. Con el ratón, basta pulsar la cabecera de la columna. Las fechas, los números y los tamaños se ordenan por su valor, no por el texto (en orden ascendente, «hace 3 días» va antes que «hace 5 minutos»), los números dentro del texto también («issue 2» antes que «issue 10») y lo que no tiene valor queda al final. El orden de cada lista se recuerda. Se ordena lo que ya está cargado: si la lista tiene más páginas, cárguelas antes con Control+M.

En Preferencias, Accesibilidad, se elige qué se dice al recorrer las columnas (número de fila, nombre de la columna y contenido). En Preferencias, «Columnas de las listas», se elige para cada lista qué columnas se ven y en qué orden: así decide qué lee el lector al moverse por las filas y en qué orden.

## Buscar en GitHub

Control+E abre la búsqueda. Elija qué buscar (repositorios, código, issues y pull requests, usuarios, commits, temas o etiquetas) y escriba el texto. Admite toda la sintaxis de GitHub; el botón «Ejemplos de calificadores» la explica.

Al cambiar lo que se busca, o al elegir una búsqueda del historial o de las guardadas, las pestañas de filtros cambian, pero el foco se queda en el desplegable: recórralas con Tabulador cuando quiera.

Para repositorios hay además una **búsqueda guiada**: una categoría (populares con un mínimo de estrellas, más bifurcados, actualizados desde una fecha, sin actualizar desde una fecha, que piden ayuda, listas Awesome, o un tema como accesibilidad, lector de pantalla, inteligencia artificial, Arduino o Synology), el lenguaje y la licencia. El «Historial de búsquedas» guarda las últimas para repetirlas.

En la lista de resultados, Aplicaciones (o Mayúsculas+F10) muestra lo que se puede hacer con cada uno según lo que sea:

- **Ver el propietario** (Control+Mayúsculas+P): abre el perfil de la persona u organización dueña del repositorio, con sus datos, sus repositorios, a quién sigue y el botón Seguir. Está en los repositorios y también en las issues, pull requests, código, commits y discusiones encontrados.
- **Ver al autor**: el perfil de quien escribió la issue, el pull request, la discusión o el commit.
- **Ir al repositorio** (Control+Mayúsculas+R): abre el repositorio al que pertenece una issue, un archivo de código, un commit o una discusión.
- En los repositorios, además: clonar (Control+K), poner o quitar la estrella (Control+S), vigilar y bifurcar.
- En las personas y organizaciones: **Seguir o dejar de seguir**, sin abrir el perfil.

## Escribir textos: el editor

Las issues, comentarios, descripciones de pull requests, revisiones y notas de release se escriben en el mismo editor:

- El texto es Markdown. F7 muestra la vista previa con formato.
- Control+Intro envía. Si el envío falla, el editor no se cierra y el texto sigue ahí.
- Si cierra el editor sin enviar, le pregunta si quiere guardar lo escrito como **borrador**; al volver a escribir en el mismo sitio se lo ofrece.
- Tabulador y Mayúsculas+Tabulador pasan al control siguiente o al anterior, como en el resto de Windows. Si prefiere que Tabulador escriba una tabulación en el texto, actívelo en Preferencias, Editor, «El tabulador escribe una tabulación en el texto Markdown»; entonces se pasa de control con Control+Tabulador.
- **Adjuntar archivo** (Alt+J), en issues, pull requests, discusiones y comentarios, añade archivos de texto, como un registro `.log` para enseñárselo a quien desarrolla. Se pueden elegir varios a la vez. Para cada uno pregunta cómo adjuntarlo:
  - **Dentro del texto, plegado**: el contenido va en un bloque de código que en GitHub se ve como el nombre del archivo y se despliega al pulsarlo. Se puede revisar y cambiar en el editor antes de enviar.
  - **Como gist secreto, con su enlace**: el archivo se sube a un gist que no sale en los listados y el texto lleva solo su enlace. Es la única opción si el archivo no cabe en el texto (GitHub admite 65 536 caracteres). Necesita el permiso «gist», que ya pide el inicio de sesión con el navegador.

  Antes de adjuntar un registro, revise que no lleve contraseñas, tokens ni datos personales: lo leerá cualquiera que vea la issue, y un gist secreto lo abre cualquiera que tenga el enlace. GitHub no deja subir imágenes ni otros archivos binarios desde aplicaciones, solo desde su web: envíe el texto y ábralo después en el navegador (Control+B) para arrastrar el archivo.

## El visor de diferencias

Las diferencias de un commit, un pull request o un archivo local se muestran como una lista en la que cada línea es una fila con su tipo («Añadida», «Eliminada», «Sin cambios», «Bloque» o «Archivo»), su número de línea y su texto. Al llegar a una línea añadida o eliminada suena un sonido distinto.

- F8 y Mayúsculas+F8: siguiente y anterior grupo de cambios.
- Control+F8 y Control+Mayúsculas+F8: siguiente y anterior bloque.
- F7 y Mayúsculas+F7: siguiente y anterior archivo.
- Control+G: ir a una línea por su número.
- Control+T: ver todo como texto para leerlo seguido o copiarlo.
- Control+C: copiar la línea.
- Control+D: dice qué ha cambiado dentro de la línea añadida o eliminada en la que está, comparándola con la línea a la que sustituye o que la sustituye («Cambia «timeout=30» por «timeout=60»», «Añade…», «Quita…» o «Línea reescrita»). Si no tiene pareja, lo dice.
- Control+Mayúsculas+D: resumen de las diferencias (archivos, cambios y líneas añadidas y eliminadas), el archivo en el que está (nuevo, borrado, renombrado o modificado) y el número de cambio. F8 y Mayúsculas+F8 dicen también «Cambio n de m».
- Control+Mayúsculas+T: las diferencias narradas, un texto que empieza por el resumen y recorre cada cambio con sus números de línea («Cambió la línea 12: … Por: …»).
- Los caracteres que no se ven (controles, espacios especiales, marcas que cambian la dirección del texto) se muestran con su nombre, como «<U+202E RIGHT-TO-LEFT OVERRIDE>», y al llegar a una línea que los tiene se avisa «Contiene caracteres invisibles». Pueden esconder código malicioso, por eso conviene saberlo.
- En un pull request, Intro comenta la línea y Control+Intro lee los comentarios que ya tiene (las líneas comentadas tienen un sonido de aviso y una columna «Comentarios»).

## La ventana de un repositorio

Se abre con Intro sobre cualquier repositorio, con Control+O escribiendo «dueño/nombre» o un enlace, o desde una notificación. Igual que la principal, tiene a la izquierda las secciones y a la derecha su contenido (F6 alterna, Control+Tabulador cambia de sección, Control+W cierra; Escape no la cierra para no perder el sitio).

Secciones: Resumen (información y botón para leer el README con formato), Código (explorador de carpetas y archivos, con Retroceso para subir, F4 para cambiar de rama y Control+P para buscar un archivo), Issues, Pull requests, Discusiones, Actions, Releases, Ramas, Etiquetas, Commits, Proyectos, Wiki, Hitos, Etiquetas de issues, Colaboradores, Bifurcaciones, Observadores, Seguridad, Entornos, Secretos y variables de Actions, Webhooks, Claves de despliegue, Reglas y protección, Estadísticas, Despliegues, Pages y Configuración.

En todas las listas de secciones: Intro abre, Control+N crea, F2 cambia o renombra, Suprimir borra (siempre pregunta antes) y F4 cambia el filtro (por ejemplo, issues abiertas, cerradas o todas, por etiqueta o asignado). Para borrar el repositorio entero hay que escribir su nombre, como en la web.

En el menú Repositorio, **Ver el propietario** (Control+Mayúsculas+P) abre el perfil de quien es dueño del repositorio, para ver sus otros repositorios o seguirle. **Descargar el código en zip** guarda la rama principal en un zip, diciendo cuánto lleva cada 10 MB. Si el repositorio es una bifurcación (fork), **Abrir el repositorio original** va al proyecto del que se copió y **Sincronizar con el original** trae a una rama suya lo nuevo del original, como el botón «Sync fork» de la web; en los demás repositorios esas dos órdenes aparecen como no disponibles.

En la sección Código, «Descargar el repositorio en zip» guarda el código de la rama elegida en un archivo zip sin necesidad de git.

### La wiki

La sección **Wiki** muestra las páginas de la wiki del repositorio: primero la portada (Home), luego las demás por orden alfabético y al final la barra lateral y el pie, si los tiene. GitHub no ofrece la wiki en su API: la aplicación la descarga con git (hace falta Git for Windows) en `data/cache/wikis` y la pone al día cada vez que entra en la sección o pulsa F5.

- Intro abre la página con formato en el visor. Los enlaces a otras páginas de la misma wiki se abren también en el visor; los demás, en el navegador.
- F2 edita la página en el editor (con vista previa y borradores) y Control+N crea una nueva, en Markdown o en otro de los formatos que admite GitHub. Cada cambio se guarda en GitHub en ese momento, con el mensaje que usted escriba o uno automático. Si no tiene permiso para editar la wiki, se avisa y no se cambia nada.
- «Cambiar el título» renombra la página y Suprimir la borra (pregunta antes; sigue en el historial).
- «Historial de la página» lista sus cambios: puede leer la página tal como quedó en cualquiera de ellos o ver sus diferencias en el visor de diferencias.
- Control+P busca un texto en todas las páginas y abre la elegida.
- Control+B abre la página en el navegador y Control+Mayúsculas+C copia su enlace.
- «Clonar la wiki en una carpeta» la descarga con git para trabajar con ella como con cualquier repositorio.

Si la wiki está desactivada, la etiqueta de la lista lo dice y las acciones ofrecen activarla (si el repositorio es suyo). Si está activada pero vacía, GitHub no la crea hasta guardar la primera página desde la web: use «Crear la primera página en el navegador» y luego F5.

## Issues y pull requests

La ventana de una issue muestra arriba un resumen (título, estado, autor, etiquetas, asignados, hito, reacciones y fechas), después la **conversación** como lista (descripción, comentarios y eventos como «etiquetado» o «cerrado») y debajo el texto completo del elemento enfocado, que cambia al moverse sin quitar el foco de la lista. Desde la lista se comenta (Control+N), se responde citando (Control+R), se edita o borra un comentario propio, se reacciona (Control+E) y se ve con formato (Intro). Desde el menú Acciones: cerrar como completada o no planificada, reabrir, etiquetas, asignados, hito, bloquear, fijar, transferir y suscribirse.

**Nueva issue** (Control+N en la sección Issues de un repositorio): si el repositorio tiene plantillas, se elige una de la lista, con su nombre y su descripción. «Issue en blanco» solo aparece si el repositorio lo permite, y sus enlaces de contacto (foros, avisos de seguridad) se abren en el navegador.

- Las plantillas de texto abren el editor con su título y su contenido.
- Los **formularios** piden cada dato en su propio campo: texto, texto largo, desplegable, lista de casillas o casillas. Los obligatorios dicen «(obligatorio)» y Control+H lee la explicación de cada campo. Control+Intro crea la issue y F7 muestra la vista previa; si falta algo obligatorio, se dice qué y el cursor va a ese campo. La issue queda igual que si se rellenara en la web.
- La issue se crea con las etiquetas, las personas asignadas y el tipo que indique la plantilla; si GitHub no los acepta por falta de permiso, se crea sin ellos y se avisa.

Al crear un **pull request** (desde el repositorio o desde la ventana de git), la descripción empieza con la plantilla del repositorio; si tiene varias, se elige una o ninguna.

La ventana de un pull request tiene pestañas (Control+Tabulador):

- **Conversación**: como en las issues.
- **Commits**: Intro abre las diferencias de cada commit.
- **Archivos cambiados**: los archivos y el visor de diferencias con todo el pull request. Intro sobre una línea la comenta; los comentarios se pueden guardar en una revisión pendiente y enviarla al final.
- **Checks**: el resultado de cada comprobación; Intro abre la ejecución de Actions.
- **Hilos de revisión**: resolver, reabrir, responder e ir a la línea.

«Revisar» (Alt+V) aprueba, pide cambios o comenta. «Fusionar» (Alt+F) permite fusión, squash o rebase y avisa si hay conflictos o faltan comprobaciones. También se puede activar la fusión automática, marcar como listo o como borrador, pedir revisión, actualizar la rama y hacer checkout en un repositorio local.

## Archivos, commits y blame

El visor de un archivo lo muestra en un campo de solo lectura: Control+G va a una línea, Control+L dice en qué línea está, Control+F busca y F3 repite. «Blame» muestra en una lista quién cambió cada línea y cuándo; «Historial», los commits del archivo. «Editar» (Control+E) abre el archivo para cambiarlo y guardarlo con un commit, en la misma rama o en una nueva (con la opción de abrir un pull request).

## GitHub Actions

La ventana de una ejecución muestra la información, la lista de **trabajos**, la de **pasos** del trabajo elegido y su **registro** limpio (sin códigos de color; las marcas de tiempo se pueden mostrar con una casilla). En el registro, F8 salta al siguiente error o aviso y lo lee. Intro sobre un paso lleva a su parte del registro. Hay listas de anotaciones y de artefactos (Intro descarga). Se puede volver a ejecutar todo o solo lo fallido (Control+R y Control+Mayúsculas+R), cancelar, aprobar despliegues y «Seguir en vivo»: mientras está en curso se actualiza cada 10 segundos, anuncia los cambios y suena al terminar con un sonido de éxito o de fallo.

«Lanzar flujo» (en la sección Actions del repositorio) lee las entradas del flujo y muestra un control para cada una.

### Vigilar ejecuciones en segundo plano

La aplicación puede avisarle cuando termine una ejecución aunque no tenga ninguna ventana abierta: dice el resultado («Actions de ana/proyecto: «CI» en main ha terminado: fallida»), suena el sonido de éxito o de fallo y, si quiere, muestra una notificación de Windows.

- En la sección Actions de un repositorio, «Avisarme cuando termine» (Control+Mayúsculas+W) sobre una ejecución en curso. También está en el menú Ejecución de su ventana.
- En el menú Repositorio, «Avisar al terminar cada ejecución de Actions» (casilla) vigila todas las de ese repositorio hasta que la desmarque.
- Al enviar cambios (push) a GitHub desde la ventana de git, se vigilan solas las ejecuciones que lance ese commit y se dice cómo han ido. Si el repositorio no tiene Actions, no se dice nada.
- Herramientas, «Ejecuciones de Actions vigiladas», muestra lo que se vigila y permite dejar de vigilarlo.

Lo vigilado se recuerda al cerrar la aplicación. El intervalo, la notificación de Windows y la vigilancia tras enviar se eligen en Preferencias, Actions.

## Releases, gists, discusiones y proyectos

- **Releases**: crear (con notas generadas automáticamente), editar, borrar, subir recursos y descargarlos con progreso. Al descargar un recurso, si GitHub publica su suma SHA-256, la aplicación la comprueba sola y dice si es correcta; si no coincide, avisa de que el archivo puede estar dañado. «Copiar la suma SHA-256» la copia para compartirla.
- **Gists**: ver cada archivo, editarlo, añadir, renombrar o borrar archivos, comentarios, historial, estrella y bifurcar.
- **Discusiones**: comentarios con sus respuestas, marcar la respuesta, votar, cerrar y reabrir.
- **Perfiles**: Control+U, «Ver el propietario» o «Ver al autor» abren el perfil de una persona. Tiene pestañas de Resumen (datos, fijados y contribuciones), Repositorios, Con estrella, Actividad (lo que ha hecho últimamente, como en Inicio), Seguidores, Seguidos, Gists y Organizaciones. El botón **Leer el README del perfil** (Alt+M) abre con formato la presentación que muestra la web. Si es una organización se abre su ventana propia.
- **Proyectos**: los elementos como lista, con una columna por cada campo. «Mover a» (Control+M) cambia el estado sin arrastrar nada; F2 cambia cualquier campo; se pueden añadir borradores e issues, archivar, filtrar y agrupar.

## Git local

Desde «Repositorios locales» o con Control+Mayúsculas+G se abre la ventana de un repositorio de este equipo. Su zona de estado dice la rama, si va por delante o por detrás del remoto y cuántos cambios hay. Como en las demás ventanas, moverse por la lista de secciones muestra cada una sin mover el foco; Intro, Tabulador o F6 entran en su contenido. Secciones:

- **Cambios**: archivos modificados; Espacio o Intro los prepara o los quita, Control+D muestra sus diferencias. Debajo está el mensaje del commit, con casillas para enmendar el último y firmar; Control+Intro confirma.
- **Historial**, **Ramas**, **Etiquetas**, **Stash**, **Remotos**, **Submódulos**, **Worktrees** y **Reflog**.
- **Conflictos**: tras una fusión o reorganización con conflictos, Intro sobre un archivo abre la resolución **bloque a bloque**: se lee cada bloque («Bloque 2 de 5. Su versión… La otra versión…») y se elige con un botón. En una reorganización los lados se invierten y la aplicación lo dice con claridad. Después se continúa o se aborta la operación.

El menú Git trae, tira, envía y sincroniza con progreso hablado (solo en los hitos para no saturar) y con Cancelar. Si el remoto es de GitHub, también abre el repositorio en la aplicación y crea pull requests.

## Herramientas

- **Claves SSH y GPG**: claves de la cuenta (añadir desde un archivo o pegándolas, borrar) y generar una clave SSH nueva y subirla.
- **Configuración de git**: nombre, correo, rama por defecto, fin de línea, reorganizar al tirar y firma.
- **Límite de uso de la API**, **Estado de GitHub**, **Historial de avisos de voz**, carpeta de registros y paquete de diagnóstico.

## Preferencias

Herramientas, Preferencias (Control+P). Los cambios se aplican al momento en las ventanas abiertas; Cancelar no guarda nada y «Restablecer valores de fábrica» vuelve a lo original.

- **General**: idioma de la interfaz, sección al abrir, voz al arrancar, bandeja del sistema (minimizar, cerrar, iniciar e icono permanente), confirmar al salir, carpeta de descargas.
- **Actualizaciones**: buscar al arrancar y el origen (servidor del autor y GitHub, solo uno de ellos o una dirección personalizada).
- **Cuentas**: identificador de la aplicación OAuth y permisos que se piden.
- **Accesibilidad**: avisos por voz y braille, retardo, lectura por columnas, anuncio de las listas de casillas (estado, si va antes del texto, posición), explicaciones que lee el lector, columnas del visor de diferencias y sus sonidos, y formato HTML.
  - **Explicaciones**: cada control tiene una explicación, la misma que dice Control+H. El lector de pantalla también puede leerla sola al llegar al control. «Explicaciones: leerlas al llegar a botones y casillas» (activada de fábrica) la lee en botones y casillas sueltas. «Explicaciones: leerlas también en cada fila de las listas de casillas» (desactivada de fábrica) la repite en cada fila de una lista de casillas, como «Buscar el texto en» de la búsqueda. Si la desactiva, al moverse por la lista solo oye cada fila y si está marcada. Control+H sigue diciendo la explicación siempre.
- **Sonidos**: activar, silenciar, volumen, paquete y una lista con cada evento para activar o desactivar su sonido, con un botón para probarlo.
- **Listas**: elementos por página y fechas relativas o completas.
- **Notificaciones** (también quién lee los avisos en segundo plano: el lector o una voz SAPI 5 con su voz, velocidad y volumen), **Teclas globales** (ver arriba), **Actions** (vigilancia de ejecuciones y hora en los registros), **Git**, **Editor** (confirmar al descartar, firma y si el tabulador escribe tabulaciones), **Red y registro**.
- **Columnas de las listas**: columnas visibles y su orden en cada lista.
- **Secciones**: para la ventana principal y para la de un repositorio, qué secciones se ven (casillas) y en qué orden (Subir y Bajar). «Resultados de la búsqueda» y «Resumen» no se pueden ocultar. Si abre una sección oculta desde otro sitio, se dice que está oculta.

## Actualizaciones

La aplicación busca versiones nuevas al arrancar y una vez al día, y también desde Ayuda, «Buscar actualizaciones». Al encontrar una, muestra sus novedades (las de todas las versiones posteriores a la que tiene, por si se saltó alguna) y ofrece «Actualizar ahora», «Omitir esta versión» o «Más tarde». Si el servidor no las da, lo dice y se verán al abrirse la versión nueva. Tras actualizar, la aplicación abre una sola vez las novedades: las de la versión nueva y, como mínimo, las de las tres anteriores. Cada versión va firmada: si el paquete no tiene la firma del autor, se rechaza. Antes de sustituir nada se hace una copia de seguridad, sus datos de `data` no se tocan y, si la versión nueva no arranca bien, se vuelve sola a la anterior.

## Problemas frecuentes

- **Una sección dice que hay que iniciar sesión**: inicie sesión con Control+Mayúsculas+L.
- **«La sesión no es válida o ha caducado»**: el token se revocó o caducó. Vuelva a iniciar sesión.
- **«La organización exige autorizar el token con su inicio de sesión único (SSO)»**: abra el enlace del mensaje y autorice el token para esa organización.
- **Se ha agotado el límite de peticiones**: el mensaje dice a qué hora se renueva. Herramientas, «Límite de uso de la API» muestra el detalle.
- **El lector repite una explicación larga en cada elemento**: desactive las explicaciones en Preferencias, Accesibilidad. Siempre podrá oírlas con Control+H.
- **No puedo adjuntar una imagen o un ZIP**: GitHub solo permite subirlos desde su web. Envíe el texto, ábralo en el navegador con Control+B y arrastre el archivo allí. Los archivos de texto sí se adjuntan desde el editor (Alt+J).
- **Git no está instalado**: instale Git for Windows o indique la ruta de `git.exe` en Preferencias, Git.
- **Algo falla**: Herramientas, «Generar un paquete de diagnóstico» crea un ZIP con los registros, sin tokens ni su nombre de usuario de Windows, para pedir ayuda.

## Datos y privacidad

Todo lo que la aplicación guarda está en su carpeta `data`: configuración (`config`), tokens cifrados (`config/secretos.dat`), borradores (`db`), registros (`logs`) y temporales (`temp`). No envía nada a nadie salvo a GitHub (y al servidor de actualizaciones para comprobar versiones). Los registros nunca contienen tokens.

## Autor y licencia

GitHub Accesible es obra de Héctor J. Benítez Corredera y se distribuye con licencia GPL versión 3. Si le resulta útil, puede invitar al autor a un café desde Ayuda, «Invítame a un café si te gusta mi trabajo».
