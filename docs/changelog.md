# Novedades de GitHub Accesible

Cada versión tiene su apartado, de la más reciente a la más antigua. Dentro de cada versión, los cambios se agrupan en Novedades, Mejoras y Correcciones, contados con palabras de quien usa la aplicación.

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
