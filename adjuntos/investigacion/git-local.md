# Git local: operaciones y cómo invocarlas desde Python

Investigación del 21 de noviembre de 2026. Equipo de referencia: Git para Windows 2.55.0 (`C:\Program Files\Git\cmd\git.exe`), Git Credential Manager 2.9.0, gh 2.100.0.

## Parte 1. Operaciones que debe ofrecer un cliente completo

Para cada operación: la orden recomendada y notas de accesibilidad o de análisis de la salida.

### Repositorios

- Clonar: `git clone --progress [--depth N] [--branch RAMA] [--recurse-submodules] [--filter=blob:none] URL CARPETA`. El progreso va por stderr (ver Parte 3). Ofrecer clon parcial (`--filter=blob:none`) para repos grandes.
- Crear: `git init -b main CARPETA`. Luego, si se quiere publicar, crear el repo con la API (`POST /user/repos`) y `git remote add origin URL` y `git push -u origin main`.
- Abrir un repo existente: `git rev-parse --show-toplevel --git-dir --is-bare-repository --is-inside-work-tree` para validar la carpeta.
- Comprobar si hay operación en curso (fusión, rebase, cherry-pick, revert, bisect): mirar si existen, usando `git rev-parse --git-path NOMBRE` para obtener la ruta real: `MERGE_HEAD`, `rebase-merge`, `rebase-apply`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`. Anunciarlo siempre en la ventana del repo («Fusión en curso con 3 conflictos»).

### Estado

- `git status --porcelain=v2 -z --branch --show-stash --untracked-files=all` (más `--ignored` si se piden los ignorados).
- Formato porcelain v2 (estable entre versiones, pensado para programas):
  - Cabeceras: `# branch.oid SHA`, `# branch.head RAMA` (o `(detached)`), `# branch.upstream origin/RAMA`, `# branch.ab +3 -1` (adelantado 3, atrasado 1), `# stash N`.
  - `1 XY sub mH mI mW hH hI ruta`: cambio normal. X = estado en el índice (preparado), Y = estado en el árbol de trabajo. Letras: `.` sin cambio, `M` modificado, `T` cambio de tipo, `A` añadido, `D` borrado, `R` renombrado, `C` copiado, `U` sin fusionar.
  - `2 XY sub mH mI mW hH hI Xscore ruta` seguido (con -z) de la ruta original: renombrados o copiados.
  - `u XY sub m1 m2 m3 mW h1 h2 h3 ruta`: conflicto. XY: `UU` ambos modificados, `AA` ambos añadidos, `DD` ambos borrados, `AU` añadido por nosotros, `UA` añadido por ellos, `DU` borrado por nosotros, `UD` borrado por ellos.
  - `? ruta`: sin seguimiento. `! ruta`: ignorado.
- Con `-z` las rutas no se entrecomillan ni escapan, y cada entrada termina en NUL. Imprescindible con nombres con acentos o espacios.
- Para la interfaz: dos listas («Preparados para commit» y «Cambios sin preparar», más «Sin seguimiento» y «En conflicto»), con columnas Archivo, Estado (en palabras: «modificado», «nuevo», «borrado», «renombrado desde X») y Carpeta.
- En sondeos en segundo plano usar `GIT_OPTIONAL_LOCKS=0` para que `status` no bloquee el índice mientras la persona trabaja en otra herramienta.

### Preparar (stage) y quitar del índice

- Archivo entero: `git add -- RUTA...`, `git add -A` (todo), `git rm --cached -- RUTA` (dejar de seguir), `git restore --staged -- RUTA` (quitar del índice).
- Parcial por bloques o por líneas (lo que hace `git add -p`, pero sin modo interactivo):
  - Obtener el diff con `git diff --no-color --no-ext-diff -U3 -- RUTA`.
  - Construir un parche solo con los bloques o líneas elegidos (en una selección por líneas: las líneas no elegidas «+» se quitan y las «-» no elegidas se convierten en contexto).
  - Aplicarlo al índice: `git apply --cached --recount --whitespace=nowarn -` (parche por stdin).
  - Quitar del índice parcialmente: `git diff --cached` y `git apply --cached --reverse --recount -`.
  - Descartar cambios parciales del árbol de trabajo: `git apply --reverse --recount -`.
- Interfaz accesible: lista de bloques («Bloque 2 de 5, líneas 40 a 52, 3 añadidas, 1 eliminada»), casilla por bloque o por línea, tecla Espacio para marcar, Intro para preparar.

### Descartar cambios

