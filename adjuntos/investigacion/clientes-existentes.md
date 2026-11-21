# Clientes existentes de Git y GitHub: análisis para nuestra aplicación

Fecha de la investigación: 21 de noviembre de 2026.

Objetivo: reunir las funciones destacadas de los clientes de Git y GitHub más usados, su estado de accesibilidad con lectores de pantalla y las ideas que conviene copiar, para que nuestra aplicación (Python + wxPython, Windows, en español, accesible con NVDA y JAWS) no olvide nada.

Nota sobre las fuentes: al final de cada apartado se indican las fuentes consultadas. Cuando algo procede de conocimiento general y no de una fuente consultada en esta investigación, se indica con la marca «(conocimiento general, sin verificar en esta investigación)».

## 1. GitHub Desktop

### Funciones destacadas

- Añadir repositorio nuevo, añadir repositorio local existente, clonar desde GitHub o desde una URL, publicar un repositorio local en GitHub.
- Lista de repositorios con búsqueda rápida (Ctrl+T).
- Vista «Cambios»: lista de archivos modificados con casillas para incluir o excluir cada archivo del commit; selección de líneas o bloques concretos en el diff para hacer commits parciales; descartar cambios de archivos o de líneas.
- Campo de resumen y descripción del commit, coautores (Co-authored-by), y en versiones recientes ayuda para redactar el mensaje.
- Vista «Historial»: lista de commits de la rama, con el diff de cada commit.
- Ramas: crear (también desde un commit anterior), renombrar, eliminar, cambiar, comparar con otra rama, actualizar desde la rama por defecto, fusionar en la rama actual (incluido «squash and merge» y rebase de una rama sobre otra).
- Edición de historial por arrastrar y soltar: cherry-pick (desde la versión 2.7), squash y reordenar commits, enmendar el último commit (desde la versión 2.9), revertir commit, deshacer el último commit, restablecer a un commit.
- Etiquetas: crear etiqueta en un commit y borrar etiquetas locales no publicadas.
- Stash: guardar los cambios actuales en un stash y verlo o restaurarlo (un único stash visible por rama).
- Fetch, pull, push y push forzado cuando hace falta.
- Conflictos: lista de archivos en conflicto, opción de abrir en el editor externo o elegir «usar la versión mía / la suya», y abortar la fusión.
- Pull requests: ver la lista de PR del repositorio, hacer checkout de un PR, vista previa del PR antes de crearlo, abrir el PR actual en el navegador, estado de las comprobaciones (checks) con opción de volver a ejecutarlas, y notificaciones cuando un PR recibe revisiones o comentarios.
- Comportamiento con forks: preguntar si el fork se usa para contribuir al repositorio padre o para uso propio.
- Integración con editor externo y con la terminal preferida (configurables).
- Cuentas: GitHub.com y GitHub Enterprise.

### Atajos de teclado en Windows (lista oficial)

Generales de la aplicación:

- Ctrl+coma: abrir Opciones.
- F11: pantalla completa.
- Ctrl+0, Ctrl+igual, Ctrl+guion: restablecer, aumentar y reducir el zoom.
- Ctrl+8 y Ctrl+9: estrechar y ensanchar el panel activo.
- Ctrl+Mayús+I: herramientas de desarrollo.

Repositorios:

- Ctrl+N: nuevo repositorio.
- Ctrl+O: añadir repositorio local.
- Ctrl+Mayús+O: clonar repositorio.
- Ctrl+T: lista de repositorios.
- Ctrl+P: push.
- Ctrl+Mayús+P: pull.
- Ctrl+Suprimir: quitar repositorio de la lista.
- Ctrl+Mayús+G: ver el repositorio en GitHub.
- Ctrl+acento grave: abrir en la terminal.
- Ctrl+Mayús+F: mostrar en el Explorador.
- Ctrl+Mayús+A: abrir en el editor.
- Ctrl+I: crear una issue en GitHub.

Ramas:

- Ctrl+1: vista de cambios.
- Ctrl+2: vista de historial.
- Ctrl+B: lista de ramas.
- Ctrl+G: ir al campo de resumen del commit.
- Ctrl+Intro: hacer commit desde el resumen o la descripción.
- Espacio: marcar o desmarcar los archivos seleccionados.
- Ctrl+Mayús+N: nueva rama.
- Ctrl+Mayús+R: renombrar la rama actual.
- Ctrl+Mayús+D: eliminar la rama actual.
- Ctrl+Mayús+U: actualizar desde la rama por defecto.
- Ctrl+Mayús+B: comparar con otra rama.
- Ctrl+Mayús+M: fusionar en la rama actual.
- Ctrl+Mayús+S: guardar los cambios en stash.
- Ctrl+H: mostrar u ocultar los cambios guardados en stash.
- Ctrl+Mayús+C: comparar ramas en GitHub.
- Ctrl+R: ver el pull request actual en GitHub.

Idea: estos atajos son conocidos por muchas personas; conviene reutilizar los que no choquen con NVDA, JAWS ni con nuestros menús (por ejemplo Ctrl+1 y Ctrl+2 para cambiar de vista, Ctrl+G para ir al mensaje del commit, Ctrl+Intro para confirmar el commit, Ctrl+P y Ctrl+Mayús+P para push y pull).

### Estado de accesibilidad

