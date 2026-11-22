# GitHub Accesible

[English version of this page](README.en.md)

Aplicación de escritorio para Windows con la que se maneja **GitHub entero y git local desde el teclado y con lector de pantalla** (NVDA, JAWS o Narrador). Está en español y en inglés (elige sola el idioma de Windows y se cambia en Preferencias), cada pantalla está pensada para escucharse bien y nada obliga a usar el ratón ni la web.

- Autor: Héctor J. Benítez Corredera.
- Licencia: GPL versión 3 (ver [LICENSE](LICENSE)).
- Descargas: [releases de GitHub](https://github.com/hxebolax/GithubAccesible/releases) y [servidor del autor](https://xebolax.synology.me/GithubAccesible/).

## Para quien usa la aplicación

### Qué es y por qué existe

La web de GitHub es usable con lector de pantalla, pero algunas tareas diarias son muy pesadas: leer las diferencias de un pull request, comentar una línea concreta, seguir el registro de una ejecución de Actions, resolver conflictos de fusión o mover tarjetas de un proyecto. GitHub Accesible convierte todo eso en listas nativas de Windows, con columnas que se pueden leer una a una, sonidos que indican lo que pasa y teclas para saltar justo a lo importante.

### Qué puede hacer

#### Cuentas e inicio de sesión

- Iniciar sesión **con el navegador y un código** (el más seguro: la contraseña, el doble factor o la llave de acceso se usan en la web, nunca en la aplicación).
- Iniciar sesión con un **token de acceso personal**, clásico o de grano fino, con botones que abren GitHub con los permisos ya marcados.
- **Importar la sesión de GitHub CLI** (`gh`) o las **credenciales de Git** si ya las tiene en el equipo.
- **Varias cuentas** a la vez y **GitHub Enterprise Server**. Los tokens se guardan cifrados con su usuario de Windows.

#### Ventana principal

Una lista de secciones a la izquierda y su contenido a la derecha:

- **Inicio**: actividad de las personas y repositorios que sigue.
- **Notificaciones**: abrir, marcar como leída o hecha, silenciar conversaciones. Se comprueban solas en segundo plano y se anuncian con voz y sonido (uno distinto si le mencionan o le piden una revisión).
- **Mis repositorios**, **Estrellas** y **Vigilados**: abrir, clonar, estrella, bifurcar, crear y borrar.
- **Mis issues** y **Mis pull requests**: asignados, creados, menciones, revisiones pedidas.
- **Gists**, **Organizaciones**, **Proyectos**, **Codespaces**, **Seguidores** y **Personas que sigo**.
- **Repositorios locales**: las carpetas de git de este equipo.
- **Búsqueda** en GitHub: repositorios, código, issues, usuarios, commits y temas, con toda la sintaxis de calificadores.

#### Ventana de cada repositorio

Resumen y README con formato, explorador de código, issues, pull requests, discusiones, GitHub Actions, releases, ramas, etiquetas, commits, proyectos, hitos, etiquetas de issues, colaboradores, bifurcaciones, observadores, seguridad (Dependabot, análisis de código y secretos), entornos, secretos y variables de Actions, webhooks, claves de despliegue, reglas y protección de ramas, estadísticas y tráfico, despliegues, GitHub Pages y configuración completa del repositorio.

#### Issues y pull requests

- Conversación completa en una lista (descripción, comentarios y eventos) con el texto íntegro del elemento enfocado.
- Comentar, responder citando, editar, reaccionar, cerrar, reabrir, etiquetas, asignados, hitos, bloquear y transferir.
- **Adjuntar archivos de texto** (registros `.log`, por ejemplo) a issues, pull requests, discusiones y comentarios: plegados dentro del texto o subidos a un gist secreto con su enlace.
- Pull requests con pestañas de conversación, commits, archivos cambiados, checks e hilos de revisión.
- **Revisión línea a línea**: Intro sobre una línea del diff la comenta; las líneas comentadas se marcan y se oyen; se puede aprobar, pedir cambios, resolver hilos y fusionar (fusión, squash o rebase).

#### Visor de diferencias

Cada línea es una fila con su tipo («Añadida», «Eliminada», «Sin cambios»), su número y su texto, con un sonido distinto para cada tipo. F8 salta al siguiente grupo de cambios, Control+F8 al siguiente bloque y F7 al siguiente archivo.

#### GitHub Actions

Ejecuciones, trabajos y pasos en listas; registro limpio (sin códigos de color ni marcas de tiempo) con F8 para saltar al siguiente error; anotaciones; volver a ejecutar, cancelar, aprobar despliegues, descargar artefactos y lanzar flujos con sus entradas. Sigue en vivo una ejecución y avisa al terminar.

#### Más de GitHub

Releases (crear con notas automáticas, subir y descargar recursos), gists, discusiones, proyectos (con «Mover a…» en lugar de arrastrar), perfiles, organizaciones y equipos, claves SSH y GPG (y generar una clave SSH nueva), estado de GitHub y límite de uso de la API.

#### Git local

Cambios con preparar y quitar, commit (también enmendar y firmar), historial con diferencias, ramas, etiquetas, stash, remotos, traer, tirar y enviar con progreso hablado, cherry-pick, revertir, restablecer, reflog, submódulos, worktrees, bisección guiada y **resolución de conflictos bloque a bloque** («su versión» o «la otra», también en reorganizaciones). Clonar con progreso y cancelación.

### Accesibilidad

- Controles nativos de Windows: el lector anuncia nombre, tipo y estado sin trucos.
- **Listas con lectura por columnas**: Izquierda y Derecha recorren las columnas; Control más un número lee una columna directamente. En Preferencias se elige si se dice el número de fila, el nombre de la columna y el contenido.
- **Columnas de cada lista configurables**: cuáles se ven y en qué orden (y así, qué y en qué orden lee el lector).
- **Listas de casillas** que anuncian su estado; se puede elegir decir el estado antes o después del texto y la posición.
- **El foco lo mueve usted**: moverse por las secciones o elegir en un desplegable cambia lo que se ve, pero el foco no salta a ninguna parte hasta que usted lo pide (Tabulador, Intro o F6).
- Ayuda de cualquier control con Control+H y manual completo con F1. En Preferencias se elige si el lector lee además esa explicación al llegar a botones y casillas, y en cada fila de las listas de casillas.
- Sonidos para cada evento, con volumen, paquetes y eventos que se pueden desactivar uno a uno.
- Historial de los avisos de voz para volver a escuchar lo que se dijo.
- README, manual y textos largos con formato HTML navegable por encabezados (o en texto plano si lo prefiere).
- La interfaz nunca se bloquea: todo lo que tarda va en segundo plano.

### Instalación

1. Descargue el último `GithubAccesible_vX.Y.Z.zip` de las releases o del servidor del autor.
2. Descomprímalo donde quiera (por ejemplo, en `Documentos` o en una memoria USB).
3. Ejecute `GithubAccesible.exe`.

Es **portable**: no se instala nada en el sistema y todo lo que la aplicación guarda (configuración, registros, sonidos propios) queda en su carpeta `data`. Para desinstalarla basta con borrar la carpeta. Para usar git local hace falta tener instalado [Git for Windows](https://git-scm.com).

### Actualizaciones

La aplicación busca versiones nuevas al arrancar y una vez al día (se puede desactivar). En **Preferencias, Actualizaciones** se elige el origen:

- Servidor del autor y, si no responde, GitHub (predeterminado).
- Solo el servidor del autor.
- Solo las releases de GitHub.
- Una dirección personalizada.

Cada versión va **firmada digitalmente**: la aplicación rechaza cualquier paquete que no lleve la firma del autor. Antes de sustituir nada se hace una copia de seguridad, nunca se tocan sus datos de `data` y, si la versión nueva no arranca bien, se vuelve sola a la anterior.

### Teclas principales

- F6: alternar entre la lista de secciones y su contenido.
- Alt+1 a Alt+9 y Alt+0: ir a cada sección.
- Intro: abrir el elemento. Aplicaciones o Mayúsculas+F10: sus acciones.
- F5: actualizar. Control+F: filtrar la lista. Control+B: abrir en el navegador. Control+I: detalles completos.
- Control+O: abrir un repositorio por nombre o enlace. Control+E: buscar en GitHub.
- Control+P: Preferencias. F1: manual. Mayúsculas+F1: lista completa de teclas.

La lista completa está en [docs/teclas.md](docs/teclas.md) y el manual en [docs/manual.md](docs/manual.md).

### Apoyar el proyecto

Si la aplicación le resulta útil, puede invitar al autor a un café desde el menú Ayuda, «Invítame a un café si te gusta mi trabajo».

## Para quien quiera compilarla o colaborar

### Requisitos

- Windows 10 u 11 de 64 bits.
- [Python 3.15](https://www.python.org) (el proyecto usa `py -3.15`).
- Git para Windows (para las pruebas de git local).

Dependencias principales: wxPython 4.3.2, requests, Markdown, cryptography y accessible_output2. De desarrollo: cx_Freeze 8.7, pytest, ruff, comtypes y PyNaCl.

### Entorno y tareas habituales

Todo se hace con `entorno.bat`, que tiene un menú accesible y también órdenes directas:

```
entorno.bat crear
entorno.bat ejecutar
entorno.bat pruebas
entorno.bat compilar
```

- `crear`: crea `.venv` con Python 3.15 e instala `requirements.txt` y `requirements-dev.txt`.
- `ejecutar`: lanza la aplicación desde el código.
- `pruebas`: ejecuta la batería de pytest.
- `compilar`: compila con cx_Freeze (con los runtimes de Visual C++ y `WebView2Loader.dll`), verifica que la compilación esté completa y limpia, y genera el ZIP y el `version.json`.

Sin el menú: `.venv\Scripts\python.exe -m pytest` y `.venv\Scripts\python.exe main.py --comprobar-arranque`.

### Publicar una versión

1. Cambie `APP_VERSION` en `app/core/version.py` (la única fuente de la versión) y `version` en `pyproject.toml`.
2. Añada sus novedades en `docs/changelog.md` y, traducidas, en `docs/en/changelog.md` (la misma versión en los dos).
3. Ejecute `.venv\Scripts\python.exe tools\publicar.py`. Compila, empaqueta, firma el `version.json` con la clave privada de `tools/claves/` (que nunca se sube al repositorio), copia el ZIP y el manifiesto a la carpeta sincronizada con el servidor y crea la release de GitHub con `gh`.

La clave privada de firma es imprescindible para publicar versiones que acepten las instalaciones existentes: guarde una copia fuera del equipo.

### Inicio de sesión con el navegador (aplicación OAuth)

El inicio «con el navegador y un código» necesita el Client ID de una aplicación OAuth con «Enable Device Flow» marcado. Es un dato público (no se usa secreto de cliente). Cómo registrarla, probarla desde Preferencias y dejarla fija en `ID_CLIENTE_OAUTH` está en [docs/oauth.md](docs/oauth.md).

### Estructura

- `main.py`: arranque en el orden correcto, con red de seguridad.
- `app/core`: rutas portables, versión, configuración, secretos cifrados (DPAPI), registro, tareas en segundo plano, traducción, contexto compartido.
- `app/services`: lógica sin interfaz. `github/` (cliente REST y GraphQL, autenticación, toda la API por áreas), `git_local.py`, `diferencias.py`, `conflictos.py`, `sonidos.py`, `formato.py`, `actualizador.py`.
- `app/ui`: interfaz. `accesibilidad/` (listas, casillas, diálogos, voz, teclado), `vistas/` (marco de listas y secciones), `repositorio/`, `detalle/` (issues, pull requests, diferencias, Actions, releases...), `git/`, `herramientas/`, preferencias, inicio de sesión.
- `tests`: pruebas de pytest, sin red y sin tocar el `data` real.
- `tools`: compilación, empaquetado, firma, publicación, traducciones y comprobación de teclas.
- `docs`: manual, lista de teclas y registro de cambios en español; `docs/en`, los mismos en inglés.
- `data/locales`: plantilla de traducción (`.pot`) y catálogo inglés (`en/LC_MESSAGES/githubaccesible.po` y `.mo`).
- `adjuntos`: investigación y repositorios de referencia usados durante el desarrollo (no se distribuye).

### Convenciones

- Código con tabulaciones y `ruff` (`.venv\Scripts\ruff.exe check .`).
- El español es el idioma principal y el inglés el secundario. El código, los comentarios y los registros están en español; todo texto que ve u oye la persona usuaria se marca con `_()` (o `N_()` en tablas) y se traduce en el catálogo inglés, y cada documento de `docs/` tiene su versión en `docs/en/`.
- Para traducir: `tools\extraer_cadenas.py`, `tools\actualizar_po.py`, traducir lo nuevo en `data/locales/en/LC_MESSAGES/githubaccesible.po` y `tools\compilar_traducciones.py`.
- Accesibilidad obligatoria: etiqueta creada antes de cada control, letras de acceso sin repetir en cada pantalla y en los dos idiomas (hay pruebas que lo revisan), botones en el idioma de la interfaz, nada que bloquee la interfaz.
- Ningún error se pierde: todo queda en `data/logs` con archivo, línea y traza, y los tokens se tapan en los registros.

### Licencia

GPL versión 3. Copyright (C) 2026 Héctor J. Benítez Corredera.
