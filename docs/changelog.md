# Novedades de GitHub Accesible

Cada versión tiene su apartado, de la más reciente a la más antigua. Dentro de cada versión, los cambios se agrupan en Novedades, Mejoras y Correcciones, contados con palabras de quien usa la aplicación.

## Versión 1.0.13 - 2026-11-24

### Novedades

- **Gestor de descargas** (Control+Mayúsculas+D, Herramientas, «Descargas», o el menú de la bandeja). Todas las descargas (recursos de releases, artefactos y registros de Actions, código en zip) son de la aplicación: siguen aunque cierre la ventana que las pidió, y se pueden bajar varias a la vez mientras sigue trabajando.
  - Una lista con el estado, el progreso, lo descargado, la velocidad, el tiempo que queda, el origen, la carpeta y el error explicado si falla.
  - Pausar y reanudar donde se quedó (Espacio), reintentar las que fallan, cancelar (Suprimir), abrir el archivo (Intro) o su carpeta (Control+O), quitar las terminadas y pausar o reanudar todas.
  - Aviso y sonido al terminar o fallar cada una, con la ventana cerrada también. La suma SHA-256 de los recursos de una release se comprueba sola.
  - Si sale con descargas en curso, se pausan y siguen solas al volver a abrir la aplicación.
  - Preferencias, Descargas: cuántas a la vez, seguir al abrir y abrir la ventana al empezar una. Y una tecla global opcional para abrirla desde cualquier programa.

## Versión 1.0.12 - 2026-11-24

### Novedades

- **La actividad de un perfil ya no se queda en el último mes.** GitHub solo da los eventos de los últimos 30 días; al llegar al final de la lista, la aplicación sigue cargando, año a año y hasta el alta de la persona en GitHub, sus contribuciones anteriores: commits, issues y pull requests abiertos, revisiones y repositorios creados. Cada año gasta 1 punto de los 5.000 por hora que permite GitHub; se puede desactivar en Preferencias, Listas.

## Versión 1.0.11 - 2026-11-24

### Novedades

- **Seguidores** y **Personas que sigo** muestran los repositorios públicos, los seguidores, desde cuándo está cada persona en GitHub, sus contribuciones del último año y el enlace a su perfil.
- **Más columnas en las listas de repositorios** (Preferencias, «Columnas de las listas»): fecha de creación, tamaño, licencia, temas, sitio web, enlace, clonar por HTTPS y por SSH, observadores, última release y su permiso. «Mis repositorios» muestra de fábrica la fecha de creación. Control+I también da el permiso y la última release.

### Correcciones

- **«Mis issues» salía vacía** a quien abre issues en repositorios de otras personas. Ahora se buscan en todo GitHub y muestra de fábrica las creadas por usted; F4 cambia a asignadas, menciones, comentadas, todas en las que participa o las de sus repositorios.
- Control+I en un repositorio daba como observadores el número de estrellas.

## Versión 1.0.10 - 2026-11-23

### Novedades

- **Opciones generales para el aviso al terminar una ejecución de Actions** (Preferencias, Actions), que valen para todo lo vigilado a la vez: «Avisarme cuando termine», «Avisar al terminar cada ejecución de Actions» de cada repositorio y lo que lanza un push.
  - Sonido al terminar, sí o no.
  - Resultado por voz, sí o no (con el lector o con la voz SAPI 5).
  - De qué ejecuciones avisar: de todas, solo de las que fallan o solo de las que van bien.

## Versión 1.0.9 - 2026-11-23

### Novedades

- **Avisos con una voz SAPI 5 propia** (Preferencias, Notificaciones, «Leer los avisos en segundo plano con»). Las notificaciones nuevas y el final de las ejecuciones de Actions vigiladas los puede decir una voz de Windows aparte, que no se corta al pulsar teclas como el lector de pantalla. Se eligen la voz, la velocidad y el volumen, y se prueban antes de aceptar. De fábrica sigue diciéndolos el lector.
- **Las teclas de cada sección funcionan también desde la lista de secciones**, en la ventana principal y en la de un repositorio: por ejemplo, Control+Mayúsculas+A marca todas las notificaciones como leídas y Control+N crea una issue nueva sin entrar antes en la lista. Las que actúan sobre un elemento (Suprimir, F2…) siguen funcionando solo dentro de la lista, para no cambiar nada a ciegas.