- Es una aplicación Electron (web). GitHub ha ido corrigiendo problemas con NVDA: la versión 3.2.3 hizo que NVDA anuncie el número de sugerencias de autocompletado; la 3.3 dio el rol de alerta a los mensajes de error de los diálogos; la 3.4.4 hizo que se anuncien los encabezados de los diálogos «Abrir un pull request» y «Acerca de».
- El informe de conformidad (ACR) de GitHub Desktop, actualizado el 8 de septiembre de 2026, marca todos los criterios WCAG 2.2 A y AA como «Supports», sin incidencias abiertas. Versiones anteriores del informe (2024) listaban problemas: no se anunciaba el mensaje de selección al seleccionar varios archivos con Mayús+flechas, no se anunciaba el resultado resaltado del cuadro de búsqueda y el control deslizante del diff de imágenes no era alcanzable con el teclado.
- Puntos débiles conocidos por su diseño: muchas operaciones de edición de historial dependen de arrastrar y soltar (hay alternativas en menús contextuales para algunas, no para todas); el diff es una vista web que se lee mejor con el modo exploración que con el modo foco.

### Lo que no hace (límites que nuestra app debe superar)

- No tiene rebase interactivo completo: sólo squash, reordenar y enmendar; no permite editar un commit intermedio, descartarlo (drop), hacer fixup con autosquash ni dividir commits.
- Un solo stash visible por rama; no hay lista de stashes ni stash parcial.
- No muestra blame, ni historial de un archivo concreto, ni grafo de ramas, ni búsqueda en el historial por contenido.
- No gestiona remotos múltiples (más allá de origin y upstream de forks), ni submódulos, ni worktrees, ni Git LFS más allá de lo básico.
- No permite revisar PR (comentarios en líneas, aprobar, pedir cambios), ni gestionar issues, Actions, releases, gists, proyectos, discusiones, organizaciones ni ajustes del repositorio; todo eso lo envía al navegador.
- No firma commits con interfaz propia ni gestiona claves SSH o GPG.
- (Lista de límites basada en conocimiento general, sin verificar punto por punto en esta investigación.)

### Ideas a copiar

- Casillas por archivo y por línea para preparar el commit; Espacio para marcar.
- Vista previa del PR antes de crearlo.
- Preguntar el propósito de un fork.
- Proteger operaciones peligrosas con confirmación y ofrecer «deshacer el último commit».
- Avisos (notificaciones) cuando un PR propio recibe revisión.

Fuentes:

- https://docs.github.com/en/desktop/overview/github-desktop-keyboard-shortcuts
- https://accessibility.github.com/conformance/desktop-github-com
- https://github.blog/changelog/2024-09-10-github-desktop-3-4-4-introducing-custom-editor-and-shell-integration
- https://github.blog/news-insights/product-news/github-desktop-2-9-squashing-reordering-amending/
- https://docs.github.com/en/enterprise-server@3.16/desktop/managing-commits/options-for-managing-commits-in-github-desktop
- https://github.blog/changelog/2023-05-03-github-desktop-makes-force-pushing-and-fetching-easy-and-adds-pull-request-comment-notifications

## 2. GitHub CLI (gh)

Versión analizada: gh 2.100.0 (2026-09-03), instalada en C:\Program Files\GitHub CLI\gh.exe. La lista se ha obtenido con `gh help`, `gh help reference` y `gh <comando> --help`, sin ejecutar nada que use la red.

### Opciones transversales importantes para nuestra app

- Casi todos los comandos de listado y vista aceptan `--json campos`, `--jq expresión` y `--template plantilla`: es la forma fiable de leer datos para mostrarlos en nuestras listas.
- `-R` o `--repo [HOST/]PROPIETARIO/REPO` permite actuar sobre otro repositorio sin estar en su carpeta.
- `--web` abre el elemento en el navegador en muchos comandos.
- Ayuda de accesibilidad propia (`gh help accessibility`): `gh config set accessible_prompter enabled` (preguntas no interactivas con listas numeradas), `gh config set spinner disabled` (progreso en texto en lugar de animación), `gh config set accessible_colors enabled` (paleta de 4 bits de alto contraste) y `gh config set color_labels enabled`.

### Comandos principales (CORE COMMANDS)

gh auth: autenticación de gh y de git.

- login: iniciar sesión en una cuenta.
- logout: cerrar sesión.
- refresh: renovar credenciales o añadir permisos (scopes).
- setup-git: configurar git para usar gh como gestor de credenciales.
- status: cuenta activa y estado de autenticación en cada host.
- switch: cambiar de cuenta activa (multi-cuenta).
- token: mostrar el token que usa gh.

gh browse: abrir en el navegador el repositorio, una issue o PR por número, una ruta, un commit, la rama, la vista blame, Actions, proyectos, releases, ajustes o wiki; con `--no-browser` sólo imprime la URL.

gh codespace: gestionar codespaces.

- code: abrir en Visual Studio Code.
- cp: copiar archivos entre local y remoto.
- create, delete, edit, list, view: crear, borrar, editar, listar y ver.
- jupyter: abrir en JupyterLab.
- logs: ver registros.
- ports: listar y reenviar puertos.
- rebuild: reconstruir.
- ssh: conectarse por SSH.
- stop: detener.

gh discussion (preview): discusiones de GitHub.

- create, edit, list, view: crear, editar, listar y ver.
- comment: añadir, editar o borrar un comentario o una respuesta.

gh gist: gists.

- clone, create, delete, edit, list, rename (renombrar un archivo del gist), view.

gh issue: issues.

- create, list, status (issues relevantes para mí), view.
- close, reopen, delete.
- comment: comentar.
- edit: editar una o varias issues (título, cuerpo, etiquetas, asignados, hito, proyectos).
- develop: gestionar ramas vinculadas a una issue (crear rama para trabajar en ella).
- lock, unlock: bloquear o desbloquear la conversación.
- pin, unpin: fijar o desfijar.
- transfer: transferir a otro repositorio.

gh org: organizaciones.

- list: listar mis organizaciones (no hay más subcomandos: equipos y miembros sólo vía `gh api`).

gh pr: pull requests.