- `git restore -- RUTA` (árbol de trabajo), `git restore --source=HEAD --staged --worktree -- RUTA` (todo).
- Archivos sin seguimiento: `git clean -n` (simulación: mostrar la lista primero) y `git clean -f -- RUTA`. Con `-d` carpetas, `-x` también ignorados. Siempre confirmar: es irreversible. Alternativa más segura: mover a la papelera de Windows con send2trash o la API de shell.

### Commit

- `git commit -F -` y el mensaje por stdin en UTF-8. Evita problemas de comillas y de longitud de la línea de órdenes.
- Opciones: `--amend` (modificar el último), `--no-edit`, `--allow-empty`, `--signoff`, `-S` (firmar), `--author="Nombre <correo>"`, `--date`, `--no-verify` (saltar hooks: pedir confirmación), `--fixup=SHA` y `--squash=SHA` (para autosquash).
- Coautores: añadir en el cuerpo líneas `Co-authored-by: Nombre <correo>`; ofrecer una lista de colaboradores.
- Antes de hacer commit, si `user.name` o `user.email` no están configurados, pedirlos (ver Configuración). Proponer el correo noreply de GitHub `ID+login@users.noreply.github.com` (el id sale de `GET /user`).
- Plantillas: `commit.template`, y convenciones (Conventional Commits) como ayuda opcional.
- Hooks: si `pre-commit` o `commit-msg` fallan, mostrar su salida completa en un cuadro de texto de solo lectura navegable.

### Ramas

- Listar: `git for-each-ref --format=%(refname)%00%(refname:short)%00%(objectname)%00%(upstream:short)%00%(upstream:track,nobracket)%00%(committerdate:unix)%00%(HEAD)%00%(subject) refs/heads refs/remotes`. Mejor separar campos con `%00` o `%1f` y registros con salto de línea (las refs no pueden contener NUL ni salto de línea).
- Crear: `git branch NOMBRE [PUNTO_DE_PARTIDA]` o `git switch -c NOMBRE`.
- Cambiar: `git switch RAMA` (Git 2.23 o posterior; si no, `git checkout RAMA`). Con cambios sin guardar que chocan, git se niega: ofrecer «Guardar en stash y cambiar», «Llevar los cambios» (`git switch --merge`) o «Descartar».
- Desde una rama remota: `git switch --track origin/RAMA`.
- Renombrar: `git branch -m VIEJO NUEVO`. Borrar: `git branch -d` (seguro) o `-D` (forzar, confirmar). Borrar remota: `git push origin --delete RAMA`.
- Seguimiento: `git branch --set-upstream-to=origin/RAMA`.
- Ramas ya fusionadas: `git branch --merged main` (para limpieza).
- Detached HEAD: avisar claramente y ofrecer crear una rama.

### Remotos y sincronización

- `git remote -v`, `git remote add NOMBRE URL`, `git remote set-url`, `git remote rename`, `git remote remove`, `git remote prune origin`.
- Fetch: `git fetch --prune --progress [--all] [--tags]`.
- Pull: `git pull --progress --ff-only` por defecto, o `--rebase` o `--no-rebase` según la preferencia (`pull.rebase`, `pull.ff`). Explicar qué pasa si las ramas han divergido.
- Push: `git push --progress [-u origin RAMA] [--tags] [--force-with-lease]`. Nunca `--force` a secas; usar `--force-with-lease` y confirmar.
- Analizar rechazos: «rejected (non-fast-forward)», «fetch first», errores de protección de rama (GH006), push protection de secretos (GH013), falta de scope `workflow` («refusing to allow an OAuth App to create or update workflow without workflow scope»), archivos de más de 100 MB. Traducirlos al español con una explicación y la acción recomendada.
- Forks: remoto `upstream` y sincronización (o `POST /repos/{owner}/{repo}/merge-upstream`).

### Fusionar, rebase, cherry-pick, revert

- Merge: `git merge [--no-ff] [--squash] [--no-commit] RAMA`. Abortar: `git merge --abort`. Continuar: `git merge --continue` (o `git commit`).
- Rebase simple: `git rebase RAMA_BASE`. Continuar, saltar, abortar: `git rebase --continue`, `--skip`, `--abort`. Con `GIT_EDITOR=true` (o `-c core.editor=true`) para que `--continue` no abra editor.
- Rebase interactivo sin editor (reordenar, squash, fixup, editar, borrar, reword):
  - La app muestra la lista de commits (de `git log --reverse BASE..HEAD`) y la persona elige acciones con una lista accesible (subir y bajar con Alt+flechas, cambiar acción con un menú).
  - Se escribe el archivo todo (líneas `pick SHA asunto`, `squash`, `fixup`, `reword`, `edit`, `drop`, `exec`, `break`) en un archivo temporal.
  - Se lanza `git rebase -i BASE` con `GIT_SEQUENCE_EDITOR` apuntando a un programa que copie ese archivo sobre el que recibe git. Con Git para Windows sirve: `GIT_SEQUENCE_EDITOR=cp 'C:/ruta/todo.txt'` (git ejecuta el editor con sh y añade la ruta del archivo todo).
  - Para `reword`, poner `GIT_EDITOR` a un programa que escriba el nuevo mensaje, o usar `exec git commit --amend -F archivo` en el todo.
  - Alternativa: `git rebase -i --autosquash` con commits `fixup!` creados antes.