### Mejoras

- En el texto Markdown de issues, pull requests y comentarios, **Tabulador y Mayúsculas+Tabulador pasan de control**, como en el resto de Windows. Quien prefiera que Tabulador escriba una tabulación lo activa en Preferencias, Editor.

## Versión 1.0.8 - 2026-11-23

### Novedades

- **Ordenar las listas por columnas**, en todas las listas de la aplicación. Control+J ordena por la columna que se está leyendo: ascendente, después descendente y después el orden original. Control+Mayúsculas+J (o Acciones, «Ordenar por columna y sentido») elige columna y sentido; con el ratón, la cabecera de la columna. Las fechas, los números y los tamaños se ordenan por su valor real, los números dentro del texto también («issue 2» antes que «issue 10») y lo que no tiene valor va al final. Cada lista recuerda su orden.
- **Marcar todas las notificaciones como leídas con Control+Mayúsculas+A** en la sección Notificaciones.

## Versión 1.0.7 - 2026-11-22

### Novedades

- **La aplicación, en inglés**. El español sigue siendo el idioma principal y el inglés es el segundo: toda la interfaz, los mensajes, los avisos por voz, el manual, la lista de teclas y las novedades están en los dos idiomas.
- **Idioma automático**: al abrirla, la aplicación usa el español si Windows está en cualquier variante de español (es-ES, es-MX, es-US…) y el inglés en cualquier otro idioma. Quien ya la tenía instalada pasa también al idioma de Windows.
- **Elegir el idioma** en Preferencias, General, «Idioma de la interfaz»: automático, español o inglés. Al cambiarlo, la aplicación ofrece reiniciarse para aplicarlo.
- **Documentación en su idioma**: F1 (manual), la lista de teclas y Ayuda, Novedades se abren en el idioma de la interfaz. Las novedades tras actualizar y las de la ventana «Actualización disponible» también; la página de cada versión en GitHub las trae en los dos idiomas.

### Mejoras

- Fechas, números y tamaños con el formato de cada idioma (en inglés, «Nov 22, 2026» y «1,234»).
- Las teclas globales y los atajos de los menús se dicen con los nombres de tecla del idioma elegido («Shift», «Del» o «Enter» en inglés).
- Algunos mensajes que se montaban por trozos se dicen ahora con frases completas, como «ana envió 1 commit» (antes «1 commits») y «creó la rama dev» (antes «creó branch dev»).

## Versión 1.0.6 - 2026-11-22

### Mejoras

- La ventana «Actualización disponible» ya muestra las novedades: las de todas las versiones posteriores a la instalada, por si se ha saltado alguna. Antes decía siempre que el servidor no había publicado novedades. Si alguna vez no las hay, ya no sale un cuadro vacío: se dice que se verán al abrirse la versión nueva.
- Las novedades que se abren solas tras actualizar incluyen siempre, además de la versión nueva, las de las tres anteriores: con esta versión, desde la 1.0.3. También las lleva la página de la versión en GitHub.

## Versión 1.0.5 - 2026-11-22

### Novedades