- create, list, status, view.
- checkout: traer el PR a una rama local.
- checks: estado de CI de un PR.
- close, reopen.
- comment: comentar.
- diff: ver los cambios.
- edit: título, cuerpo, rama base, etiquetas, revisores, asignados, hito, proyectos.
- lock, unlock.
- merge: fusionar con `--merge`, `--squash` o `--rebase`; `--auto` (fusión automática al cumplir requisitos), `--disable-auto`, `--admin`, `--delete-branch`, `--subject`, `--body`, `--match-head-commit`.
- ready: marcar como listo para revisión (o volver a borrador con `--undo`).
- revert: revertir un PR fusionado.
- review: revisar con `--approve`, `--request-changes` o `--comment` y un cuerpo; no permite comentarios en líneas concretas (eso requiere `gh api`).
- update-branch: actualizar la rama del PR con la base.

gh project: GitHub Projects (versión nueva).

- close, copy, create, delete, edit, list, view, mark-template.
- field-create, field-delete, field-list: campos.
- item-add, item-archive, item-create (borrador), item-delete, item-edit, item-list: elementos.
- link, unlink: vincular a un repositorio o equipo.

gh release: releases.

- create, list, view, edit, delete.
- upload, download, delete-asset: archivos adjuntos (assets).
- verify, verify-asset: verificar atestaciones de una release o de un archivo.

gh repo: repositorios.

- create, list, view, clone, fork, delete, rename.
- archive, unarchive.
- edit: ajustes (descripción, página web, temas, visibilidad, rama por defecto, issues, wiki, proyectos, discusiones, tipos de fusión permitidos, borrar rama al fusionar, auto-merge, plantilla, seguridad avanzada, escaneo de secretos y protección de push).
- set-default: repositorio por defecto para la carpeta.
- sync: sincronizar un fork o una rama local con su origen.
- autolink: create, delete, list, view (referencias automáticas).
- deploy-key: add, delete, list (claves de despliegue).
- gitignore: list, view (plantillas .gitignore).
- license: list, view (licencias).
- read-dir y read-file (preview): leer carpetas y archivos remotos sin clonar.

gh skill (preview): habilidades de agentes: install, list, preview, publish, search, update.

### Comandos de GitHub Actions

gh cache: list, delete (cachés de Actions).

gh run: ejecuciones de flujos.

- list, view (resumen, trabajos, registros con `--log` o `--log-failed`).
- watch: seguir una ejecución hasta que termine.
- rerun: volver a ejecutar (todo o sólo lo fallido).
- cancel, delete.
- download: descargar artefactos.

gh workflow: flujos de trabajo.

- list, view.
- run: lanzar un flujo con evento workflow_dispatch y sus parámetros.
- enable, disable.

### Comandos adicionales

- gh agent-task (preview): create, list, view (tareas del agente de Copilot).
- gh alias: delete, import, list, set (atajos de comandos; existe el alias predefinido `gh co` para `pr checkout`).
- gh api: petición autenticada a la API REST o GraphQL; cubre todo lo que no tiene comando propio.
- gh attestation: download, trusted-root, verify (atestaciones de artefactos).
- gh completion: scripts de autocompletado para la shell.
- gh config: clear-cache, get, list, set (por ejemplo editor, protocolo git, navegador, opciones de accesibilidad).
- gh copilot (preview): ejecuta la CLI de GitHub Copilot (la descarga si no está).
- gh extension: browse, create, exec, install, list, remove, search, upgrade.
- gh gpg-key: add, delete, list.
- gh label: clone (copiar etiquetas de otro repositorio), create, delete, edit, list.
- gh licenses: licencias de terceros de gh.
- gh preview: prompter (probar el sistema de preguntas).
- gh ruleset: check (reglas que aplican a una rama), list, view (sólo lectura).
- gh search: code, commits, issues, prs, repos.
- gh secret: delete, list, set (secretos de repositorio, entorno, organización, Dependabot o Codespaces).
- gh ssh-key: add, delete, list.
- gh status: resumen entre repositorios de issues y PR asignados, revisiones pedidas, menciones y actividad.
- gh variable: delete, get, list, set (variables de Actions).

Temas de ayuda: accessibility, actions, environment, exit-codes, formatting, mintty, reference, telemetry.

### Lo que gh no cubre con comandos propios (habrá que usar la API)

- Bandeja de notificaciones completa (marcar como leída, suscribirse, guardar): sólo `gh status` da un resumen.
- Equipos, miembros e invitaciones de organizaciones; colaboradores del repositorio.
- Comentarios de revisión en líneas concretas, sugerencias de cambio y resolución de hilos de revisión.
- Protección de ramas clásica y creación o edición de rulesets (gh ruleset es sólo lectura).
- Webhooks, entornos de despliegue, GitHub Pages, wiki.
- Alertas de Dependabot, code scanning y secret scanning.
- Estrellas, seguir usuarios, vigilar (watch) repositorios, patrocinios, paquetes.
- Hitos (milestones) como recurso propio.
- (Esta lista se deduce de los comandos disponibles en la versión 2.100.0.)

### Accesibilidad

- GitHub publicó en mayo de 2025 mejoras de accesibilidad para gh: preguntas no interactivas, progreso en texto y colores de alto contraste. Lecciones de su artículo: evitar redibujar la pantalla, describir el progreso con texto concreto («Clonando…»), respetar los colores del usuario, que la estructura de la salida sea deducible y que el formato de tablas sea configurable.
- La guía oficial para lectores de pantalla recomienda Windows Terminal (o la consola de Windows en lugar de MinTTY), el modo marca (Ctrl+Mayús+M) para revisar la salida, copiar el código de un solo uso antes de pulsar Intro al iniciar sesión, y redactar los comentarios largos de revisión en un archivo.
- Problema típico: NVDA no lee la salida de git en MinTTY (Git Bash por defecto).

### Ideas a copiar

