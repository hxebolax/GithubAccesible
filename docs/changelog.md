# Novedades de GitHub Accesible

Cada versión tiene su apartado, de la más reciente a la más antigua. Dentro de cada versión, los cambios se agrupan en Novedades, Mejoras y Correcciones, contados con palabras de quien usa la aplicación.

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