- **Bandeja del sistema configurable** (Preferencias, General): además de minimizar e iniciar en la bandeja, ahora se puede hacer que cerrar la ventana la deje en la bandeja en vez de salir, y que el icono esté siempre. El icono dice cuántas notificaciones hay sin leer y su menú permite ir a ellas, oírlas, comprobarlas, buscar y abrir Preferencias. Archivo tiene «Ocultar en la bandeja del sistema».
- **Teclas globales configurables**, que funcionan desde cualquier programa: Control+Alt+Mayúsculas+G muestra u oculta la aplicación y Control+Alt+Mayúsculas+N dice las notificaciones sin leer. En Preferencias, Teclas globales, se cambian pulsando la combinación que se quiera y se pueden activar otras tres (abrir Notificaciones, buscar y comprobar ahora). Si otro programa ya usa una, se avisa.
- **Secciones a su gusto** (Preferencias, Secciones): se ocultan las que no use y se ordenan, en la ventana principal y en la de los repositorios. Alt más un número sigue el orden elegido.
- **Paleta de órdenes** (Control+Mayúsculas+O en cualquier ventana): se escribe parte del nombre de lo que se quiere hacer y se ejecuta con Intro; dice la tecla y el menú de cada orden.
- **Vigilar ejecuciones de Actions en segundo plano**: «Avisarme cuando termine» en las ejecuciones en curso (Control+Mayúsculas+W), vigilar todas las de un repositorio desde su menú, y aviso automático del resultado de las ejecuciones que lanza un push hecho desde la aplicación. Avisa con voz, sonido y, si se quiere, una notificación de Windows. Herramientas, «Ejecuciones de Actions vigiladas», muestra lo vigilado.
- **Diferencias narradas** en el visor de diferencias: Control+D dice qué cambia dentro de una línea («Cambia «30» por «60»»), Control+Mayúsculas+D da el resumen, Control+Mayúsculas+T muestra las diferencias contadas como texto y F8 dice «Cambio n de m». Los caracteres invisibles o que cambian la dirección del texto se ven con su nombre y se avisan.
- **Formularios de issue**: los formularios del repositorio se rellenan en un cuadro accesible, con un campo por dato y los obligatorios marcados, y la issue queda igual que en la web. Las plantillas de texto conservan su título, etiquetas, asignados y tipo; se respetan «Issue en blanco» y los enlaces de contacto. Los pull requests empiezan con la plantilla del repositorio.

### Correcciones

- Control+U (ver un perfil) fallaba con una sección abierta en la ventana principal desde la versión 1.0.4.
- La ventana de una ejecución de Actions y el diálogo de actualización ya no dan el foco a controles de una ventana oculta.

## Versión 1.0.4 - 2026-11-22

### Novedades

- Nueva sección **Wiki** en la ventana de un repositorio. Lista las páginas (la portada primero), las abre con formato en el visor (los enlaces a otras páginas de la wiki se abren también ahí) y permite editarlas con F2, crear páginas con Control+N, cambiarles el título, borrarlas, ver el historial de cada una con sus versiones antiguas y diferencias, y buscar un texto en todas con Control+P. Si la wiki está desactivada o vacía, se dice y se ofrece activarla o crear la primera página en el navegador. GitHub no ofrece las wikis en su API: hace falta Git for Windows.
- En los resultados de una búsqueda, las acciones (Aplicaciones) permiten **ver el propietario** de cada resultado (Control+Mayúsculas+P) para abrir su perfil, ver sus repositorios o seguirle; ver al autor de una issue, pull request, discusión o commit; ir a su repositorio (Control+Mayúsculas+R); y, en los repositorios, clonar, poner la estrella, vigilar y bifurcar. En las personas encontradas se puede seguir o dejar de seguir sin abrir el perfil.
- En la ventana de un repositorio, el menú Repositorio tiene «Ver el propietario» (Control+Mayúsculas+P).
- «Descargar el código en zip» está ahora también en el menú Repositorio, en las listas de repositorios (míos, con estrella, vigilados y los de un perfil) y en los resultados de búsqueda, y dice cuánto lleva descargado.
- En una bifurcación (fork), el menú Repositorio permite abrir el repositorio original y sincronizar una rama con él, como el botón «Sync fork» de la web.
- Control+U (ver un perfil) propone la persona de la fila elegida: quien hizo la actividad, el autor de la issue o el commit, o el dueño del repositorio.
- El perfil de una persona tiene dos pestañas nuevas, Con estrella y Actividad, y el botón «Leer el README del perfil» (Alt+M) con la presentación que muestra la web.
- Al descargar un recurso de una release se comprueba la suma SHA-256 que publica GitHub y se dice si es correcta; también se puede copiar.
- En las listas de repositorios, «Ver la wiki» abre directamente esa sección.

### Correcciones

- «Descargar el repositorio en zip» daba el error 415 de GitHub («Unsupported 'Accept' header»). Ya descarga bien, igual que el zip de una etiqueta y el código que se baja al clonar sin git.
- En los menús de acciones de la ventana principal (repositorios, issues, pull requests, gists, organizaciones, proyectos, repositorios locales, codespaces y resultados de búsqueda) ya no hay dos órdenes con la misma letra de acceso. «Borrar el repositorio» se queda sin letra a propósito, para no borrarlo por accidente.