- Usar gh (o la API) como motor y presentar su salida JSON en listas accesibles.
- Cuenta activa visible y cambio de cuenta (como `gh auth switch`).
- Un «estado» global estilo `gh status` como pantalla de inicio.
- Comandos de seguimiento en vivo (`gh run watch`) traducidos a avisos hablados.

Fuentes:

- Ayuda local de gh 2.100.0 (`gh help`, `gh help reference`, `gh help accessibility`).
- https://cli.github.com/manual
- https://github.blog/changelog/2025-05-01-improved-accessibility-features-in-github-cli
- https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/
- https://accessibility.github.com/documentation/guide/cli/
- https://groups.google.com/g/git-for-windows/c/jgru0i0cDss

## 3. GitKraken Desktop

### Funciones destacadas

- Grafo de commits muy visual, con varias ramas y remotos.
- Paleta de comandos para ejecutar cualquier acción con el teclado y una referencia de atajos para Windows, macOS y Linux.
- Rebase interactivo visual, arrastrar y soltar ramas para fusionar o hacer rebase, deshacer y rehacer.
- Editor de conflictos integrado, staging por líneas y bloques.
- Integración con GitHub, GitLab, Bitbucket y Azure DevOps: PR, issues, varios perfiles y cuentas.
- Workspaces con varios repositorios, Git LFS, submódulos, Git Flow, firmas GPG.
- (Las funciones de rebase, conflictos, integraciones y perfiles proceden de conocimiento general, sin verificar en esta investigación.)

### Accesibilidad

- No se ha encontrado documentación, informe VPAT ni notas de versión sobre NVDA, JAWS o ARIA. Es una aplicación Electron centrada en un grafo dibujado; previsiblemente difícil con lector de pantalla.
- Sí tiene atajos y paleta de comandos; una nota antigua corrige la navegación con teclado en la lista de archivos del panel de commit.

### Ideas a copiar

- Paleta de comandos (buscar cualquier acción por nombre): muy útil con lector de pantalla.
- Perfiles para separar cuentas (trabajo y personal).
- Deshacer y rehacer operaciones.

Fuentes:

- https://help.gitkraken.com/gitkraken-desktop/11x/
- https://help.gitkraken.com/start-here/tips/

## 4. Fork

### Funciones destacadas

- Notificaciones de GitHub discretas.
- Ayudante de conflictos y herramienta de resolución integrada.
- Rebase interactivo visual: editar, reordenar y hacer squash.
- Diff de imágenes y visor de diff avanzado.
- Historial de un archivo o carpeta y blame por línea.
- Staging y unstaging línea a línea.
- Explorar el árbol de archivos en cualquier commit.
- Recuperar commits perdidos con el reflog.
- Stashes visibles en la lista de commits.
- Git Flow, Git LFS, GPG, submódulos, cherry-pick, revert, merge, rebase, etiquetas.
- Gestor de repositorios con recientes.

### Accesibilidad

- No se ha encontrado información sobre lectores de pantalla. En Windows usa controles propios dibujados (conocimiento general, sin verificar).

### Ideas a copiar

- Explorar el repositorio en un commit concreto.
- Recuperación desde el reflog con interfaz.
- Historial de archivo y blame como funciones de primera clase.

Fuente: https://git-fork.com/

## 5. Sourcetree (Atlassian)

### Funciones destacadas (conocimiento general, sin verificar en esta investigación)

- Gratuito, Windows y macOS; grafo de ramas.
- Staging por bloques y líneas, rebase interactivo (con reordenar, squash, editar mensaje y borrar), stashes múltiples, cherry-pick, etiquetas.
- Git Flow y Hg Flow integrados, Git LFS, submódulos.
- Varias cuentas de hospedaje (Bitbucket, GitHub, GitLab) y creación de PR en Bitbucket.
- Acciones personalizadas (ejecutar scripts sobre el repositorio).

### Accesibilidad

- No se ha encontrado información específica. En la práctica es poco usable con lector de pantalla (conocimiento general, sin verificar).

### Ideas a copiar

- Acciones personalizadas definidas por la persona usuaria.
- Ayuda guiada para Git Flow.

## 6. TortoiseGit

### Funciones destacadas (conocimiento general, sin verificar en esta investigación)

- Se integra en el menú contextual del Explorador de Windows: commit, pull, push, log, diff, blame, rebase, stash, bisect, submódulos, etiquetas, ramas, revisiones de reflog.
- Iconos superpuestos que indican el estado de cada archivo.
- Diálogos clásicos de Windows (Win32/MFC), lo que en principio favorece a los lectores de pantalla.
- TortoiseGitMerge para conflictos, rebase interactivo en diálogo, ventana de log con filtros, envío de parches por correo.

### Accesibilidad

- No se han encontrado informes sobre TortoiseGit con NVDA. En su proyecto hermano TortoiseSVN hubo informes: NVDA leía los botones y el título de un diálogo pero no el texto del mensaje (2011), y los campos de texto basados en Scintilla no eran accesibles para JAWS (2019). TortoiseGit usa componentes parecidos, por lo que pueden existir los mismos problemas.

### Ideas a copiar

- Integración con el menú contextual del Explorador (opcional en nuestra app: «Abrir con GitHub Accesible»).
- Diálogos nativos de Windows y controles estándar, en lugar de controles dibujados.
- Evitar Scintilla o editores sin soporte de accesibilidad en los campos de mensaje.

Fuentes:

- https://svn.haxx.se/tsvnusers/archive-2011-04/0209.shtml
- https://groups.google.com/g/tortoisesvn/c/UiDX_B7xPds/m/IwMU9_oJAAAJ

## 7. lazygit (interfaz de texto en terminal)

### Funciones destacadas