- Cherry-pick: `git cherry-pick [-x] [-n] SHA...`, `--continue`, `--skip`, `--abort`.
- Revert: `git revert [--no-edit] SHA`, `-m 1` para commits de fusión, `--continue`, `--abort`.
- Fusionar sin tocar el árbol de trabajo (previsualizar conflictos): `git merge-tree --write-tree --name-only -z RAMA1 RAMA2` (Git 2.38 o posterior). Permite avisar «esta fusión tendrá conflictos en 2 archivos» antes de hacerla.

### Conflictos

- Detectarlos con las entradas `u` de status porcelain v2 o `git diff --name-only --diff-filter=U -z`.
- Versiones de cada lado: `git show :1:RUTA` (base común), `:2:RUTA` (nuestra, ours), `:3:RUTA` (la otra, theirs).
- Resolver un archivo entero: `git checkout --ours -- RUTA` o `--theirs` y luego `git add -- RUTA`. Ojo: en un rebase «ours» y «theirs» están invertidos; la interfaz debe hablar de «tu rama» y «la rama que se aplica» y no de ours y theirs.
- Resolver bloque a bloque: leer el archivo con los marcadores `<<<<<<<`, `|||||||` (si `merge.conflictStyle=diff3` o `zdiff3`, recomendado porque muestra la base), `=======`, `>>>>>>>`. Presentar cada conflicto como «Conflicto 1 de 3, líneas 20 a 34», con opciones «Quedarse con lo mío», «Quedarse con lo suyo», «Ambos (mío primero)», «Ambos (suyo primero)», «Editar a mano». Escribir el resultado y hacer `git add`.
- Volver a generar los marcadores: `git checkout -m -- RUTA`. Fusión de tres archivos fuera de git: `git merge-file -p ACTUAL BASE OTRO`.
- Conflictos de borrado o de binarios: ofrecer solo mantener o borrar (`git rm`).
- `git rerere` (recordar resoluciones) como opción avanzada.

### Stash

- `git stash push [-u] [-k] -m "mensaje" [-- RUTAS]` (`-u` incluye sin seguimiento, `-k` mantiene el índice, `--staged` solo lo preparado).
- Listar: `git stash list -z --format=%gd%x1f%H%x1f%ct%x1f%gs`.
- Ver: `git stash show -p stash@{N}` (y `--include-untracked`).
- Aplicar: `git stash apply --index stash@{N}`, `git stash pop`, borrar `git stash drop`, `git stash clear` (confirmar), `git stash branch RAMA stash@{N}`.

### Etiquetas (tags)

- Listar: `git for-each-ref --sort=-creatordate --format=... refs/tags`.
- Crear: `git tag NOMBRE [SHA]` (ligera), `git tag -a NOMBRE -F -` (anotada, mensaje por stdin), `-s` firmada.
- Publicar: `git push origin NOMBRE` o `--tags`. Borrar: `git tag -d NOMBRE` y `git push origin --delete refs/tags/NOMBRE`.
- Enlazar con releases de GitHub (crear release desde un tag).

### Historial (log)

- `git log -z --format=%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%cn%x1f%ct%x1f%D%x1f%G?%x1f%s%x1f%b [RANGO] [-- RUTA]`. Con `-z` cada commit termina en NUL; dentro, los campos se separan con el carácter 0x1F.
- Paginar con `--skip=N -n 200` o mejor con `--max-count` y continuar desde el último SHA.
- Filtros: `--author`, `--since`, `--until`, `--grep` (mensaje, `-i`), `-S texto` y `-G regex` (búsqueda en cambios, «pico»), `--follow -- ARCHIVO` (historial de un archivo con renombrados), `--first-parent`, `--merges`, `--no-merges`, `--all`.
- Gráfico de ramas: `--graph` produce arte ASCII; no leerlo con voz. En su lugar, mostrar por commit sus padres, las ramas y tags que apuntan a él (`%D`) y si es fusión («Fusión de rama X en Y»).
- `%G?` da el estado de la firma: G buena, B mala, U buena con validez desconocida, N sin firma, etc.
- Detalle de un commit: `git show --no-color --stat --patch -M SHA`, y `--format=fuller`.
- Reflog: `git reflog -z --format=%H%x1f%gd%x1f%gs%x1f%ct` (para recuperar commits perdidos tras un reset o rebase: ofrecer «Deshacer última operación» basado en el reflog, como lazygit y GitKraken).

