# Inventario de la API REST y GraphQL de GitHub

Investigación del 21 de noviembre de 2026. La base REST es `https://api.github.com` (en Enterprise Server, `https://HOST/api/v3`). GraphQL: `https://api.github.com/graphql`.

Notación: cada línea es «MÉTODO ruta: qué hace». `{owner}` y `{repo}` son el propietario y el repositorio. Las rutas están en la referencia oficial https://docs.github.com/en/rest; si una ruta no aparece allí, tratarla como no verificada.

Cuando gh CLI no tiene comando propio, todo esto se puede probar con `gh api RUTA` (útil para experimentar).

## Parte 1. Reglas generales

### Cabeceras

- `Accept: application/vnd.github+json` (por defecto).
- `X-GitHub-Api-Version: 2026-03-10` (o `2022-11-28`; ver autenticacion.md).
- `Authorization: Bearer TOKEN`.
- `User-Agent` obligatorio.
- Tipos de contenido especiales con `Accept`:
  - `application/vnd.github.raw+json`: contenido en bruto (archivos, cuerpo de issues sin procesar).
  - `application/vnd.github.html+json`: cuerpo en HTML ya renderizado (`body_html`). Muy útil para mostrar issues y comentarios en un visor HTML accesible.
  - `application/vnd.github.text+json`: cuerpo en texto plano (`body_text`). Útil para leer con voz.
  - `application/vnd.github.full+json`: las tres versiones.
  - `application/vnd.github.diff` y `application/vnd.github.patch`: diff o patch de un commit, comparación o PR.
  - `application/vnd.github.sha`: solo el SHA de un commit.
  - `application/octet-stream`: descargar un asset de release.

### Paginación

- Parámetros `per_page` (máximo 100, por defecto 30) y `page`.
- Usar siempre la cabecera `Link` con `rel="next"`, `rel="prev"`, `rel="first"` y `rel="last"`. No construir URLs a mano: algunos endpoints paginan por cursor (`before`, `after`, `since`).
- `requests` expone `response.links["next"]["url"]`; en httpx hay que parsearla.
- Las búsquedas devuelven como máximo 1.000 resultados en total (`total_count` puede ser mayor; `incomplete_results` indica tiempo agotado).
- Para mostrar «página X de Y» accesible, leer `rel="last"` y su número de página.
- Ordenar de forma estable al paginar (las órdenes por `updated` pueden mover elementos de una página a otra).

### Límites de uso (rate limits)

- Primarios (REST):
  - Sin autenticar: 60 peticiones por hora y por IP.
  - Usuario autenticado (PAT, OAuth, token de usuario de GitHub App): 5.000 por hora.
  - Apps de organizaciones Enterprise Cloud: 15.000 por hora.
  - GITHUB_TOKEN de Actions: 1.000 por hora por repositorio.
  - La búsqueda tiene su propio cupo: 30 peticiones por minuto autenticado (10 sin autenticar); la búsqueda de código, 10 por minuto.
- Primario GraphQL: 5.000 **puntos** por hora para usuarios. El coste de una consulta se calcula sumando las peticiones de cada conexión suponiendo que se llenan los `first`/`last`, dividiendo entre 100 y redondeando (mínimo 1).
  - Cada conexión necesita `first` o `last` entre 1 y 100; máximo 500.000 nodos por consulta.
  - Las consultas de más de 10 segundos se cortan con 502 o 504 y penalizan.
  - Consultar `rateLimit { limit remaining used resetAt cost }`.
- Secundarios (comunes a REST y GraphQL):
  - Máximo 100 peticiones simultáneas.
  - 900 puntos por minuto en REST y 2.000 en GraphQL. Un GET cuesta 1 punto; POST, PATCH, PUT y DELETE cuestan 5; una consulta GraphQL 1 y una mutación 5.
  - 90 segundos de CPU por minuto real (60 como máximo de GraphQL).
  - Creación de contenido: unas 80 por minuto y 500 por hora (menos en algunos endpoints).
  - 2.000 peticiones de token OAuth por hora.
- Cabeceras de respuesta: `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-used`, `x-ratelimit-reset` (segundos de época UTC), `x-ratelimit-resource` (core, search, graphql, code_search...), y `retry-after` en límites secundarios.
- `GET /rate_limit` no gasta cuota primaria. Con la versión 2026-03-10 leer `resources.core`, `resources.search`, `resources.graphql`, etc. (ya no hay `rate`).
- Cómo tratarlos:
  - Respuesta 403 o 429.
  - Si hay `retry-after`, esperar esos segundos.
  - Si `x-ratelimit-remaining` es 0, esperar hasta `x-ratelimit-reset`.
  - Si no hay ninguna de las dos, esperar al menos 1 minuto y luego reintentar con espera exponencial, con un número máximo de reintentos.
  - No seguir haciendo peticiones mientras se está limitado: GitHub puede bloquear la integración.
  - Hacer las peticiones en serie (una cola), no en paralelo, y esperar al menos 1 segundo entre peticiones que modifican datos cuando sean muchas.
  - En la interfaz: anunciar «Límite de la API alcanzado. Se reanudará a las HH:MM» y mostrar el cupo restante en la barra de estado o en un diálogo de información.
- Fuente: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

### Peticiones condicionales (ETag)

- Guardar la cabecera `ETag` (o `Last-Modified`) de cada GET y enviarla después en `If-None-Match` (o `If-Modified-Since`).
- Si nada cambió, la respuesta es `304 Not Modified` sin cuerpo y **no gasta cuota primaria**, siempre que la petición lleve `Authorization`.
- Usar los mismos parámetros en cada sondeo: otros parámetros dan otro ETag.
- Respetar `X-Poll-Interval` (por ejemplo en notificaciones y eventos): no sondear más a menudo.
- Ideal para refrescar notificaciones, listas de PR, issues y ejecuciones de Actions en segundo plano.
- Implementación: una caché local (por ejemplo en SQLite o con hishel sobre httpx) que guarde ETag y cuerpo por URL.

### Otras buenas prácticas

- Seguir redirecciones: 301 (repositorio renombrado o transferido: actualizar la URL guardada), 302 y 307 (repetir en `Location`).
- Usar los campos `number`, `url` y `html_url` de las respuestas, no extraer datos de las URL.
- Los errores 422 traen `errors` con detalles por campo: mostrarlos en español junto al campo del formulario.
- Un 404 en un repositorio privado puede significar falta de permiso (GitHub no revela su existencia).
- Fuente: https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api

## Parte 2. Inventario REST por áreas

### Meta y utilidades