- Staging de bloques completos o de líneas y rangos de líneas.
- Rebase interactivo sin editar el archivo TODO a mano: squash, fixup, drop, edit y reordenar.
- Cherry-pick copiando y pegando commits.
- Bisect marcando commits buenos o malos.
- Parches personalizados: extraer parte de un commit antiguo a un commit nuevo o aplicarla al revés.
- Quitar un bloque de un commit antiguo.
- Enmendar un commit antiguo con los cambios preparados (no sólo el último).
- Restablecer el árbol de trabajo, incluidos submódulos.
- Worktrees.
- Rebase desde un commit base marcado.
- Deshacer y rehacer usando el reflog.
- Filtro de búsqueda en cualquier vista.
- Grafo de commits, comparar dos commits o ramas.
- Comandos y atajos personalizados.
- Estado de PR de GitHub junto a las ramas (usa gh).

### Accesibilidad

- Es una interfaz de terminal que redibuja la pantalla constantemente; con NVDA es poco práctica (conocimiento general, sin verificar en esta investigación). Sus funciones sí son una excelente referencia.

### Ideas a copiar

- Rebase interactivo como lista editable: mover arriba y abajo, cambiar la acción de cada commit (pick, squash, fixup, drop, edit, reword).
- Enmendar cualquier commit, no sólo el último.
- Parches personalizados y división de commits.
- Deshacer global basado en el reflog.
- Filtro rápido en todas las listas.

Fuente: https://github.com/jesseduffield/lazygit

## 8. Sublime Merge

### Funciones destacadas

- Paleta de comandos.
- Staging por líneas y bloques, incluso dividiendo bloques.
- Búsqueda instantánea en el repositorio por mensaje, autor, ruta o contenido.
- Blame e historial de archivo.
- Herramienta de fusión integrada para conflictos.
- Diff lado a lado con resaltado por caracteres y contexto ampliable.
- Edición de commits, submódulos, Git Flow.
- Muestra los comandos git que ejecuta (integración con la línea de comandos).

### Accesibilidad

- No se ha encontrado información. Usa su propio motor de interfaz dibujado (como Sublime Text), que en general no expone información a los lectores de pantalla (conocimiento general, sin verificar).

### Ideas a copiar

- Mostrar (o registrar) el comando git exacto que se ejecuta: ayuda a aprender y a depurar.
- Búsqueda en historial por mensaje, autor, ruta y contenido.

Fuente: https://www.sublimemerge.com/

## 9. Git Extensions

### Funciones destacadas (conocimiento general, sin verificar en esta investigación)

- Cliente libre para Windows hecho en .NET WinForms; grafo de commits, explorador de archivos por commit, blame, historial de archivo.
- Rebase interactivo, cherry-pick, bisect, stash múltiple, submódulos, worktrees, gestión de remotos, Git LFS.
- Scripts personalizados y complementos (plugins), integración con GitHub (fork, PR) mediante plugin.
- Atajos de teclado configurables.

### Accesibilidad

- No se ha encontrado información específica. Al usar WinForms con controles estándar en parte de la interfaz, podría ser más legible que los clientes Electron, pero el grafo es un control dibujado (sin verificar).

### Ideas a copiar

- Atajos totalmente configurables.
- Sistema de scripts o complementos.

## 10. Visual Studio Code (control de código fuente) y extensión GitHub Pull Requests

### Control de código fuente integrado (conocimiento general salvo lo indicado)

- Vista de cambios con preparados y no preparados, staging de rangos seleccionados, commit, enmendar, deshacer último commit, stash, ramas, etiquetas, remotos, sincronizar, grafo de historial, timeline de archivo, editor de fusión de 3 vías para conflictos.

### Extensión GitHub Pull Requests and Issues

- Iniciar sesión en GitHub.com, GHE.com y GitHub Enterprise Server.
- Listar y explorar PR con consultas personalizables.
- Revisar PR con comentarios dentro del editor.
- Checkout de PR para validarlos.
- Listar issues con consultas personalizables.
- Tarjetas emergentes de usuarios e issues mencionados; autocompletado de @usuarios e #issues.
- Empezar a trabajar en una issue (crea una rama).
- Crear issues a partir de comentarios TODO.

### Accesibilidad

- VS Code se prueba con NVDA y JAWS. Para NVDA recomiendan quedarse en modo foco y usar atajos.
- Visor de diff accesible (Accessible Diff Viewer): F7 y Mayús+F7 van al cambio siguiente o anterior y muestran el diff en formato unificado navegable por líneas; Intro vuelve al editor en esa línea; Escape lo cierra.
- Hay ayuda de accesibilidad contextual (Alt+F1) y señales sonoras (por ejemplo, al llegar a una línea añadida, borrada o con conflicto) (conocimiento general, sin verificar en esta investigación).
- Problema conocido: al moverse entre diferencias con Alt+F5, el lector no leía la línea automáticamente.

### Ideas a copiar

- Visor de diff accesible: un cambio por elemento, anuncio de «línea añadida / borrada / sin cambios» con número de línea, saltar al bloque siguiente o anterior con una tecla.
- Señales sonoras opcionales para línea añadida, borrada, conflicto, error y éxito.
- Ayuda de accesibilidad contextual de cada vista.
- Empezar a trabajar en una issue creando la rama.

Fuentes:

- https://code.visualstudio.com/docs/configure/accessibility/accessibility
- https://code.visualstudio.com/updates/v1_81
- https://github.com/microsoft/vscode-pull-request-github
- https://accessibility.github.com/documentation/guide/pull-requests
- https://lightrun.com/answers/microsoft-vscode-accessibility-screen-readers-do-not-read-currently-focused-line-when-using-altf5altshiftf5

## 11. GitHub Mobile (iOS y Android)

### Funciones destacadas