## Versión 1.0.3 - 2026-11-22

### Novedades

- Al escribir una issue, un pull request, una discusión o un comentario se pueden adjuntar archivos de texto, como un registro `.log`, con el botón «Adjuntar archivo» (Alt+J). El contenido va dentro del texto, en un bloque plegado con el nombre del archivo, o, si es muy largo, se sube a un gist secreto y el texto lleva su enlace. Lo pidió Slann Tonić en la primera issue del proyecto. GitHub no deja subir imágenes ni otros archivos binarios desde aplicaciones; para esos sigue haciendo falta su web.

## Versión 1.0.2 - 2026-11-21

### Mejoras

- Nuevas opciones en Preferencias, Accesibilidad, para elegir si el lector de pantalla lee la explicación de cada control al llegar a él: una para botones y casillas, y otra para cada fila de las listas de casillas. La de las filas viene desactivada: al moverse por una lista de casillas solo se oye cada fila y su estado. Control+H sigue diciendo la explicación siempre.
- En la ventana de un repositorio local, Intro en la lista de secciones entra en el contenido, como en la ventana principal.

### Correcciones

- En la búsqueda, cambiar lo que se busca (repositorios, issues, código…) o cargar una búsqueda del historial o de las guardadas ya no lleva el foco a la lista «Buscar el texto en»: se queda en el desplegable.
- En la ventana de un repositorio local, moverse por las secciones ya no mete el foco en la lista de la sección.
- En Preferencias, «Columnas de las listas», Subir y Bajar ya no llevan el foco a la lista: se queda en el botón para seguir moviendo.

## Versión 1.0.1 - 2026-11-21

### Novedades

- Ya se puede iniciar sesión con el navegador y un código sin configurar nada: la aplicación trae su propio identificador de GitHub.
- Si GitHub da un token que caduca, la aplicación lo renueva sola antes de que caduque o cuando GitHub lo rechaza, sin pedir otra vez el inicio de sesión.

### Correcciones

- El número de notificaciones de la lista de secciones («Notificaciones (2)») ya cambia en cuanto se marcan como leídas o hechas, o se actualiza la lista; antes se quedaba con el número antiguo.
- Tras cambiar algo en GitHub (marcar como leída, dar estrella, cerrar…), las listas ya no muestran datos antiguos guardados.
- Si el identificador de la aplicación OAuth está mal, se dice claramente en lugar de dar un error genérico.

## Versión 1.0.0 - 2026-11-21

### Novedades

- Primera versión publicada.
- Inicio de sesión con el navegador y un código, con token de acceso personal, importando la sesión de GitHub CLI o con las credenciales de Git. Varias cuentas y GitHub Enterprise Server.
- Ventana principal con Inicio, Notificaciones, Mis repositorios, Estrellas, Mis issues, Mis pull requests, Gists, Organizaciones, Proyectos, Repositorios locales, Vigilados, Seguidores, Personas que sigo, Codespaces y Búsqueda.
- Ventana de cada repositorio con todo: código, issues, pull requests, discusiones, Actions, releases, ramas, etiquetas, commits, proyectos, hitos, colaboradores, seguridad, secretos y variables, webhooks, reglas, estadísticas, Pages y configuración.
- Issues y pull requests con la conversación completa, revisión línea a línea, hilos, checks y fusión.
- Visor de diferencias accesible: tipo de línea, número, sonidos y saltos por cambios, bloques y archivos.
- GitHub Actions: ejecuciones, trabajos, pasos, registros limpios con salto a errores, artefactos y lanzar flujos.
- Git local completo: cambios, commits, historial, ramas, stash, etiquetas, remotos, conflictos bloque a bloque y clonar con progreso hablado.
- Notificaciones en segundo plano con voz, sonido y aviso de Windows opcional.
- Preferencias de accesibilidad: lectura por columnas, columnas visibles de cada lista, listas de casillas, sonidos por evento.
- Actualización automática firmada desde el servidor del autor, desde GitHub, desde ambos o desde una dirección personalizada.