- GET /: raíz de la API.
- GET /meta: IPs de GitHub, claves y huellas SSH, versión instalada (Enterprise Server).
- GET /versions: versiones de API admitidas.
- GET /octocat y GET /zen: pruebas.
- GET /rate_limit: cupos.
- GET /emojis: lista de emojis con su URL.
- POST /markdown: renderizar Markdown (modo `markdown` o `gfm` con `context` owner/repo para enlazar #123 y @usuario).
- POST /markdown/raw: renderizar texto plano Markdown.
- GET /licenses, GET /licenses/{license}: licencias.
- GET /repos/{owner}/{repo}/license: licencia del repo.
- GET /gitignore/templates, GET /gitignore/templates/{name}: plantillas .gitignore.
- GET /codes_of_conduct, GET /codes_of_conduct/{key}.

### Usuarios

- GET /user: usuario autenticado. PATCH /user: editar perfil (nombre, bio, blog, empresa, ubicación, hireable, twitter_username).
- GET /users/{username}: perfil público. GET /user/{account_id}: por id.
- GET /users: listar todos (paginación por `since`).
- GET /users/{username}/hovercard: información contextual.
- Correos: GET /user/emails, POST /user/emails, DELETE /user/emails, GET /user/public_emails, PATCH /user/email/visibility.
- Seguidores: GET /user/followers, GET /user/following, GET /users/{username}/followers, GET /users/{username}/following, GET /user/following/{username} (comprobar), PUT /user/following/{username} (seguir), DELETE /user/following/{username}.
- Claves SSH: GET /user/keys, POST /user/keys, GET /user/keys/{key_id}, DELETE /user/keys/{key_id}, GET /users/{username}/keys.
- Claves SSH de firma: GET /user/ssh_signing_keys, POST /user/ssh_signing_keys, GET y DELETE /user/ssh_signing_keys/{id}, GET /users/{username}/ssh_signing_keys.
- Claves GPG: GET /user/gpg_keys, POST /user/gpg_keys, GET y DELETE /user/gpg_keys/{gpg_key_id}, GET /users/{username}/gpg_keys.
- Bloqueos: GET /user/blocks, GET /user/blocks/{username}, PUT /user/blocks/{username}, DELETE /user/blocks/{username}.
- Cuentas sociales: GET /user/social_accounts, POST /user/social_accounts, DELETE /user/social_accounts, GET /users/{username}/social_accounts.
- Interacciones (limitar quién comenta): GET, PUT y DELETE /user/interaction-limits.
- Instalaciones de apps visibles: GET /user/installations, GET /user/installations/{installation_id}/repositories.
- Atestaciones: GET /users/{username}/attestations/{subject_digest}.

### Repositorios

- Listar: GET /user/repos (filtros `visibility`, `affiliation`, `type`, `sort`), GET /users/{username}/repos, GET /orgs/{org}/repos, GET /repositories (todos los públicos).
- Crear: POST /user/repos, POST /orgs/{org}/repos, POST /repos/{template_owner}/{template_repo}/generate (desde plantilla).
- GET /repos/{owner}/{repo}: datos. PATCH /repos/{owner}/{repo}: editar (nombre, descripción, web, visibilidad, rama por defecto, issues, wiki, projects, discussions, merges permitidos, borrar rama al fusionar, archivar, plantilla, seguridad). DELETE /repos/{owner}/{repo}: borrar (scope `delete_repo`).
- POST /repos/{owner}/{repo}/transfer: transferir.
- Temas: GET y PUT /repos/{owner}/{repo}/topics.
- Lenguajes: GET /repos/{owner}/{repo}/languages.
- Etiquetas git (tags) resumidas: GET /repos/{owner}/{repo}/tags.
- Equipos con acceso: GET /repos/{owner}/{repo}/teams.
- Contribuidores: GET /repos/{owner}/{repo}/contributors.
- Activity: GET /repos/{owner}/{repo}/activity (historial de pushes, force pushes y borrados de ramas).
- Seguridad: PUT y DELETE /repos/{owner}/{repo}/vulnerability-alerts, GET /repos/{owner}/{repo}/vulnerability-alerts, PUT y DELETE /repos/{owner}/{repo}/automated-security-fixes, GET /repos/{owner}/{repo}/private-vulnerability-reporting, PUT y DELETE de lo mismo.
- POST /repos/{owner}/{repo}/dispatches: evento repository_dispatch.
- Autolinks: GET y POST /repos/{owner}/{repo}/autolinks, GET y DELETE /repos/{owner}/{repo}/autolinks/{autolink_id}.
- Propiedades personalizadas: GET y PATCH /repos/{owner}/{repo}/properties/values.
- Comunidad: GET /repos/{owner}/{repo}/community/profile (README, licencia, CONTRIBUTING, código de conducta...).
- CODEOWNERS: GET /repos/{owner}/{repo}/codeowners/errors.
- Descargar archivo comprimido: GET /repos/{owner}/{repo}/zipball/{ref} y GET /repos/{owner}/{repo}/tarball/{ref} (redirige a codeload.github.com). Alternativa a clonar si no hay git.
- Tipos de issue del repo y estados de planificación: aparecen en la navegación de la referencia (Repositories > Issue types, Planning statuses); verificar rutas.

### Contenidos (archivos)

- GET /repos/{owner}/{repo}/readme, GET /repos/{owner}/{repo}/readme/{dir}: README (con `Accept` html para verlo renderizado).
- GET /repos/{owner}/{repo}/contents/{path}?ref=RAMA: archivo (contenido en base64) o lista de una carpeta. Con 2026-03-10, los submódulos tienen `type: "submodule"`. Archivos de hasta 1 MB con JSON; de 1 a 100 MB solo con `Accept: application/vnd.github.raw+json`.
- PUT /repos/{owner}/{repo}/contents/{path}: crear o actualizar archivo (mensaje de commit, contenido base64, `sha` del blob anterior si se actualiza, rama, autor). Base de «editar archivo en la web».
- DELETE /repos/{owner}/{repo}/contents/{path}: borrar archivo (con `sha` y mensaje).
- Para cambiar varios archivos en un solo commit sin git: usar la API Git database (abajo) o la mutación GraphQL `createCommitOnBranch` (recomendada: firma el commit como verificado).
- Árbol completo del repo (navegador de archivos): GET /repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1 (si viene `truncated: true`, recorrer carpeta a carpeta).

### Git database (bajo nivel)

- Blobs: POST /repos/{owner}/{repo}/git/blobs, GET /repos/{owner}/{repo}/git/blobs/{file_sha}.
- Árboles: POST /repos/{owner}/{repo}/git/trees, GET /repos/{owner}/{repo}/git/trees/{tree_sha}.
- Commits: POST /repos/{owner}/{repo}/git/commits, GET /repos/{owner}/{repo}/git/commits/{commit_sha}.
- Referencias: GET /repos/{owner}/{repo}/git/ref/{ref}, GET /repos/{owner}/{repo}/git/matching-refs/{ref}, POST /repos/{owner}/{repo}/git/refs, PATCH y DELETE /repos/{owner}/{repo}/git/refs/{ref}.
- Etiquetas anotadas: POST /repos/{owner}/{repo}/git/tags, GET /repos/{owner}/{repo}/git/tags/{tag_sha}.

### Ramas

- GET /repos/{owner}/{repo}/branches (filtro `protected`), GET /repos/{owner}/{repo}/branches/{branch}.
- POST /repos/{owner}/{repo}/branches/{branch}/rename: renombrar.
- POST /repos/{owner}/{repo}/merges: fusionar una rama en otra en el servidor.
- POST /repos/{owner}/{repo}/merge-upstream: sincronizar un fork con su origen («Sync fork»).
- Crear rama: POST /repos/{owner}/{repo}/git/refs con `ref: refs/heads/NOMBRE` y `sha`. Borrar: DELETE /repos/{owner}/{repo}/git/refs/heads/NOMBRE.
- GET /repos/{owner}/{repo}/commits/{commit_sha}/branches-where-head.

### Protección de ramas (clásica)

- GET, PUT y DELETE /repos/{owner}/{repo}/branches/{branch}/protection.
- Subrecursos (GET, POST, PATCH, DELETE según el caso) bajo .../protection/:
  - `enforce_admins`
  - `required_pull_request_reviews`
  - `required_signatures`
  - `required_status_checks` y `required_status_checks/contexts`
  - `restrictions`, `restrictions/apps`, `restrictions/teams`, `restrictions/users`

### Rulesets (reglas, el sistema nuevo)

- Repositorio: GET y POST /repos/{owner}/{repo}/rulesets, GET, PUT y DELETE /repos/{owner}/{repo}/rulesets/{ruleset_id}.
- Historial: GET /repos/{owner}/{repo}/rulesets/{ruleset_id}/history y .../history/{version_id}.
- Reglas que se aplican a una rama: GET /repos/{owner}/{repo}/rules/branches/{branch}.
- Evaluaciones (rule suites): GET /repos/{owner}/{repo}/rulesets/rule-suites, GET .../rule-suites/{rule_suite_id}.
- Organización: GET y POST /orgs/{org}/rulesets, GET, PUT y DELETE /orgs/{org}/rulesets/{ruleset_id}, GET /orgs/{org}/rulesets/rule-suites.

### Commits

- GET /repos/{owner}/{repo}/commits (filtros `sha` rama, `path` archivo, `author`, `committer`, `since`, `until`): historial.
- GET /repos/{owner}/{repo}/commits/{ref}: detalle con `files` y `patch` por archivo (máximo 300 archivos; paginar si hay más). Con `Accept: application/vnd.github.diff` devuelve el diff entero.
- GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls: PR asociados.
- Comparar: GET /repos/{owner}/{repo}/compare/{basehead} con `basehead` = `BASE...HEAD` (también entre forks: `usuario:rama`). Devuelve `ahead_by`, `behind_by`, `commits`, `files`.
- Comentarios de commit: GET /repos/{owner}/{repo}/comments, GET, PATCH y DELETE /repos/{owner}/{repo}/comments/{comment_id}, GET y POST /repos/{owner}/{repo}/commits/{commit_sha}/comments.
- Estados de commit (statuses): GET /repos/{owner}/{repo}/commits/{ref}/status (combinado), GET /repos/{owner}/{repo}/commits/{ref}/statuses, POST /repos/{owner}/{repo}/statuses/{sha}.
- No hay `git blame` en REST: usar GraphQL (`blame` en un objeto Commit) o git local.

### Issues

- GET /issues (todas las asignadas), GET /user/issues, GET /orgs/{org}/issues, GET /repos/{owner}/{repo}/issues (filtros `state`, `labels`, `assignee`, `creator`, `mentioned`, `milestone`, `type`, `since`, `sort`, `direction`). Ojo: incluye los PR (tienen `pull_request`); filtrarlos.
- POST /repos/{owner}/{repo}/issues: crear (título, cuerpo, `assignees`, etiquetas, hito, `type`). Con 2026-03-10 ya no existe `assignee` singular.
- GET y PATCH /repos/{owner}/{repo}/issues/{issue_number}: ver y editar (estado `open` o `closed`, `state_reason`: `completed`, `not_planned`, `duplicate`, `reopened`).
- Bloquear: PUT y DELETE /repos/{owner}/{repo}/issues/{issue_number}/lock (motivo: off-topic, too heated, resolved, spam).
- Asignados: GET /repos/{owner}/{repo}/assignees, GET /repos/{owner}/{repo}/assignees/{assignee}, POST y DELETE /repos/{owner}/{repo}/issues/{issue_number}/assignees.
- Comentarios: GET /repos/{owner}/{repo}/issues/comments, GET /repos/{owner}/{repo}/issues/{issue_number}/comments, POST en la misma ruta, GET, PATCH y DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}. Fijar comentario: hay rutas `.../pin` en versiones recientes (verificar).
- Eventos: GET /repos/{owner}/{repo}/issues/events, GET /repos/{owner}/{repo}/issues/events/{event_id}, GET /repos/{owner}/{repo}/issues/{issue_number}/events.
- Línea de tiempo completa: GET /repos/{owner}/{repo}/issues/{issue_number}/timeline (comentarios, referencias cruzadas, cambios de etiqueta, commits...). Base de la vista de conversación.
- Sub-issues: GET /repos/{owner}/{repo}/issues/{issue_number}/sub_issues, POST en la misma ruta, DELETE /repos/{owner}/{repo}/issues/{issue_number}/sub_issue, PATCH /repos/{owner}/{repo}/issues/{issue_number}/sub_issues/priority, GET /repos/{owner}/{repo}/issues/{issue_number}/parent.
- Dependencias: GET /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by, POST en la misma ruta, DELETE .../blocked_by/{issue_id}, GET .../dependencies/blocking.
- Tipos de issue de organización: GET, POST /orgs/{org}/issue-types, PUT y DELETE /orgs/{org}/issue-types/{issue_type_id}.
- Campos de issue (issue fields) y sus valores: nuevas secciones de la referencia (Organizations > Issue fields, Issues > Issue field values); verificar rutas.
- Transferir un issue: solo GraphQL (`transferIssue`). Fijar un issue: solo GraphQL (`pinIssue`, `unpinIssue`).