- Bandeja de notificaciones para triar el trabajo (marcar como hecho, guardar, cancelar suscripción, filtros) (detalle de la bandeja: conocimiento general).
- Revisar PR, aprobar y fusionar desde el teléfono.
- Asignar issues a Copilot, seguir y controlar las tareas del agente.
- Revisión de código por Copilot y chat con Copilot sobre el código.
- Aprobación de inicios de sesión con autenticación en dos pasos (conocimiento general, sin verificar en esta investigación).

### Accesibilidad

- GitHub publica informes de conformidad para iOS y Android y ha dedicado actualizaciones a la accesibilidad: en junio de 2024 corrigió el rol de las insignias del autor de los comentarios y mejoró el contraste y el soporte de TalkBack en Inicio y Repositorio; en septiembre y octubre de 2024 siguió con mejoras de accesibilidad.
- Problemas listados en los informes: en Android, TalkBack no anunciaba la etiqueta asociada de algunas casillas; en iOS, VoiceOver no anunciaba el número de la issue.
- Es la referencia de buena experiencia con lector de pantalla para triar notificaciones.

### Ideas a copiar

- Bandeja de notificaciones con acciones rápidas por elemento (en escritorio: menú contextual y atajos en lugar de gestos).
- Pantalla de inicio con «lo que requiere mi atención».
- Elementos de lista de una sola parada que se leen completos (título, repositorio, número, estado, motivo).

Fuentes:

- https://github.com/mobile
- https://accessibility.github.com/conformance/mobile-ios/
- https://accessibility.github.com/conformance/mobile-android/
- https://github.blog/changelog/2024-07-08-whats-new-in-mobile-june-update
- https://github.blog/changelog/2024-09-16-whats-new-in-mobile-september-update
- https://github.blog/changelog/2024-10-14-whats-new-in-mobile-october-update/

## 12. Tower

### Funciones destacadas

- Deshacer casi todo: cambios locales, revisiones antiguas, revertir commits, recuperar commits y ramas borradas.
- Arrastrar y soltar para operaciones avanzadas.
- Resolución visual de conflictos.
- Ver qué commits faltan por publicar.
- Gestión de autenticación sin tener que manejar claves SSH ni tokens a mano.
- Historial visual.
- Flujos de trabajo de ramas configurables (Tower Workflows), ramas apiladas (stacked branches), limpieza de ramas.
- Disponible para Windows (x64 y ARM).

### Accesibilidad

- No se ha encontrado información sobre lectores de pantalla.

### Ideas a copiar

- Deshacer universal.
- Limpieza de ramas ya fusionadas.
- Gestión de autenticación sencilla (asistente para crear o subir claves SSH y obtener tokens).
- Indicador claro de commits pendientes de subir y de bajar.

Fuente: https://www.git-tower.com/features

## 13. Herramientas accesibles hechas por la comunidad ciega

### Simple Git Assistant / Accessible GitHub Assistant in wxPython

- Autor: Ambro86. Anunciado en AppleVis en junio de 2025. Hecho en Python con wxPython, probado en Windows, con versión para macOS (barra de menús usable con VoiceOver).
- Versión 6.0 según su README («GitHub Integration & Workflows»). Interfaz en inglés, italiano, español, francés, alemán, portugués y ruso.
- Interfaz: árbol de comandos por categorías navegable con flechas, diálogo de parámetros, barra de estado con la descripción del comando, área de salida de texto y campo de ruta del repositorio con botón Examinar. Sonidos de éxito y error.
- Git: clonar, iniciar, .gitignore, estado, diffs preparados y no preparados, commit, enmendar, historial, ramas (crear, cambiar, fusionar, borrar), etiquetas ligeras, fetch, pull, push, remotos, descartar cambios, reset, abortar fusión, stash y pop, git grep.
- GitHub: Actions (listar ejecuciones, seguimiento en tiempo real, registros, lanzar workflow_dispatch, descargar artefactos), PR (listar, crear, ver, fusionar, cerrar, pedir revisión), releases (crear, editar, borrar, subir y bajar archivos), token personal guardado en el gestor de credenciales.
- Ayudas: establecer upstream automáticamente, guía de conflictos (ours, theirs, abortar), aviso antes de push forzado tras enmendar.
- Opiniones: un probador encontró etiquetas poco claras (por ejemplo, un campo «Path» sin decir de qué). No se ve licencia en la página.
- Lecciones para nosotros: el enfoque de «árbol de comandos» funciona pero es poco descubrible; nuestra app debe ofrecer vistas de datos (listas de issues, PR, commits) además de comandos, y etiquetas descriptivas en cada campo.

### Otros recursos de la comunidad

- «GIT Going with GitHub» (Community-Access): taller accesible de código abierto para usar GitHub con lector de pantalla, etiquetado para NVDA, JAWS y VoiceOver; útil como material de formación y para conocer los flujos que la comunidad enseña.
- Guías oficiales de GitHub para lectores de pantalla: repositorios, issues, pull requests, y Git con gh y Copilot CLI.
- No se ha encontrado ningún complemento de NVDA dedicado a Git o GitHub en las búsquedas realizadas, ni hilos en el foro de AudioGames.net sobre un cliente de Git accesible (los resultados de ese foro eran sobre motores de juego).

Fuentes:

- https://github.com/Ambro86/Accessible-github-assistant-in-wxpython
- https://applevis.com/forum/windows/github-assistant-accessible-way-use-github-screenreader
- https://github.com/Community-Access/git-going-with-github
- https://accessibility.github.com/documentation
- https://accessibility.github.com/documentation/guide/repos
- https://accessibility.github.com/documentation/guide/issues
- https://github.com/nvaccess/addon-datastore

## 14. Conclusiones para nuestra aplicación

