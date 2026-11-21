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

## La ventana principal

A la izquierda está la lista de **secciones**; a la derecha, la lista con el contenido de la sección elegida.

- Al moverse por las secciones con las flechas, la sección se muestra a la derecha, pero el foco **se queda en la lista de secciones**. Para entrar en el contenido pulse Tabulador, Intro o F6.
- F6 alterna entre las secciones y el contenido.
- Alt+1 a Alt+9 y Alt+0 van directamente a las diez primeras secciones (y ponen el foco en su contenido).
- El menú **Acciones** cambia según la sección y el elemento elegido; es el mismo menú que aparece con la tecla Aplicaciones o Mayúsculas+F10 sobre un elemento.

Secciones:

- **Inicio**: lo que hacen las personas y los repositorios que sigue.
- **Notificaciones**: Intro abre lo que la motivó (issue, pull request, Actions, release…) y la marca como leída. Control+L la marca como leída, Suprimir la marca como hecha, Control+Mayúsculas+S silencia la conversación y F4 cambia entre ver solo las no leídas o todas.
- **Mis repositorios**, **Repositorios con estrella** y **Repositorios vigilados**: Intro abre el repositorio, Control+K lo clona, Control+S pone o quita la estrella, Control+N crea un repositorio y F4 cambia el filtro.
- **Mis issues** y **Mis pull requests**: F4 elige qué ver (asignadas, creadas, menciones, revisión pedida…) y su estado.
- **Gists**, **Organizaciones**, **Proyectos**, **Codespaces**, **Seguidores** y **Personas que sigo**.
- **Repositorios locales**: carpetas de git de este equipo. Control+N añade una carpeta y Control+K clona un repositorio.
- **Resultados de la búsqueda**: los de la última búsqueda (Control+E).

### Notificaciones en segundo plano

La aplicación comprueba sola las notificaciones (cada minuto o lo que pida GitHub). Cuando llega alguna nueva la anuncia por voz y con un sonido, distinto si le mencionan o le piden una revisión. El número de no leídas aparece junto a la sección. Se configura en Preferencias, Notificaciones (también un aviso de Windows y la bandeja del sistema).

## Las listas

Todas las listas de la aplicación funcionan igual:

- Arriba y abajo: el lector lee la fila entera.
- Izquierda y derecha: recorren las columnas de la fila y las leen una a una. Control+1 a Control+9 leen directamente esa columna.
- Intro abre el elemento. Aplicaciones o Mayúsculas+F10 muestra todas sus acciones con sus teclas.
- F5 actualiza. Al llegar al final se cargan más elementos solos; Control+M los pide a mano.
- Control+F filtra la lista por un texto y Control+Mayúsculas+F quita el filtro.
- Control+C copia la fila, Control+Mayúsculas+C copia el enlace, Control+B abre el elemento en el navegador y Control+I muestra todos sus detalles en un texto que se puede leer con calma.

En Preferencias, Accesibilidad, se elige qué se dice al recorrer las columnas (número de fila, nombre de la columna y contenido). En Preferencias, «Columnas de las listas», se elige para cada lista qué columnas se ven y en qué orden: así decide qué lee el lector al moverse por las filas y en qué orden.

## Buscar en GitHub

Control+E abre la búsqueda. Elija qué buscar (repositorios, código, issues y pull requests, usuarios, commits, temas o etiquetas) y escriba el texto. Admite toda la sintaxis de GitHub; el botón «Ejemplos de calificadores» la explica.

Para repositorios hay además una **búsqueda guiada**: una categoría (populares con un mínimo de estrellas, más bifurcados, actualizados desde una fecha, sin actualizar desde una fecha, que piden ayuda, listas Awesome, o un tema como accesibilidad, lector de pantalla, inteligencia artificial, Arduino o Synology), el lenguaje y la licencia. El «Historial de búsquedas» guarda las últimas para repetirlas.

## Escribir textos: el editor

Las issues, comentarios, descripciones de pull requests, revisiones y notas de release se escriben en el mismo editor:

- El texto es Markdown. F7 muestra la vista previa con formato.
- Control+Intro envía. Si el envío falla, el editor no se cierra y el texto sigue ahí.
- Si cierra el editor sin enviar, le pregunta si quiere guardar lo escrito como **borrador**; al volver a escribir en el mismo sitio se lo ofrece.
- Tabulador escribe una tabulación en el texto; para pasar al siguiente control use Control+Tabulador.

## El visor de diferencias

Las diferencias de un commit, un pull request o un archivo local se muestran como una lista en la que cada línea es una fila con su tipo («Añadida», «Eliminada», «Sin cambios», «Bloque» o «Archivo»), su número de línea y su texto. Al llegar a una línea añadida o eliminada suena un sonido distinto.

- F8 y Mayúsculas+F8: siguiente y anterior grupo de cambios.
- Control+F8 y Control+Mayúsculas+F8: siguiente y anterior bloque.
- F7 y Mayúsculas+F7: siguiente y anterior archivo.
- Control+G: ir a una línea por su número.
- Control+T: ver todo como texto para leerlo seguido o copiarlo.
- Control+C: copiar la línea.
- En un pull request, Intro comenta la línea y Control+Intro lee los comentarios que ya tiene (las líneas comentadas tienen un sonido de aviso y una columna «Comentarios»).

## La ventana de un repositorio