### Etiquetas (labels)

- GET y POST /repos/{owner}/{repo}/labels, GET, PATCH y DELETE /repos/{owner}/{repo}/labels/{name}.
- En un issue: GET, POST (añadir), PUT (sustituir) y DELETE (todas) /repos/{owner}/{repo}/issues/{issue_number}/labels, DELETE .../labels/{name}.
- GET /repos/{owner}/{repo}/milestones/{milestone_number}/labels.

### Hitos (milestones)

- GET y POST /repos/{owner}/{repo}/milestones, GET, PATCH y DELETE /repos/{owner}/{repo}/milestones/{milestone_number}.

### Reacciones

- Contenidos posibles: `+1`, `-1`, `laugh`, `confused`, `heart`, `hooray`, `rocket`, `eyes`. Nombres en español para la interfaz: pulgar arriba, pulgar abajo, risa, confusión, corazón, celebración, cohete, ojos.
- Issue: GET y POST /repos/{owner}/{repo}/issues/{issue_number}/reactions, DELETE .../reactions/{reaction_id}.
- Comentario de issue: GET y POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions, DELETE .../{reaction_id}.
- Comentario de commit: /repos/{owner}/{repo}/comments/{comment_id}/reactions.
- Comentario de revisión de PR: /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions.
- Release: /repos/{owner}/{repo}/releases/{release_id}/reactions.
- Discusiones de equipo: /orgs/{org}/teams/{team_slug}/discussions/... (en retirada).

### Pull requests