- Ningún cliente gráfico de escritorio combina hoy gestión completa de GitHub y accesibilidad nativa con lector de pantalla en Windows. GitHub Desktop es el más accesible de los gráficos, pero cubre poco de GitHub; gh cubre casi todo GitHub pero en terminal; la única alternativa comunitaria (wxPython) cubre una parte.
- El hueco más claro: rebase interactivo accesible, visor de diff accesible, revisión de PR con comentarios en líneas, bandeja de notificaciones y Actions, todo con controles nativos.
- Estrategia técnica sugerida: git local mediante la línea de comandos de git; GitHub mediante gh (con `--json`) o la API REST/GraphQL directamente para lo que gh no cubre.

## 15. Lista de verificación de funciones

### Cuentas y autenticación

- Iniciar sesión por navegador (flujo de dispositivo) y por token personal; mostrar el código de un solo uso de forma accesible y copiable.
- Varias cuentas y varios hosts (GitHub.com, GHE.com, Enterprise Server); cambiar cuenta activa; cuenta por repositorio.
- Ver estado de autenticación y permisos (scopes); renovar o ampliar permisos; cerrar sesión.
- Configurar git para usar las credenciales de la app; elegir protocolo HTTPS o SSH.
- Guardar secretos cifrados (DPAPI o Administrador de credenciales).
- Gestión de claves SSH y GPG de la cuenta (listar, añadir, borrar, generar localmente).

### Repositorios

- Clonar (de mi lista, de una organización, por URL, con profundidad y rama), crear, iniciar local, añadir local existente, publicar local en GitHub.
- Lista de repositorios recientes y favoritos con búsqueda; agrupar por cuenta u organización.
- Fork (con opción de clonar) y sincronizar fork con el original.
- Ver información: descripción, temas, estrellas, idioma, licencia, README legible.
- Explorar archivos remotos sin clonar y en cualquier commit o rama.
- Ajustes del repositorio: nombre, descripción, web, temas, visibilidad, rama por defecto, funciones (issues, wiki, proyectos, discusiones), tipos de fusión, borrar rama al fusionar, auto-merge, plantilla.
- Archivar, desarchivar, renombrar, transferir, borrar (con confirmación fuerte).
- Colaboradores e invitaciones, claves de despliegue, autolinks, webhooks, entornos, Pages.
- Plantillas .gitignore y licencias al crear.
- Estrellas, vigilar (watch) y seguir.
- Abrir en el navegador, en el Explorador, en el editor y en la terminal.

### Estado y cambios locales

- Estado del árbol de trabajo: modificados, nuevos, borrados, renombrados, en conflicto, ignorados.
- Indicador de commits pendientes de subir y de bajar respecto al remoto.
- Descartar cambios de archivo, de bloque o de línea (con papelera o copia de seguridad).
- Añadir a .gitignore desde la lista.
- Ver archivos sin seguimiento e ignorados.

### Staging parcial

- Preparar y quitar de preparación por archivo, por bloque (hunk) y por línea o rango de líneas.
- Dividir bloques.
- Lectura accesible de cada bloque y línea con su tipo (añadida o borrada) y número.

### Commits

- Mensaje con resumen y descripción, contador de caracteres del resumen, plantillas de mensaje.
- Coautores, firma (GPG, SSH), saltar ganchos de forma explícita, autor personalizado.
- Enmendar el último commit y enmendar cualquier commit anterior (fixup).
- Deshacer el último commit (soft reset) y revertir un commit.
- Cherry-pick de uno o varios commits.
- Ayuda opcional para redactar el mensaje (Copilot u otro).

### Historial

- Lista de commits con autor, fecha, mensaje, hash corto y referencias (ramas, etiquetas).
- Filtrar por rama, autor, fecha, mensaje, ruta y contenido (pickaxe).
- Historial de un archivo o carpeta, seguimiento de renombrados.
- Blame por línea con salto al commit.
- Descripción textual del grafo (padres, fusiones, rama de origen) en lugar de dibujo.
- Comparar dos commits, ramas o etiquetas.
- Reflog con recuperación de commits y ramas perdidos.
- Bisect guiado (bueno, malo, saltar, terminar).
- Copiar hash, mensaje o URL del commit; abrir el commit en GitHub.

### Diff

- Visor de diff accesible: navegación por bloque y por línea, anuncio de tipo de línea y números, salto al cambio siguiente y anterior.
- Modos unificado y lado a lado (este último como texto alterno para lector).
- Diferencias dentro de la línea (por palabras o caracteres) descritas en texto.
- Opciones: ignorar espacios en blanco, más o menos contexto.
- Archivos binarios e imágenes: información de tamaño y dimensiones.
- Señales sonoras opcionales.

### Ramas y etiquetas

- Listar locales y remotas con su seguimiento (upstream), adelanto y retraso.
- Crear (desde HEAD, un commit, una etiqueta o una issue), cambiar, renombrar, borrar local y remota, establecer upstream.
- Fusionar (normal, squash, sin fast-forward), rebase sobre otra rama, actualizar desde la rama por defecto.
- Limpieza de ramas ya fusionadas y de ramas remotas eliminadas (prune).
- Etiquetas ligeras y anotadas, firmadas, subir y borrar etiquetas remotas.
- Worktrees: crear, listar, abrir, borrar.

### Remotos y sincronización

- Fetch (todos los remotos, con prune), pull (merge o rebase), push, push forzado con lease, push de etiquetas.
- Gestionar varios remotos: añadir, renombrar, cambiar URL, borrar.
- Progreso hablado y cancelable en operaciones largas.

### Stash

- Lista de stashes con mensaje y rama; crear con mensaje, incluir sin seguimiento, stash parcial por archivos.
- Ver el diff de un stash, aplicar, aplicar y borrar (pop), borrar, crear rama desde stash.

### Conflictos

- Lista de archivos en conflicto con el tipo de conflicto.
- Resolución por bloque: aceptar la mía, la suya, ambas, o editar a mano en un editor accesible.
- Usar versión completa propia o ajena, marcar como resuelto, abortar o continuar fusión, rebase o cherry-pick.
- Abrir herramienta externa configurada.