Se abre con Intro sobre cualquier repositorio, con Control+O escribiendo «dueño/nombre» o un enlace, o desde una notificación. Igual que la principal, tiene a la izquierda las secciones y a la derecha su contenido (F6 alterna, Control+Tabulador cambia de sección, Control+W cierra; Escape no la cierra para no perder el sitio).

Secciones: Resumen (información y botón para leer el README con formato), Código (explorador de carpetas y archivos, con Retroceso para subir, F4 para cambiar de rama y Control+P para buscar un archivo), Issues, Pull requests, Discusiones, Actions, Releases, Ramas, Etiquetas, Commits, Proyectos, Hitos, Etiquetas de issues, Colaboradores, Bifurcaciones, Observadores, Seguridad, Entornos, Secretos y variables de Actions, Webhooks, Claves de despliegue, Reglas y protección, Estadísticas, Despliegues, Pages y Configuración.

En todas las listas de secciones: Intro abre, Control+N crea, F2 cambia o renombra, Suprimir borra (siempre pregunta antes) y F4 cambia el filtro (por ejemplo, issues abiertas, cerradas o todas, por etiqueta o asignado). Para borrar el repositorio entero hay que escribir su nombre, como en la web.

## Issues y pull requests

La ventana de una issue muestra arriba un resumen (título, estado, autor, etiquetas, asignados, hito, reacciones y fechas), después la **conversación** como lista (descripción, comentarios y eventos como «etiquetado» o «cerrado») y debajo el texto completo del elemento enfocado, que cambia al moverse sin quitar el foco de la lista. Desde la lista se comenta (Control+N), se responde citando (Control+R), se edita o borra un comentario propio, se reacciona (Control+E) y se ve con formato (Intro). Desde el menú Acciones: cerrar como completada o no planificada, reabrir, etiquetas, asignados, hito, bloquear, fijar, transferir y suscribirse.

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

## Releases, gists, discusiones y proyectos

- **Releases**: crear (con notas generadas automáticamente), editar, borrar, subir recursos y descargarlos con progreso.
- **Gists**: ver cada archivo, editarlo, añadir, renombrar o borrar archivos, comentarios, historial, estrella y bifurcar.
- **Discusiones**: comentarios con sus respuestas, marcar la respuesta, votar, cerrar y reabrir.
- **Proyectos**: los elementos como lista, con una columna por cada campo. «Mover a» (Control+M) cambia el estado sin arrastrar nada; F2 cambia cualquier campo; se pueden añadir borradores e issues, archivar, filtrar y agrupar.

## Git local

Desde «Repositorios locales» o con Control+Mayúsculas+G se abre la ventana de un repositorio de este equipo. Su zona de estado dice la rama, si va por delante o por detrás del remoto y cuántos cambios hay. Secciones:

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

- **General**: sección al abrir, voz al arrancar, bandeja del sistema, confirmar al salir, carpeta de descargas.
- **Actualizaciones**: buscar al arrancar y el origen (servidor del autor y GitHub, solo uno de ellos o una dirección personalizada).
- **Cuentas**: identificador de la aplicación OAuth y permisos que se piden.
- **Accesibilidad**: avisos por voz y braille, retardo, lectura por columnas, anuncio de las listas de casillas (estado, si va antes del texto, posición), columnas del visor de diferencias y sus sonidos, y formato HTML.
- **Sonidos**: activar, silenciar, volumen, paquete y una lista con cada evento para activar o desactivar su sonido, con un botón para probarlo.
- **Listas**: elementos por página y fechas relativas o completas.
- **Notificaciones**, **Git**, **Editor**, **Red y registro**.
- **Columnas de las listas**: columnas visibles y su orden en cada lista.

## Actualizaciones

La aplicación busca versiones nuevas al arrancar y una vez al día, y también desde Ayuda, «Buscar actualizaciones». Al encontrar una, muestra sus novedades y ofrece «Actualizar ahora», «Omitir esta versión» o «Más tarde». Cada versión va firmada: si el paquete no tiene la firma del autor, se rechaza. Antes de sustituir nada se hace una copia de seguridad, sus datos de `data` no se tocan y, si la versión nueva no arranca bien, se vuelve sola a la anterior.

## Problemas frecuentes

- **Una sección dice que hay que iniciar sesión**: inicie sesión con Control+Mayúsculas+L.
- **«La sesión no es válida o ha caducado»**: el token se revocó o caducó. Vuelva a iniciar sesión.
- **«La organización exige autorizar el token con su inicio de sesión único (SSO)»**: abra el enlace del mensaje y autorice el token para esa organización.
- **Se ha agotado el límite de peticiones**: el mensaje dice a qué hora se renueva. Herramientas, «Límite de uso de la API» muestra el detalle.
- **Git no está instalado**: instale Git for Windows o indique la ruta de `git.exe` en Preferencias, Git.
- **Algo falla**: Herramientas, «Generar un paquete de diagnóstico» crea un ZIP con los registros, sin tokens ni su nombre de usuario de Windows, para pedir ayuda.

## Datos y privacidad

Todo lo que la aplicación guarda está en su carpeta `data`: configuración (`config`), tokens cifrados (`config/secretos.dat`), borradores (`db`), registros (`logs`) y temporales (`temp`). No envía nada a nadie salvo a GitHub (y al servidor de actualizaciones para comprobar versiones). Los registros nunca contienen tokens.

## Autor y licencia

GitHub Accesible es obra de Héctor J. Benítez Corredera y se distribuye con licencia GPL versión 3. Si le resulta útil, puede invitar al autor a un café desde Ayuda, «Invítame a un café si te gusta mi trabajo».