- GET /repos/{owner}/{repo}/pulls (filtros `state`, `head`, `base`, `sort`, `direction`).
- POST /repos/{owner}/{repo}/pulls: crear (título, `head`, `base`, cuerpo, `draft`, `maintainer_can_modify`; o `issue` para convertir un issue).
- GET y PATCH /repos/{owner}/{repo}/pulls/{pull_number}: ver (incluye `mergeable`, `mergeable_state`, `rebaseable`, contadores) y editar (título, cuerpo, estado, base).
- GET /repos/{owner}/{repo}/pulls/{pull_number}/commits (máximo 250).
- GET /repos/{owner}/{repo}/pulls/{pull_number}/files (máximo 3.000 archivos, con `patch` por archivo, `status` added, removed, modified, renamed, `additions`, `deletions`).
- Diff completo: GET /repos/{owner}/{repo}/pulls/{pull_number} con `Accept: application/vnd.github.diff`.
- Fusionar: GET /repos/{owner}/{repo}/pulls/{pull_number}/merge (¿ya fusionado? 204 o 404), PUT en la misma ruta con `merge_method` (`merge`, `squash`, `rebase`), `commit_title`, `commit_message`, `sha` (para evitar fusionar si cambió).
- PUT /repos/{owner}/{repo}/pulls/{pull_number}/update-branch: actualizar la rama con la base.
- Revisores solicitados: GET, POST y DELETE /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers (usuarios y equipos). Pedir revisión a Copilot: ver la sección «Copilot code review» de la referencia.
- Reviews (revisiones):
  - GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews.
  - POST en la misma ruta: crear revisión con `event` (`APPROVE`, `REQUEST_CHANGES`, `COMMENT`; sin `event` queda pendiente), `body` y `comments` (lista de comentarios por línea con `path`, `line`, `side` LEFT o RIGHT, `start_line` y `start_side` para rangos).
  - GET, PUT (editar cuerpo) y DELETE (solo pendiente) /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}.
  - GET .../reviews/{review_id}/comments.
  - POST .../reviews/{review_id}/events: enviar una revisión pendiente.
  - PUT .../reviews/{review_id}/dismissals: descartar una revisión.
- Comentarios de revisión (en líneas del diff):
  - GET /repos/{owner}/{repo}/pulls/comments (todos del repo), GET /repos/{owner}/{repo}/pulls/{pull_number}/comments.
  - POST /repos/{owner}/{repo}/pulls/{pull_number}/comments: comentario en línea (`commit_id`, `path`, `line`, `side`, `start_line`, `start_side`, o `subject_type: file` para comentar el archivo entero). Sugerencias de cambio: bloque ```suggestion en el cuerpo.
  - POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies: responder en el hilo.
  - GET, PATCH y DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}.
  - Resolver o reabrir hilos: solo GraphQL (`resolveReviewThread`, `unresolveReviewThread`).
- Solo GraphQL: marcar listo para revisión (`markPullRequestReadyForReview`), pasar a borrador (`convertPullRequestToDraft`), auto-merge (`enablePullRequestAutoMerge`, `disablePullRequestAutoMerge`), cola de fusión (`enqueuePullRequest`), marcar archivo como visto (`markFileAsViewed`, `unmarkFileAsViewed`).
- Novedades en la referencia (noviembre de 2026):
  - Stacks de PR (PR apilados): GET y POST /repos/{owner}/{repo}/stacks, GET /repos/{owner}/{repo}/stacks/{stack_number}, POST .../stacks/{stack_number}/add, POST .../stacks/{stack_number}/unstack.
  - «Agent Merge» y «Copilot code review»: secciones nuevas de Pull requests; verificar rutas.

### Checks (comprobaciones)

- Check runs: POST /repos/{owner}/{repo}/check-runs, GET y PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}, GET .../check-runs/{check_run_id}/annotations (errores por archivo y línea: muy útil para anunciar fallos), POST .../check-runs/{check_run_id}/rerequest, GET /repos/{owner}/{repo}/commits/{ref}/check-runs, GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs.
- Check suites: POST /repos/{owner}/{repo}/check-suites, PATCH /repos/{owner}/{repo}/check-suites/preferences, GET /repos/{owner}/{repo}/check-suites/{check_suite_id}, POST .../rerequest, GET /repos/{owner}/{repo}/commits/{ref}/check-suites.
- Para el resumen de un PR («3 comprobaciones correctas, 1 fallida»): combinar check-runs y statuses del último commit, o GraphQL `statusCheckRollup`.

### GitHub Actions

- Workflows: GET /repos/{owner}/{repo}/actions/workflows, GET /repos/{owner}/{repo}/actions/workflows/{workflow_id} (id o nombre de archivo), PUT .../enable, PUT .../disable, POST .../dispatches (lanzar a mano con `ref` e `inputs`; con 2026-03-10 devuelve 200 con los datos de la ejecución), GET .../timing.
- Ejecuciones (runs):
  - GET /repos/{owner}/{repo}/actions/runs (filtros `actor`, `branch`, `event`, `status`, `created`, `head_sha`), GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs.
  - GET y DELETE /repos/{owner}/{repo}/actions/runs/{run_id}.
  - GET .../runs/{run_id}/attempts/{attempt_number}.
  - POST .../runs/{run_id}/cancel, POST .../force-cancel.
  - POST .../runs/{run_id}/rerun, POST .../rerun-failed-jobs.
  - GET .../runs/{run_id}/logs (zip de todos los registros), DELETE .../logs.
  - GET .../runs/{run_id}/attempts/{attempt_number}/logs.
  - GET .../runs/{run_id}/approvals, POST .../approve (forks), GET .../pending_deployments, POST .../pending_deployments (aprobar o rechazar despliegues), POST .../deployment_protection_rule.
  - GET .../runs/{run_id}/timing (uso).
- Trabajos (jobs):
  - GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs (filtro `filter=latest|all`), GET .../runs/{run_id}/attempts/{attempt_number}/jobs.
  - GET /repos/{owner}/{repo}/actions/jobs/{job_id}: incluye `steps` con nombre, estado, conclusión y tiempos. Base del árbol «ejecución, trabajo, paso».
  - GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs: registro en texto plano del trabajo (redirige a una URL temporal). Las líneas llevan marca de tiempo ISO al principio y marcadores `##[group]`, `##[endgroup]`, `##[error]`, `##[warning]` que sirven para dividir por pasos y saltar a errores.
  - POST /repos/{owner}/{repo}/actions/jobs/{job_id}/rerun.
- Artefactos: GET /repos/{owner}/{repo}/actions/artifacts (filtro `name`), GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts, GET y DELETE /repos/{owner}/{repo}/actions/artifacts/{artifact_id}, GET .../artifacts/{artifact_id}/zip (descarga).
- Cachés: GET /repos/{owner}/{repo}/actions/caches, DELETE /repos/{owner}/{repo}/actions/caches?key=..., DELETE .../caches/{cache_id}, GET /repos/{owner}/{repo}/actions/cache/usage, GET /orgs/{org}/actions/cache/usage y .../usage-by-repository.
- Secretos (los valores se cifran con la clave pública del repo usando libsodium sealed box: hace falta PyNaCl):
  - GET /repos/{owner}/{repo}/actions/secrets/public-key, GET /repos/{owner}/{repo}/actions/secrets, GET, PUT y DELETE /repos/{owner}/{repo}/actions/secrets/{secret_name}.
  - Entornos: /repos/{owner}/{repo}/environments/{environment_name}/secrets/... (mismas operaciones).
  - Organización: GET /orgs/{org}/actions/secrets/public-key, GET /orgs/{org}/actions/secrets, GET, PUT, DELETE /orgs/{org}/actions/secrets/{secret_name}, y .../repositories para repos seleccionados.
  - Secretos de organización disponibles para un repo: GET /repos/{owner}/{repo}/actions/organization-secrets.