### Rebase interactivo

- Lista editable de commits con acción por commit: pick, reword, edit, squash, fixup, drop; mover arriba y abajo con teclado.
- Autosquash de commits fixup.
- Pausa en edit con instrucciones claras; continuar, saltar, abortar.
- Dividir un commit; parches personalizados (mover cambios entre commits).
- Deshacer el rebase mediante el reflog.

### Submódulos y LFS

- Listar, iniciar, actualizar y añadir submódulos.
- Git LFS: instalar, seguir patrones, ver archivos, bloqueos (locks).

### Pull requests

- Listas: mis PR, revisión pedida, asignados, del repositorio, con filtros y búsqueda.
- Crear PR: rama base y de origen, título y cuerpo (plantilla de PR), borrador, revisores, asignados, etiquetas, hito, proyectos; vista previa de commits y archivos.
- Ver PR: descripción, conversación cronológica, commits, archivos cambiados, checks, estado de fusión y conflictos.
- Checkout de PR, actualizar rama del PR, marcar listo o volver a borrador.
- Editar, cerrar, reabrir, bloquear conversación, revertir PR fusionado.
- Fusionar (merge, squash, rebase), auto-merge, borrar rama tras fusionar, cola de fusión.
- Comentar, reaccionar, editar y borrar comentarios.

### Revisión de código

- Revisión con comentarios en líneas o rangos, sugerencias de cambio, comentarios pendientes enviados juntos.
- Aprobar, pedir cambios o comentar.
- Ver, responder y resolver hilos de revisión; marcar archivos como vistos.
- Pedir y quitar revisores (personas y equipos); revisión por Copilot.

### Issues

- Listas con filtros (abiertas, cerradas, asignadas, mencionadas, creadas por mí, etiquetas, hito) y búsqueda.
- Crear con plantillas y formularios de issue, editar, cerrar (como completada o no planificada), reabrir, borrar, transferir, fijar, bloquear.
- Comentarios, reacciones, menciones con autocompletado.
- Etiquetas, asignados, hitos, tipos, sub-issues y relaciones.
- Crear rama desde una issue (develop) y vincular PR.
- Asignar a Copilot.

### Discusiones

- Listar, ver, crear, editar, comentar y responder, marcar respuesta.

### Proyectos (Projects)

- Listar, ver, crear, editar, cerrar, copiar.
- Elementos: añadir, crear borrador, editar campos, archivar, borrar; campos personalizados; vincular a repositorios y equipos.

### Actions

- Lista de flujos (workflows), activar y desactivar, lanzar con parámetros (workflow_dispatch).
- Lista de ejecuciones con estado, rama, evento y duración; seguimiento en vivo con avisos hablados al terminar.
- Ver trabajos y pasos, registros completos o sólo lo fallido en un visor de texto accesible con búsqueda.
- Volver a ejecutar (todo o fallidos), cancelar, borrar ejecuciones.
- Descargar artefactos; gestionar cachés.
- Secretos y variables de repositorio, entorno y organización.

### Releases y paquetes

- Listar, ver, crear (con notas generadas automáticamente), editar, borrar, borrador y preliminar (pre-release).
- Subir, descargar y borrar archivos adjuntos.
- Verificar atestaciones.
- Ver paquetes del repositorio u organización.

### Notificaciones

- Bandeja con filtros (no leídas, participando, menciones, revisiones pedidas, por repositorio y motivo).
- Marcar como leída o hecha, guardar, cancelar suscripción, abrir el elemento dentro de la app.
- Comprobación periódica en segundo plano con aviso del sistema y anuncio en el lector.
- Resumen tipo «gh status» como pantalla de inicio.

### Búsqueda

- Buscar repositorios, código, commits, issues, PR, usuarios y temas, con calificadores y filtros guardados.

### Gists

- Listar, ver, crear (público o secreto, varios archivos), editar, renombrar archivos, borrar, clonar, estrellas.

### Organizaciones y equipos

- Listar mis organizaciones, ver repositorios, miembros y equipos.
- Gestionar miembros, invitaciones, equipos y sus permisos (para administradores).
- Rulesets: ver y comprobar reglas que aplican a una rama; crear y editar mediante la API.

### Seguridad

- Alertas de Dependabot, code scanning y secret scanning (listar, ver, descartar).
- Activar escaneo de secretos y protección de push.
- Protección de ramas y rulesets.
- Verificación de firmas de commits.
- Claves de despliegue y auditoría básica.

### Codespaces y Copilot

- Listar, crear, parar, borrar y abrir codespaces (en VS Code o SSH).
- Tareas del agente de Copilot: crear, listar, ver.

### Ajustes de la aplicación

- Identidad de git (nombre y correo, global y por repositorio), editor, herramienta de diff y de fusión externas, terminal.
- Comportamiento de pull (merge o rebase), fetch automático, firma por defecto.
- Opciones de verbosidad y de anuncios del lector, sonidos, formato de lectura de las listas (orden de columnas).
- Atajos configurables, idioma, tema de alto contraste y tamaño de letra.
- Registro de los comandos git y gh ejecutados, visible y copiable.
- Exportar e importar configuración; portabilidad.

### Accesibilidad transversal (requisitos de diseño)

- Controles nativos de wxPython con etiquetas; listas multicolumna que se leen completas.
- Paleta de comandos para buscar cualquier acción por nombre.
- Atajos sin conflicto con NVDA y JAWS; menús con todas las acciones.
- Progreso en texto (nunca sólo animación) y avisos de fin de operación.
- Mensajes de error claros, leídos automáticamente, con el texto original de git o de GitHub disponible.
- Confirmaciones para acciones destructivas y deshacer donde sea posible.
- Ayuda contextual en cada pantalla.