### Diff

- Árbol de trabajo frente al índice: `git diff`. Índice frente a HEAD: `git diff --cached`. Entre commits o ramas: `git diff A..B` o `A...B` (desde la base común, como en un PR).
- Siempre `--no-color --no-ext-diff`, y `-M` (detectar renombrados), `-U3` (contexto; permitir cambiarlo).
- Lista de archivos: `git diff --name-status -z` y `git diff --numstat -z` (líneas añadidas y borradas por archivo; `-` `-` para binarios).
- Diferencias dentro de una línea: `git diff --word-diff=porcelain` marca palabra a palabra qué cambió (líneas que empiezan por espacio, `+`, `-` y `~` como fin de línea). Muy útil para anunciar «cambiado: 3 por 4» en vez de leer dos líneas casi iguales.
- `--ignore-all-space` (`-w`), `--ignore-blank-lines`, `--diff-algorithm=histogram` (resultados más legibles).
- Diff de imágenes y binarios: solo anunciar «archivo binario modificado, tamaño antes y después».
- Accesibilidad: el visor de diff debe mostrar una línea por elemento con prefijo hablado («añadida», «eliminada», «contexto»), número de línea antiguo y nuevo, saltos entre bloques y archivos, y sonidos opcionales. Ver necesidades-usuarios.md.

### Blame

- `git blame --porcelain -M -C [-w] [REV] -- RUTA` o `--line-porcelain` (repite la información del commit en cada línea: más fácil de analizar).
- `--ignore-revs-file .git-blame-ignore-revs` si existe.
- En la interfaz: al moverse por las líneas del archivo, una tecla anuncia «Línea 42: autor, fecha, asunto del commit»; Intro abre el commit.

### Submódulos

- `git submodule status --recursive`, `git submodule update --init --recursive --progress`, `git submodule add URL RUTA`, `git submodule sync`, `git submodule foreach ...`, `git submodule deinit`.
- En status porcelain v2, el campo `sub` indica si una entrada es submódulo (`S` seguido de C, M, U: commit cambiado, cambios sin preparar, sin seguimiento).

### Git LFS

- Comprobar: `git lfs version` (viene con Git para Windows).
- `git lfs install` (una vez por usuario), `git lfs track "*.wav"`, `git lfs ls-files`, `git lfs pull`, `git lfs fetch`, `git lfs status`, `git lfs migrate import`.
- Las credenciales de LFS usan el mismo helper o el mismo `http.extraheader`.
- Avisar si un archivo grande no está en LFS antes de hacer push (GitHub rechaza archivos de más de 100 MB y avisa a partir de 50 MB).

### Worktrees

- `git worktree list --porcelain -z`, `git worktree add RUTA RAMA` (o `-b NUEVA`), `git worktree remove RUTA`, `git worktree prune`, `lock` y `unlock`.
- Útil para revisar un PR sin tocar la rama actual.

### Configuración

- Leer: `git config --list --show-origin --show-scope -z` (con `-z` cada entrada es `origen NUL clave\nvalor NUL`).
- Escribir: `git config --global user.name "..."`, `git config --global user.email "..."`, y valores por repo con `--local`.
- Valores recomendados que la app puede proponer (siempre con permiso, porque cambian la configuración global): `init.defaultBranch=main`, `pull.ff=only` o `pull.rebase=true`, `merge.conflictStyle=zdiff3`, `core.longpaths=true`, `core.autocrlf=true` (Windows), `fetch.prune=true`, `rerere.enabled=true`.
- «Dubious ownership»: si git dice que el repo pertenece a otro usuario (frecuente en discos externos o carpetas copiadas), explicar y ofrecer `git config --global --add safe.directory RUTA`.
- `.gitignore`: editor con plantillas de `GET /gitignore/templates`; `git check-ignore -v -z RUTA` para explicar por qué se ignora un archivo.
- `.gitattributes`: finales de línea y LFS.

### Hooks

- Viven en `.git/hooks` o en `core.hooksPath`. Git los ejecuta con el sh de Git para Windows.
- La app debe: mostrar la salida de un hook que falla, permitir saltarlo con confirmación (`--no-verify`), listar los hooks activos y abrir su archivo.
- Herramientas como pre-commit (Python) o husky (Node) instalan hooks: si fallan por falta de entorno, dar un mensaje claro.