- Variables: GET y POST /repos/{owner}/{repo}/actions/variables, GET, PATCH y DELETE .../variables/{name}; lo mismo en /repos/{owner}/{repo}/environments/{environment_name}/variables y /orgs/{org}/actions/variables; GET /repos/{owner}/{repo}/actions/organization-variables.
- Runners autoalojados: GET /repos/{owner}/{repo}/actions/runners, GET .../runners/downloads, POST .../runners/registration-token, POST .../runners/remove-token, GET y DELETE .../runners/{runner_id}, etiquetas en .../runners/{runner_id}/labels; equivalentes en /orgs/{org}/actions/runners y grupos en /orgs/{org}/actions/runner-groups.
- Runners alojados por GitHub (organización): /orgs/{org}/actions/hosted-runners.
- Permisos: GET y PUT /repos/{owner}/{repo}/actions/permissions, .../permissions/access, .../permissions/selected-actions, .../permissions/workflow (permisos del GITHUB_TOKEN); equivalentes en /orgs/{org}/actions/permissions.
- OIDC: /repos/{owner}/{repo}/actions/oidc/customization/sub.
- Grupos de concurrencia: nueva sección de la referencia; verificar rutas.
- Uso y facturación: secciones Billing (Budgets, Billing usage), por ejemplo GET /users/{username}/settings/billing/usage (verificar).

### Releases y assets

- GET y POST /repos/{owner}/{repo}/releases (crear: `tag_name`, `target_commitish`, `name`, `body`, `draft`, `prerelease`, `generate_release_notes`, `make_latest`, `discussion_category_name`).
- GET /repos/{owner}/{repo}/releases/latest, GET /repos/{owner}/{repo}/releases/tags/{tag}.
- GET, PATCH y DELETE /repos/{owner}/{repo}/releases/{release_id}.
- POST /repos/{owner}/{repo}/releases/generate-notes: generar notas automáticas (para previsualizarlas antes de publicar).
- Assets: GET /repos/{owner}/{repo}/releases/{release_id}/assets, GET, PATCH y DELETE /repos/{owner}/{repo}/releases/assets/{asset_id} (descarga con `Accept: application/octet-stream`).
- Subir asset: POST `https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name=ARCHIVO&label=...` con el binario en el cuerpo y su `Content-Type`. Usar la URL `upload_url` de la release (es una plantilla RFC 6570: quitar `{?name,label}`).
- Releases inmutables: ajustes en /orgs/{org}/settings/immutable-releases (verificar).

### Etiquetas git (tags)

- Listar: GET /repos/{owner}/{repo}/tags. Crear ligera: POST /repos/{owner}/{repo}/git/refs con `refs/tags/NOMBRE`. Anotada: POST /repos/{owner}/{repo}/git/tags y luego la ref. Borrar: DELETE /repos/{owner}/{repo}/git/refs/tags/NOMBRE.
- La protección de tags antigua (tag protection) se retiró en favor de los rulesets.

### Gists

- GET /gists (propias), GET /gists/public, GET /gists/starred, GET /users/{username}/gists.
- POST /gists (archivos, descripción, `public`).
- GET, PATCH y DELETE /gists/{gist_id}.
- GET /gists/{gist_id}/commits, GET /gists/{gist_id}/{sha} (revisión concreta).
- GET y POST /gists/{gist_id}/forks.
- GET, PUT y DELETE /gists/{gist_id}/star.
- Comentarios: GET y POST /gists/{gist_id}/comments, GET, PATCH y DELETE /gists/{gist_id}/comments/{comment_id}.
- Con 2026-03-10 el objeto base ya no incluye `history` ni `forks`.
- Una gist también es un repo git: `https://gist.github.com/{gist_id}.git`.

### Notificaciones

- GET /notifications (parámetros `all`, `participating`, `since`, `before`; sondear con `If-Modified-Since` y respetar `X-Poll-Interval`).
- PUT /notifications: marcar todas como leídas (`last_read_at`).
- GET /repos/{owner}/{repo}/notifications, PUT /repos/{owner}/{repo}/notifications.
- GET y PATCH /notifications/threads/{thread_id} (PATCH = marcar como leída), DELETE /notifications/threads/{thread_id} (marcar como hecha).
- GET, PUT y DELETE /notifications/threads/{thread_id}/subscription (silenciar un hilo).
- Cada notificación trae `reason` (assign, author, comment, ci_activity, invitation, manual, mention, review_requested, security_alert, state_change, subscribed, team_mention...), `subject` (título, tipo Issue, PullRequest, Release, Discussion, CheckSuite, Commit, RepositoryVulnerabilityAlert; y `url` de la API, no la web) y `repository`. Traducir `reason` y el tipo al español.
- Las notificaciones guardadas (save) y los filtros personalizados de la bandeja web no están en la API (verificar).

### Actividad: estrellas, seguimiento y eventos

- Estrellas: GET /user/starred, GET /users/{username}/starred, GET /user/starred/{owner}/{repo} (comprobar), PUT y DELETE /user/starred/{owner}/{repo}, GET /repos/{owner}/{repo}/stargazers. Listas de estrellas (Lists): solo web o GraphQL (verificar).
- Watching (seguir repos): GET /user/subscriptions, GET /users/{username}/subscriptions, GET /repos/{owner}/{repo}/subscribers, GET, PUT y DELETE /repos/{owner}/{repo}/subscription (`subscribed`, `ignored`). La suscripción personalizada por tipo (solo releases, issues, PR...) no está en REST; GraphQL `updateSubscription` admite estados básicos (verificar).
- Eventos (feeds): GET /events, GET /repos/{owner}/{repo}/events, GET /networks/{owner}/{repo}/events, GET /orgs/{org}/events, GET /users/{username}/events, GET /users/{username}/events/public, GET /users/{username}/events/orgs/{org}, GET /users/{username}/received_events (el «feed» de inicio), GET /users/{username}/received_events/public. Solo los últimos 90 días y máximo 300 eventos.
- GET /feeds: URLs de los feeds Atom.

### Forks

- GET /repos/{owner}/{repo}/forks, POST /repos/{owner}/{repo}/forks (`organization`, `name`, `default_branch_only`).
- Sincronizar: POST /repos/{owner}/{repo}/merge-upstream.

### Colaboradores e invitaciones

- GET /repos/{owner}/{repo}/collaborators (filtro `affiliation`, `permission`), GET /repos/{owner}/{repo}/collaborators/{username} (comprobar), PUT (invitar o cambiar permiso: pull, triage, push, maintain, admin o rol personalizado), DELETE.
- GET /repos/{owner}/{repo}/collaborators/{username}/permission.
- Invitaciones del repo: GET /repos/{owner}/{repo}/invitations, PATCH y DELETE /repos/{owner}/{repo}/invitations/{invitation_id}.
- Invitaciones recibidas: GET /user/repository_invitations, PATCH (aceptar) y DELETE (rechazar) /user/repository_invitations/{invitation_id}.

### Organizaciones y miembros

- GET /user/orgs, GET /users/{username}/orgs, GET /organizations, GET y PATCH /orgs/{org}, DELETE /orgs/{org}.
- Miembros: GET /orgs/{org}/members, GET y DELETE /orgs/{org}/members/{username}, GET /orgs/{org}/public_members, PUT y DELETE /orgs/{org}/public_members/{username}.
- Membresías: GET, PUT y DELETE /orgs/{org}/memberships/{username}; propias: GET /user/memberships/orgs, GET y PATCH /user/memberships/orgs/{org} (aceptar invitación).
- Invitaciones: GET y POST /orgs/{org}/invitations, DELETE /orgs/{org}/invitations/{invitation_id}, GET /orgs/{org}/failed_invitations, GET /orgs/{org}/invitations/{invitation_id}/teams.
- Colaboradores externos: GET /orgs/{org}/outside_collaborators, PUT y DELETE /orgs/{org}/outside_collaborators/{username}.
- Bloqueos: GET /orgs/{org}/blocks, GET, PUT y DELETE /orgs/{org}/blocks/{username}.
- Roles de organización: /orgs/{org}/organization-roles y asignaciones a usuarios y equipos.
- Gestores de seguridad: /orgs/{org}/security-managers (en transición a roles).
- Webhooks de organización: GET y POST /orgs/{org}/hooks, GET, PATCH y DELETE /orgs/{org}/hooks/{hook_id}, .../config, .../deliveries, POST .../pings.
- Propiedades personalizadas: /orgs/{org}/properties/schema y /orgs/{org}/properties/values.
- PAT de la organización: GET /orgs/{org}/personal-access-tokens, GET /orgs/{org}/personal-access-token-requests, POST para aprobar o denegar.
- Instalaciones de apps: GET /orgs/{org}/installations.
- Límites de interacción: GET, PUT y DELETE /orgs/{org}/interaction-limits.
- Otras secciones nuevas: API Insights, Artifact metadata, Network configurations, Issue fields, Issue types.

### Equipos (teams)

- GET y POST /orgs/{org}/teams (con 2026-03-10 ya no se envía `permission` al crear), GET, PATCH y DELETE /orgs/{org}/teams/{team_slug}.
- Miembros: GET /orgs/{org}/teams/{team_slug}/members, GET, PUT y DELETE /orgs/{org}/teams/{team_slug}/memberships/{username}.
- Repos del equipo: GET /orgs/{org}/teams/{team_slug}/repos, GET, PUT y DELETE /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}.
- Subequipos: GET /orgs/{org}/teams/{team_slug}/teams.
- Invitaciones pendientes: GET /orgs/{org}/teams/{team_slug}/invitations.
- Equipos propios: GET /user/teams.
- Las discusiones de equipo se retiraron (sustituidas por Discussions de organización).

### Projects (v2)

- Desde 2025 hay API REST para Projects además de GraphQL:
  - GET /orgs/{org}/projectsV2, GET /orgs/{org}/projectsV2/{project_number}.
  - GET /users/{username}/projectsV2, GET /users/{username}/projectsV2/{project_number}.
  - Elementos: GET y POST /orgs/{org}/projectsV2/{project_number}/items, GET, PATCH y DELETE /orgs/{org}/projectsV2/{project_number}/items/{item_id}; lo mismo bajo /users/{username}/projectsV2/{project_number}/items.
  - Elementos según una vista guardada: GET /orgs/{org}/projectsV2/{project_number}/views/{view_number}/items.
  - Borradores: POST /orgs/{org}/projectsV2/{project_number}/drafts y POST /user/{user_id}/projectsV2/{project_number}/drafts.
  - Campos y vistas: la referencia tiene secciones Fields y Views (GET /orgs/{org}/projectsV2/{project_number}/fields, .../fields/{field_id}; creación de vistas: verificar).
- Crear y configurar proyectos, campos y la mayoría de cambios siguen siendo más completos en GraphQL (ver Parte 3).
- Scope necesario: `project` (o `read:project`). Los PAT fine-grained no acceden a projects de usuario.
- Los Projects clásicos y su API REST (/projects/...) se retiraron.

### Discussions

- Solo GraphQL (ver Parte 3). REST no tiene endpoints de discusiones de repositorio.

### Wiki

- No hay API. La wiki es un repo git aparte: `https://github.com/{owner}/{repo}.wiki.git`. Se clona, se editan los .md y se hace push. Solo existe si se ha creado la primera página en la web (si no, el clon falla).
- `has_wiki` en el repo indica si está activada.

### GitHub Pages

- GET, POST, PUT y DELETE /repos/{owner}/{repo}/pages (configurar origen: rama y carpeta, o `build_type: workflow`; dominio personalizado; HTTPS).
- GET /repos/{owner}/{repo}/pages/builds, POST (lanzar compilación), GET .../builds/latest, GET .../builds/{build_id}.
- POST /repos/{owner}/{repo}/pages/deployments, GET .../deployments/{pages_deployment_id}, POST .../cancel.
- GET /repos/{owner}/{repo}/pages/health (comprobación DNS).

### Webhooks de repositorio

- GET y POST /repos/{owner}/{repo}/hooks, GET, PATCH y DELETE /repos/{owner}/{repo}/hooks/{hook_id}.
- GET y PATCH .../hooks/{hook_id}/config.
- GET .../hooks/{hook_id}/deliveries, GET .../deliveries/{delivery_id}, POST .../deliveries/{delivery_id}/attempts (reenviar).
- POST .../hooks/{hook_id}/pings, POST .../hooks/{hook_id}/tests.

### Deploy keys

- GET y POST /repos/{owner}/{repo}/keys (`title`, `key`, `read_only`), GET y DELETE /repos/{owner}/{repo}/keys/{key_id}.

### Entornos y despliegues

- Entornos: GET /repos/{owner}/{repo}/environments, GET, PUT y DELETE /repos/{owner}/{repo}/environments/{environment_name} (revisores requeridos, temporizador de espera, política de ramas).
- Políticas de rama del entorno: /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies.
- Reglas de protección personalizadas: .../deployment_protection_rules.
- Despliegues: GET y POST /repos/{owner}/{repo}/deployments, GET y DELETE /repos/{owner}/{repo}/deployments/{deployment_id}.
- Estados: GET y POST /repos/{owner}/{repo}/deployments/{deployment_id}/statuses, GET .../statuses/{status_id}.

### Packages

- GET /user/packages?package_type=..., GET /orgs/{org}/packages, GET /users/{username}/packages.
- GET y DELETE /{user|orgs/{org}|users/{username}}/packages/{package_type}/{package_name}, POST .../restore.
- Versiones: GET .../versions, GET y DELETE .../versions/{package_version_id}, POST .../versions/{id}/restore.
- Tipos: npm, maven, rubygems, docker, nuget, container.
- Necesita PAT clásico (`read:packages`, `delete:packages`): los fine-grained no sirven.

### Code scanning

- GET /repos/{owner}/{repo}/code-scanning/alerts (filtros `state`, `severity`, `ref`, `tool_name`), GET y PATCH .../alerts/{alert_number} (descartar con motivo), GET .../alerts/{alert_number}/instances.
- Autofix con Copilot: GET y POST .../alerts/{alert_number}/autofix, POST .../autofix/commits.
- Análisis: GET .../code-scanning/analyses, GET y DELETE .../analyses/{analysis_id}.
- Subir SARIF: POST .../code-scanning/sarifs, GET .../sarifs/{sarif_id}.
- Configuración por defecto: GET y PATCH .../code-scanning/default-setup.
- CodeQL: bases de datos .../code-scanning/codeql/databases y análisis de variantes .../codeql/variant-analyses.
- Organización: GET /orgs/{org}/code-scanning/alerts.
- Configuraciones de seguridad (code security): /orgs/{org}/code-security/configurations.

### Dependabot

- Alertas: GET /repos/{owner}/{repo}/dependabot/alerts, GET y PATCH .../alerts/{alert_number} (descartar con motivo), GET /orgs/{org}/dependabot/alerts. Con 2026-03-10, usar `cvss_severities`.
- Secretos de Dependabot: /repos/{owner}/{repo}/dependabot/secrets (misma mecánica que los de Actions) y /orgs/{org}/dependabot/secrets.
- Grafo de dependencias: GET /repos/{owner}/{repo}/dependency-graph/sbom, GET /repos/{owner}/{repo}/dependency-graph/compare/{basehead} (revisión de dependencias en un PR), POST /repos/{owner}/{repo}/dependency-graph/snapshots.