### Firma de commits y tags

- Tres formatos (`gpg.format`): `openpgp` (GPG, por defecto), `ssh` (recomendado por sencillez) y `x509` (S/MIME con gpgsm o smimesign).
- Firma con SSH: `git config --global gpg.format ssh`, `git config --global user.signingkey "%USERPROFILE%/.ssh/id_ed25519.pub"`, `git config --global commit.gpgsign true`, `tag.gpgsign true`. Subir la clave como clave de firma (`POST /user/ssh_signing_keys`). Para verificar en local hace falta `gpg.ssh.allowedSignersFile`.
- Firma con GPG: Git para Windows trae `gpg` en `C:\Program Files\Git\usr\bin\gpg.exe`; Gpg4win usa `C:\Program Files (x86)\GnuPG\bin\gpg.exe` (configurar `gpg.program`). La frase de paso la pide pinentry en una ventana propia (comprobar su accesibilidad).
- Ver firmas: `git log --show-signature` o `%G?`, `%GS`, `%GK` en el formato. `git verify-commit SHA`, `git verify-tag TAG`.
- Los commits creados con la API (`createCommitOnBranch` o la web) los firma GitHub y salen como verificados.

### Sparse checkout y clones parciales

- `git sparse-checkout init --cone`, `git sparse-checkout set CARPETA1 CARPETA2`, `git sparse-checkout list`, `git sparse-checkout disable`.
- Combinar con `git clone --filter=blob:none --sparse URL` para repos enormes (monorepos).

### Bisect

- `git bisect start MALO BUENO`, luego `git bisect good` o `git bisect bad` en cada paso (o `skip`), `git bisect reset`, `git bisect log`, `git bisect run ORDEN` (automático).
- Interfaz guiada: «Paso 3 de unos 7. Commit actual: asunto. ¿Funciona? Bueno, Malo, Saltar».

### Reset

- `git reset --soft SHA` (mantiene todo preparado), `--mixed` (por defecto, mantiene cambios sin preparar), `--hard` (descarta: confirmar con aviso claro), `--keep`.
- `git reset -- RUTA` equivale a quitar del índice.
- Ofrecer deshacer con el reflog (`git reset --hard HEAD@{1}`) tras cualquier operación destructiva.

### Limpieza y mantenimiento

- `git clean` (ver Descartar cambios), `git gc`, `git maintenance run`, `git fsck`, `git count-objects -vH` (tamaño del repo).

### Otras órdenes útiles

- `git grep -n -I --no-color -z PATRÓN` (buscar en el código local).
- `git ls-files -z` (navegador de archivos del repo), `git ls-tree -z -r --name-only REV` (archivos de cualquier commit), `git show REV:RUTA` (ver un archivo en un commit).
- `git archive --format=zip -o archivo.zip REV`.
- `git format-patch` y `git am` (parches por correo).
- `git shortlog -sne` (contribuidores).
- `git describe --tags` (versión).
- `git notes`.

## Parte 2. Detectar git instalado

- Orden de búsqueda recomendado:
  1. Ruta configurada por la persona en las preferencias.
  2. `shutil.which("git")` (equivale a `where git`; respeta PATH y PATHEXT).
  3. Registro de Windows: `HKEY_LOCAL_MACHINE\SOFTWARE\GitForWindows`, valor `InstallPath` (y la misma clave en `HKEY_CURRENT_USER` para instalaciones por usuario).
  4. Rutas típicas:
     - `C:\Program Files\Git\cmd\git.exe` (instalación normal de 64 bits).
     - `C:\Program Files (x86)\Git\cmd\git.exe`.
     - `%LOCALAPPDATA%\Programs\Git\cmd\git.exe` (instalación por usuario).
     - `%USERPROFILE%\scoop\shims\git.exe` y `%USERPROFILE%\scoop\apps\git\current\cmd\git.exe`.
     - `C:\ProgramData\chocolatey\bin\git.exe`.
     - Git portable o MinGit dentro de la carpeta de la propia app (por ejemplo `data\git\cmd\git.exe`).
     - Git de GitHub Desktop: `%LOCALAPPDATA%\GitHubDesktop\app-VERSION\resources\app\git\cmd\git.exe` (sirve, pero cambia de ruta con cada versión).
- Preferir `cmd\git.exe` frente a `mingw64\bin\git.exe`: el primero prepara bien el entorno (PATH con las herramientas de Git, como sh, ssh y gpg).
- Comprobar la versión con `git --version` (por ejemplo `git version 2.55.0.windows.3`). Mínimos: 2.11 para porcelain v2, 2.23 para `switch` y `restore`, 2.35 para `--show-stash`, 2.38 para `merge-tree --write-tree`. Recomendar 2.40 o posterior.
- Si no hay git:
  - Explicar qué funciones se pierden y ofrecer instalarlo. Opciones (todas piden permiso explícito, porque descargan e instalan software):
    - `winget install --id Git.Git -e --source winget`.
    - Descargar MinGit (zip portable, unos 40 MB, sin interfaz) de https://github.com/git-for-windows/git/releases y descomprimirlo en la carpeta de datos de la app. Encaja con una app portable y no necesita administrador.
  - Mientras tanto, usar la alternativa sin git (Parte 5).

## Parte 3. Invocar git de forma robusta con subprocess

### Reglas

- Pasar siempre una lista de argumentos (nunca `shell=True`), con la ruta completa de git.
- `stdin=subprocess.DEVNULL` salvo que se envíe algo por stdin (mensaje de commit, parche). Así git nunca se queda esperando una respuesta.
- `creationflags=subprocess.CREATE_NO_WINDOW` en Windows, para que no aparezca una consola (y en la app congelada con cx_Freeze, tampoco al lanzar sh, ssh o el helper de credenciales).
- Capturar como bytes y decodificar en UTF-8 con `errors="replace"` (o `surrogateescape` para rutas). Git para Windows escribe rutas en UTF-8; `core.quotepath=false` evita los escapes octales en salidas sin `-z`.
- Opciones globales delante de la suborden: `git --no-pager -c color.ui=false -c core.quotepath=false -c core.editor=true -c i18n.logOutputEncoding=UTF-8 -c advice.detachedHead=false SUBORDEN ...`.
- Ejecutar en el directorio del repo con `cwd=` (o `git -C RUTA`).
- Ejecutar en un hilo de trabajo, nunca en el hilo de la interfaz; anunciar inicio y fin; permitir cancelar.

### Variables de entorno

- Copiar `os.environ` y añadir:
  - `GIT_TERMINAL_PROMPT=0`: git no pide usuario ni contraseña por consola (falla en su lugar).
  - `GCM_INTERACTIVE=never`: Git Credential Manager no abre ventanas (si se quiere controlar todo desde la app).
  - `GIT_PAGER=cat` y `PAGER=cat`: sin paginador.
  - `GIT_EDITOR=true` (o un editor nuestro): nunca abrir Vim ni el Bloc de notas por sorpresa.
  - `GIT_SEQUENCE_EDITOR`: solo para el rebase interactivo controlado (ver Parte 1).
  - `LC_ALL=C` y `LANG=C`: mensajes en inglés y estables para poder analizarlos. Luego la app traduce al español los errores conocidos. Si se quiere mostrar el texto de git en español, Git para Windows incluye traducciones; probar con `LANG=es_ES.UTF-8` solo para las órdenes cuya salida se muestra tal cual (verificar en el equipo).
  - `GIT_OPTIONAL_LOCKS=0` en las órdenes de solo lectura en segundo plano.
  - `GIT_SSH_COMMAND="ssh -o BatchMode=yes"` para que ssh no pregunte nada (frase de paso, huella).
  - `GIT_ASKPASS` y `SSH_ASKPASS`: ver Parte 4.
  - `GIT_FLUSH=1` para que la salida llegue a tiempo.
  - No heredar `GIT_DIR` ni `GIT_WORK_TREE` si existieran en el entorno (borrarlas).

### Progreso

- Las órdenes de red (`clone`, `fetch`, `pull`, `push`) escriben el progreso en stderr cuando se añade `--progress`, con retornos de carro (`\r`) para actualizar la misma línea.
- Leer stderr en un hilo, byte a byte o por bloques, separando por `\r` y `\n`. Con `LC_ALL=C` las líneas son del tipo `Receiving objects:  45% (450/1000), 1.20 MiB | 2.00 MiB/s` y `Resolving deltas: 100% (300/300), done.`; extraer fase y porcentaje con una expresión regular.
- Traducir las fases: Counting objects (contando objetos), Compressing objects (comprimiendo), Receiving objects (recibiendo), Resolving deltas (resolviendo diferencias), Writing objects (enviando), Updating files (actualizando archivos).
- Actualizar una barra de progreso (wx.Gauge, que los lectores leen) y anunciar por voz solo cada 25 % o cada 10 segundos para no saturar.

### Cancelar