### Secret scanning

- GET /repos/{owner}/{repo}/secret-scanning/alerts, GET y PATCH .../alerts/{alert_number} (resolver: false_positive, wont_fix, revoked, used_in_tests), GET .../alerts/{alert_number}/locations.
- Bypass de push protection: POST /repos/{owner}/{repo}/secret-scanning/push-protection-bypasses.
- Resumen de escaneo: GET /repos/{owner}/{repo}/secret-scanning/scan-history.
- Organización: GET /orgs/{org}/secret-scanning/alerts; patrones personalizados (sección Custom patterns).

### Avisos de seguridad (security advisories)

- Globales: GET /advisories, GET /advisories/{ghsa_id}.
- Del repositorio: GET y POST /repos/{owner}/{repo}/security-advisories, GET y PATCH .../security-advisories/{ghsa_id}, POST .../{ghsa_id}/cve (pedir CVE), POST .../{ghsa_id}/forks (fork privado temporal), POST /repos/{owner}/{repo}/security-advisories/reports (informar de una vulnerabilidad de forma privada).
- Organización: GET /orgs/{org}/security-advisories.

### Tráfico y estadísticas

- Tráfico (solo con permiso de push, últimos 14 días): GET /repos/{owner}/{repo}/traffic/views, GET .../traffic/clones, GET .../traffic/popular/paths, GET .../traffic/popular/referrers.
- Estadísticas (pueden responder 202 mientras se calculan: reintentar más tarde):
  - GET /repos/{owner}/{repo}/stats/contributors
  - GET /repos/{owner}/{repo}/stats/commit_activity
  - GET /repos/{owner}/{repo}/stats/code_frequency
  - GET /repos/{owner}/{repo}/stats/participation
  - GET /repos/{owner}/{repo}/stats/punch_card
- Presentarlas como texto o tablas pequeñas, no como gráficos.

### Búsqueda

- GET /search/repositories?q=... (calificadores: `user:`, `org:`, `language:`, `stars:>100`, `topic:`, `is:public`, `archived:false`, `fork:true`...).
- GET /search/code?q=... (requiere autenticación; calificadores `repo:`, `path:`, `language:`, `extension:`; cupo de 10 por minuto). La búsqueda de código nueva de la web (con expresiones regulares) no está en la API REST.
- GET /search/issues?q=... (issues y PR; `is:issue` o `is:pr`, `is:open`, `author:`, `assignee:`, `label:`, `review-requested:@me`, `involves:@me`...). GitHub está migrando a la búsqueda avanzada de issues con operadores AND y OR y paréntesis (`advanced_search=true`; verificar estado).
- GET /search/users?q=..., GET /search/commits?q=..., GET /search/topics?q=..., GET /search/labels?repository_id=...&q=....
- Resultados con `text_matches` si se pide `Accept: application/vnd.github.text-match+json`: fragmentos con la coincidencia, útiles para leer el contexto.

### Codespaces

- GET /user/codespaces, POST /user/codespaces, GET, PATCH y DELETE /user/codespaces/{codespace_name}, POST .../start, POST .../stop, POST .../exports, POST .../publish.
- GET y POST /repos/{owner}/{repo}/codespaces, GET /repos/{owner}/{repo}/codespaces/machines, GET .../codespaces/devcontainers, GET .../codespaces/new (valores por defecto).
- POST /repos/{owner}/{repo}/pulls/{pull_number}/codespaces.
- Secretos de usuario: /user/codespaces/secrets; de repo: /repos/{owner}/{repo}/codespaces/secrets; de organización: /orgs/{org}/codespaces/secrets.
- Scope `codespace`. Conectarse a un codespace (SSH o VS Code) no se hace por REST; gh usa `gh codespace ssh`.

### Copilot

- Gestión (administradores de organización o empresa): GET /orgs/{org}/copilot/billing, GET /orgs/{org}/copilot/billing/seats, POST y DELETE .../selected_teams y .../selected_users, GET /orgs/{org}/members/{username}/copilot.
- Métricas de uso: GET /orgs/{org}/copilot/metrics y similares por equipo y empresa.
- Exclusiones de contenido, personalizaciones de equipo, gestión del agente en la nube por repositorio, revisión de código de Copilot: secciones nuevas de la referencia (verificar rutas antes de usar).
- Tareas del agente de Copilot (Agent tasks, vista previa pública, requiere Copilot Business o Enterprise para crear tareas; solo tokens de usuario de GitHub App o PAT fine-grained):
  - GET /agents/repos/{owner}/{repo}/tasks, POST /agents/repos/{owner}/{repo}/tasks (crear tarea a partir de una instrucción), GET /agents/repos/{owner}/{repo}/tasks/{task_id}, GET /agents/tasks, GET /agents/tasks/{task_id}.
- Asignar un issue a Copilot: asignando el usuario del agente (por ejemplo `Copilot`) con los endpoints de asignados o la mutación GraphQL correspondiente (verificar).
- Copilot Spaces: sección nueva con colaboradores y recursos.
- El chat de Copilot no tiene API pública general; gh 2.100 tiene `gh copilot` y `gh agent-task` en vista previa (ver clientes-existentes.md).

### Sponsors

- No hay REST. Solo GraphQL: `viewer { sponsorshipsAsSponsor sponsorshipsAsMaintainer }`, `sponsorsListing`, mutaciones `createSponsorship`, `cancelSponsorship`, `updateSponsorshipPreferences`. Los pagos deben hacerse en la web (y por las normas de seguridad de esta app, nunca automatizarlos).

### Apps instaladas y autorizaciones