- `Popen.terminate()` mata solo git.exe; los procesos hijos (git-remote-https, ssh) pueden quedarse. En Windows, usar un Job Object (pywin32: `CreateJobObject`, `AssignProcessToJobObject` con `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) o `taskkill /T /F /PID N`.
- Tras cancelar una operación que escribe (por ejemplo un fetch), puede quedar un `index.lock` o `shallow.lock`: detectar el error «Unable to create ... .lock: File exists» y ofrecer borrarlo si no hay otro git en marcha.

### Errores

- Considerar el código de salida (0 bien; 1 en `diff --exit-code` significa «hay diferencias», no error; 128 error fatal).
- Guardar stdout y stderr completos en el registro (sin tokens) y mostrar a la persona un mensaje en español más el texto original en un cuadro desplegable.

### Esqueleto en Python

    import os, subprocess

    def ejecutar_git(git, args, cwd, entrada=None, extra_env=None):
        env = dict(os.environ)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(k, None)
        env.update({
            "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
            "GIT_PAGER": "cat", "PAGER": "cat", "GIT_EDITOR": "true",
            "LC_ALL": "C", "LANG": "C",
        })
        if extra_env:
            env.update(extra_env)
        cmd = [git, "--no-pager", "-c", "color.ui=false",
               "-c", "core.quotepath=false", *args]
        r = subprocess.run(
            cmd, cwd=cwd, env=env,
            input=entrada.encode("utf-8") if entrada else None,
            stdin=None if entrada else subprocess.DEVNULL,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (r.returncode,
                r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"))

(Para órdenes largas con progreso, usar `Popen` y leer stderr en un hilo.)

## Parte 4. Pasar el token a git sin guardarlo

El objetivo es que `clone`, `fetch`, `pull` y `push` por HTTPS usen el token de la app sin escribirlo en `.git/config`, en la URL del remoto ni en la línea de órdenes (que otros procesos pueden leer).

### Opción A (recomendada): cabecera HTTP por variables de entorno

- Git 2.31 o posterior admite configuración por entorno: `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_0`, `GIT_CONFIG_VALUE_0`.
- Configurar:
  - `GIT_CONFIG_COUNT=1`
  - `GIT_CONFIG_KEY_0=http.https://github.com/.extraheader`
  - `GIT_CONFIG_VALUE_0=AUTHORIZATION: basic BASE64("x-access-token:TOKEN")`
- Es lo mismo que hace actions/checkout. La cabecera solo se envía a URLs que empiecen por `https://github.com/` (para Enterprise Server, usar su host).
- Se aplica también a Git LFS.
- Si además hay un helper de credenciales configurado (GCM), la cabecera tiene prioridad; para evitar que GCM intervenga, añadir otra entrada que vacíe el helper: `GIT_CONFIG_KEY_1=credential.helper`, `GIT_CONFIG_VALUE_1=` (vacío) y `GIT_CONFIG_COUNT=2`.
- El token queda solo en el entorno del proceso hijo (visible para el mismo usuario de Windows con herramientas avanzadas, pero no en la línea de órdenes ni en disco).

### Opción B: helper de credenciales temporal

- `git -c credential.helper= -c "credential.helper=!f() { echo username=x-access-token; echo password=$GA_TOKEN; }; f" fetch`
- El primer `credential.helper=` vacío anula los helpers anteriores (GCM). El token se pasa en la variable de entorno `GA_TOKEN`, no en la orden.
- Git ejecuta el helper con el sh de Git para Windows: funciona con Git para Windows, no con otras instalaciones sin sh.
- También se puede usar el propio gh como helper: `-c credential.helper= -c "credential.helper=!gh auth git-credential"`.

### Opción C: GIT_ASKPASS

- Git llama al programa de `GIT_ASKPASS` con la pregunta («Username for 'https://github.com': » o «Password for ...») y usa lo que imprime.
- En Windows hace falta un ejecutable o un .bat/.cmd: por ejemplo un `askpass.cmd` que imprima `x-access-token` si la pregunta empieza por «Username» y `%GA_TOKEN%` si no. En la app congelada, se puede apuntar al propio ejecutable con un argumento especial, pero arranca más lento.
- Menos fiable que A y B (depende de que git pregunte; si hay helper, no llega a preguntar).

### Qué no hacer

- No poner el token en la URL (`https://TOKEN@github.com/...`): queda guardado en `.git/config` y aparece en mensajes de error.
- No usar `git -c http.extraHeader=...` en la línea de órdenes: se ve en la lista de procesos.
- No guardar el token con `git credential approve` sin que la persona lo pida.

### Nombre de usuario

- Con cualquier token de GitHub (PAT clásico, fine-grained, OAuth `gho_`, `ghs_`) vale el usuario `x-access-token` (o el login real). La contraseña es el token.

### SSH

- Si el remoto es SSH (`git@github.com:owner/repo.git`), el token no sirve: hace falta la clave y el agente (ver autenticacion.md). La app puede ofrecer convertir el remoto a HTTPS (`git remote set-url`).

## Parte 5. Alternativas si no hay git instalado

### dulwich (recomendada como alternativa)

- Implementación de git en Python puro con extensiones opcionales en Rust. Versión 1.2.21 (5 de noviembre de 2026).
- Tiene ruedas para Windows y Python 3.15: `cp315-cp315-win_amd64`, `win32`, `win_arm64` y también la variante sin GIL (`cp315t`), además de una rueda `py3-none-any` de respaldo. Clasificadores oficiales hasta 3.15.
- Su módulo `dulwich.porcelain` cubre casi todo (lista sacada de la rueda 1.2.21): clone, init, add, commit, status, diff, log, show, blame (annotate), branch_create, branch_delete, branch_list, checkout, switch, merge, merge_tree, rebase (incluido interactivo), cherry_pick, revert, reset, restore, stash_push, stash_pop, stash_list, stash_drop, tag_create, tag_delete, tag_list, fetch, pull, push, ls_remote, remote_add, remote_remove, submodule_add, submodule_init, submodule_update, worktree_add, worktree_list, worktree_remove, sparse_checkout, bisect_start, bisect_good, bisect_bad, reflog, clean, gc, grep, describe, archive, format_patch, am, notes, rerere, filter_branch, y Git LFS (lfs_init, lfs_track, lfs_pull, lfs_push...).
- Autenticación HTTPS: pasando `username` y `password` (el token) a las funciones de red, o con un cliente HTTP propio. SSH: usa el ssh del sistema o paramiko.
- Limitaciones: más lenta que git en repos grandes; algunas funciones son más recientes y menos probadas que en git; no ejecuta hooks como git (verificar); los mensajes de error son de Python.
- Licencia Apache 2.0 o GPL 2 o posterior (doble).

### pygit2 (libgit2)

- Versión 1.21.0 (4 de noviembre de 2026), requiere Python 3.11 o posterior. Tiene ruedas `cp315-cp315-win_amd64`, `win32`, `win_arm64` y `cp315t`.
- Muy rápida y completa en lo básico: repos, índice, commits, diff, blame, merge, cherry-pick, revert, stash, worktrees, submódulos, remotos con callbacks de credenciales.
- Limitaciones: sin rebase de alto nivel, sin Git LFS, sin hooks; la compatibilidad con SSH en las ruedas de Windows depende de si incluyen libssh2 (verificar). Licencia GPL 2 con excepción de enlace.

### GitPython

- Versión 3.2.1. No es alternativa: es un envoltorio que **necesita** el ejecutable git. Además está en mantenimiento mínimo. Mejor nuestro propio envoltorio con subprocess.

### Sin ninguna librería: API de GitHub

- Descargar el código: `GET /repos/{owner}/{repo}/zipball/{ref}` (zip) o `tarball`.
- Leer archivos y carpetas: `GET /repos/{owner}/{repo}/contents/{path}` y `git/trees?recursive=1`.
- Editar archivos y hacer commit en el servidor: `PUT /repos/{owner}/{repo}/contents/{path}` o GraphQL `createCommitOnBranch` (varios archivos, firmado).
- Crear ramas, fusionar, etc. con la API (ver api-rest-graphql.md).
- Sirve para un «modo sin git» en el que la persona trabaja directamente contra GitHub, como en la web.

### Recomendación

- Git instalado es el camino principal (rendimiento, hooks, LFS, credenciales, compatibilidad total).
- dulwich como motor de respaldo si no hay git, o para operaciones de solo lectura muy frecuentes si se quisiera evitar lanzar procesos.
- Modo «solo API» para editar sin clonar.

## Fuentes

- https://git-scm.com/docs/git-status (formato porcelain v2)
- https://git-scm.com/docs/git-config (GIT_CONFIG_COUNT, http.extraHeader, credential.helper)
- https://git-scm.com/docs/gitcredentials
- https://git-scm.com/docs/git-merge-tree
- https://git-scm.com/docs/git (variables de entorno GIT_TERMINAL_PROMPT, GIT_OPTIONAL_LOCKS, GIT_ASKPASS)
- https://github.com/git-for-windows/git/releases (MinGit)
- https://github.com/actions/checkout (uso de extraheader)
- https://pypi.org/project/dulwich/ , https://pypi.org/project/pygit2/ , https://pypi.org/project/GitPython/
- Consulta del índice JSON de PyPI y de la rueda de dulwich 1.2.21 hecha el 21 de noviembre de 2026.