- GET /user/installations (apps instaladas a las que se tiene acceso). Las OAuth Apps autorizadas solo se gestionan en la web (https://github.com/settings/applications).
- Revocación de credenciales filtradas: POST /credentials/revoke (sección Credentials > Revocation).

### Migraciones e importación

- GET y POST /user/migrations, GET /user/migrations/{migration_id}, GET y DELETE .../archive (exportar todos los datos de la cuenta).
- Organización: /orgs/{org}/migrations.
- El importador de código fuente (Source imports) se retiró.

### Interacciones (limitar)

- GET, PUT y DELETE /repos/{owner}/{repo}/interaction-limits, /orgs/{org}/interaction-limits, /user/interaction-limits.

## Parte 3. GraphQL: consultas y mutaciones clave

- Endpoint: `POST https://api.github.com/graphql` con `{"query": "...", "variables": {...}}`. Misma cabecera Authorization.
- Explorador: https://docs.github.com/en/graphql/overview/explorer. Esquema descargable: `GET /graphql` con Accept o el archivo schema.docs.graphql.
- Los errores llegan con HTTP 200 y un arreglo `errors` (tipo, mensaje, ruta): comprobarlo siempre.
- Paginación por cursor: `pageInfo { hasNextPage endCursor }` y `after: $cursor`.

### Projects v2

- Listar proyectos de un usuario o una organización:
  - `user(login: $login) { projectsV2(first: 20) { nodes { id number title shortDescription closed url } } }`
  - Igual con `organization(login: $org)`.
- Campos de un proyecto (incluidos los de selección única y las iteraciones):
  - `node(id: $projectId) { ... on ProjectV2 { fields(first: 50) { nodes { ... on ProjectV2Field { id name dataType } ... on ProjectV2SingleSelectField { id name options { id name } } ... on ProjectV2IterationField { id name configuration { iterations { id title startDate } } } } } } }`
- Elementos con sus valores:
  - `items(first: 50) { nodes { id type content { ... on Issue { title number url repository { nameWithOwner } } ... on PullRequest { title number } ... on DraftIssue { title body } } fieldValues(first: 20) { nodes { ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } } ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } } ... on ProjectV2ItemFieldDateValue { date } ... on ProjectV2ItemFieldIterationValue { title } ... on ProjectV2ItemFieldNumberValue { number } } } } }`
- Vistas: `views(first: 20) { nodes { name layout filter } }` (layout: TABLE_LAYOUT, BOARD_LAYOUT, ROADMAP_LAYOUT). Un tablero se puede presentar como lista agrupada por el campo Status.
- Mutaciones:
  - `createProjectV2(input: {ownerId, title})`, `updateProjectV2`, `deleteProjectV2`, `copyProjectV2`.
  - `addProjectV2ItemById(input: {projectId, contentId})`.
  - `addProjectV2DraftIssue(input: {projectId, title, body})`, `convertProjectV2DraftIssueItemToIssue`.
  - `updateProjectV2ItemFieldValue(input: {projectId, itemId, fieldId, value: {singleSelectOptionId | text | number | date | iterationId}})`: mover una tarjeta de columna = cambiar el valor del campo Status. Así se evita el arrastrar y soltar.
  - `clearProjectV2ItemFieldValue`, `updateProjectV2ItemPosition` (reordenar), `archiveProjectV2Item`, `unarchiveProjectV2Item`, `deleteProjectV2Item`.
  - `createProjectV2Field`, `updateProjectV2Field`, `deleteProjectV2Field`.
  - `linkProjectV2ToRepository`, `linkProjectV2ToTeam`.
- Scope `project` (o `read:project`).

### Discussions

- Activadas si `repository { hasDiscussionsEnabled }`.
- Categorías: `repository(owner:, name:) { discussionCategories(first: 25) { nodes { id name emoji description isAnswerable } } }`.
- Listar: `repository { discussions(first: 25, orderBy: {field: UPDATED_AT, direction: DESC}, categoryId: $cat) { nodes { id number title author { login } createdAt answer { id } comments { totalCount } url } } }`.
- Detalle con comentarios y respuestas: `discussion(number: $n) { title body bodyHTML comments(first: 50) { nodes { id body author { login } isAnswer replies(first: 50) { nodes { id body author { login } } } } } }`.
- Mutaciones: `createDiscussion(input: {repositoryId, categoryId, title, body})`, `updateDiscussion`, `deleteDiscussion`, `addDiscussionComment(input: {discussionId, body, replyToId})`, `updateDiscussionComment`, `deleteDiscussionComment`, `markDiscussionCommentAsAnswer`, `unmarkDiscussionCommentAsAnswer`, `closeDiscussion`, `reopenDiscussion`, `lockLockable`, `addUpvote`, `removeUpvote`, `pinDiscussion` (verificar). Encuestas (polls): campo `poll` con `options` y mutación de voto (verificar nombre).
- Discussions de organización: viven en un repo designado por la organización.

### Elementos fijados y perfil

- `user(login: $login) { pinnedItems(first: 6, types: [REPOSITORY, GIST]) { nodes { ... on Repository { nameWithOwner description stargazerCount } ... on Gist { name description } } } }`.
- Cambiar los fijados: mutación de elementos fijados del perfil (no documentada como estable; verificar). Fijar issues en un repo: `pinIssue`, `unpinIssue` (máximo 3).
- README de perfil: repo `{login}/{login}`, archivo README.md.
- Estado del usuario: `user { status { emoji message } }`, mutación `changeUserStatus(input: {message, emoji, expiresAt, limitedAvailability})`.

### Contribuciones

- `user(login: $login) { contributionsCollection(from: $desde, to: $hasta) { totalCommitContributions totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } commitContributionsByRepository { repository { nameWithOwner } contributions { totalCount } } } }`
- El calendario visual de la web se puede leer como «semana del 3 de marzo: 12 contribuciones» o como resumen por meses.

### Pull requests y revisión (lo que REST no cubre)

- Hilos de revisión con su estado: `repository { pullRequest(number: $n) { reviewThreads(first: 100) { nodes { id isResolved isOutdated path line startLine diffSide comments(first: 50) { nodes { id body author { login } createdAt } } } } } }`.
- `resolveReviewThread(input: {threadId})`, `unresolveReviewThread`.
- Revisión pendiente con comentarios: `addPullRequestReview(input: {pullRequestId, event, body, threads: [{path, line, side, startLine, startSide, body}]})`, `addPullRequestReviewThread`, `submitPullRequestReview`, `deletePullRequestReview`.
- `markPullRequestReadyForReview`, `convertPullRequestToDraft`.
- Auto-merge: `enablePullRequestAutoMerge(input: {pullRequestId, mergeMethod})`, `disablePullRequestAutoMerge`.
- Cola de fusión: `enqueuePullRequest`, `dequeuePullRequest`; `repository { mergeQueue(branch:) { entries ... } }`.
- Archivos vistos: `pullRequest { files(first: 100) { nodes { path viewerViewedState additions deletions } } }`, `markFileAsViewed`, `unmarkFileAsViewed`.
- Estado de comprobaciones resumido: `pullRequest { commits(last: 1) { nodes { commit { statusCheckRollup { state contexts(first: 50) { nodes { ... on CheckRun { name conclusion detailsUrl } ... on StatusContext { context state } } } } } } } }`.
- Decisión de revisión: `pullRequest { reviewDecision mergeable mergeStateStatus }`.

### Otros solo GraphQL o mejores en GraphQL

- `blame`: `repository { object(expression: "main") { ... on Commit { blame(path: "src/a.py") { ranges { startingLine endingLine age commit { oid messageHeadline author { name date } } } } } } }`.
- Commit de varios archivos con firma verificada sin git: `createCommitOnBranch(input: {branch: {repositoryNameWithOwner, branchName}, message: {headline, body}, expectedHeadOid, fileChanges: {additions: [{path, contents(base64)}], deletions: [{path}]}})`.
- Transferir issue: `transferIssue`. Duplicar o convertir issue en discusión: `convertIssueToDiscussion` (verificar).
- Sponsors (ver arriba).
- Etiquetas de un repo con conteos, plantillas de issue (`issueTemplates`, también se leen de .github/ISSUE_TEMPLATE) y plantilla de PR (`pullRequestTemplates`).
- Tablero de inicio: `viewer { repositories, starredRepositories, organizations, watching }` en una sola consulta para cargar la ventana principal rápido.

## Fuentes

- https://docs.github.com/en/rest (índice de la referencia, consultado el 21 de noviembre de 2026)
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
- https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api
- https://docs.github.com/en/rest/about-the-rest-api/breaking-changes
- https://docs.github.com/en/rest/projects/projects y https://docs.github.com/en/rest/projects/items
- https://docs.github.com/en/rest/issues/sub-issues
- https://docs.github.com/en/rest/pulls/stacks
- https://docs.github.com/en/rest/agent-tasks/agent-tasks
- https://docs.github.com/en/graphql/guides/using-the-api-to-manage-projects
- https://docs.github.com/en/graphql/guides/using-the-graphql-api-for-discussions
