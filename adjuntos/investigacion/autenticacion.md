# Autenticación con GitHub desde una aplicación de escritorio

Investigación hecha el 21 de noviembre de 2026. Fuentes principales: documentación oficial de GitHub (docs.github.com) y el código de GitHub CLI 2.100.0 (clonado en adjuntos/repos/cli_cli y adjuntos/repos/cli_oauth).

## Resumen y recomendación

- Método principal recomendado: **OAuth Device Flow** con una **OAuth App propia** registrada para nuestra aplicación, con el device flow activado. Solo hace falta el client_id, que es público. No se necesita client_secret.
- Métodos alternativos que la app debe ofrecer:
  - Pegar un **Personal Access Token** (clásico o fine-grained).
  - **Importar el token de GitHub CLI** si gh está instalado y con sesión (`gh auth token`), con permiso explícito de la persona.
  - Usar el token que ya guarda **Git Credential Manager** (`git credential fill`).
- Para git por HTTPS, pasar el token a git sin guardarlo en disco (ver git-local.md).
- SSH es opcional: la app puede generar claves ed25519 y subirlas con la API.
- Guardar el token cifrado (Administrador de credenciales de Windows mediante keyring, o DPAPI), nunca en texto plano.
- Cabeceras en todas las peticiones REST:
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2026-03-10` (la versión más reciente; ver la sección de versiones)
  - `Authorization: Bearer <token>`
  - `User-Agent: GithubAccesible/<versión>` (GitHub rechaza peticiones sin User-Agent)

## Versiones de la API REST

- Versiones admitidas en noviembre de 2026:
  - `2026-03-10`: la más reciente. Sin fecha de fin.
  - `2022-11-28`: es la que se usa si no se envía la cabecera. Fin de soporte: 10 de marzo de 2028.
- Una versión retirada devuelve `410 Gone`.
- `GET /versions` devuelve la lista de versiones que admite el servidor. Útil con GitHub Enterprise Server, que puede no conocer la 2026-03-10.
- Estrategia recomendada: enviar `2026-03-10` a github.com. En Enterprise Server, consultar `GET /versions` al conectar y usar la más alta que admita.
- Cambios incompatibles de la 2026-03-10 que nos afectan (lista completa en https://docs.github.com/en/rest/about-the-rest-api/breaking-changes):
  - `GET /rate_limit` ya no trae la propiedad `rate`. Leer `resources.core`.
  - Desaparece el campo singular `assignee` de issues y PR. Usar el arreglo `assignees`.
  - Desaparece `merge_commit_sha` de los objetos de PR.
  - En `GET /repos/{owner}/{repo}/contents/{path}` los submódulos tienen `type: "submodule"` en vez de `"file"`.
  - `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` responde 200 con los datos de la ejecución creada (antes 204 sin cuerpo). Muy útil para anunciar «ejecución número N lanzada».
  - Desaparece `has_downloads` de los repositorios.
  - Las gists ya no traen `history` ni `forks` en el objeto base.
  - `cvss` queda obsoleto en favor de `cvss_severities` (alertas de Dependabot y avisos de seguridad).
  - Bloqueos por controles comerciales devuelven 451 en vez de 403 o 422.
- Fuente: https://docs.github.com/en/rest/about-the-rest-api/api-versions

## 1. OAuth Device Flow (método recomendado)

### Requisitos previos

- Registrar una OAuth App en https://github.com/settings/applications/new (o en una organización). Datos:
  - Nombre: por ejemplo «GitHub Accesible».
  - Homepage URL: la web del proyecto.
  - Authorization callback URL: obligatoria en el formulario aunque no se use; poner `http://127.0.0.1/callback`.
  - Marcar **Enable Device Flow**. Si no se marca, la API responde `device_flow_disabled`.
- Se obtiene un **client_id** (cadena de 20 caracteres en las OAuth Apps, por ejemplo `Ov23li...` en las nuevas). Es público y puede ir en el código.
- El client_secret **no se necesita** para el device flow ni hay que distribuirlo. Según la documentación, el secreto solo hace falta para renovar tokens que no se obtuvieron con el device flow.

### Paso 1: pedir los códigos

- Petición: `POST https://github.com/login/device/code`
- Cabecera: `Accept: application/json` (si no, la respuesta viene codificada como formulario).
- Parámetros (formulario o JSON):
  - `client_id` (obligatorio).
  - `scope` (opcional): lista separada por espacios.
- Respuesta:
  - `device_code`: 40 caracteres. Lo usa la app para preguntar por el token. No se muestra.
  - `user_code`: 8 caracteres con guion en medio, por ejemplo `WDJB-MJHT`. Se muestra a la persona.
  - `verification_uri`: `https://github.com/login/device`.
  - `expires_in`: segundos de validez. Por defecto 900 (15 minutos).
  - `interval`: segundos mínimos entre consultas. Normalmente 5.

### Paso 2: la persona autoriza

- Mostrar el código en un campo de solo lectura que se pueda leer carácter a carácter, copiarlo al portapapeles y anunciarlo («Código copiado: W D J B guion M J H T»).
- Abrir `verification_uri` en el navegador predeterminado (`webbrowser.open`). Mejor aún: abrir `https://github.com/login/device?user_code=XXXX-XXXX` (hay que comprobar si GitHub sigue rellenando el campo con ese parámetro; si no lo hace, la persona pega el código).
- En la web, la persona inicia sesión (con su 2FA o passkey) y pulsa Authorize.
- Límite: 50 envíos de código por hora por aplicación.

### Paso 3: consultar hasta obtener el token

- Petición: `POST https://github.com/login/oauth/access_token`
- Cabecera: `Accept: application/json`.
- Parámetros:
  - `client_id`
  - `device_code`
  - `grant_type=urn:ietf:params:oauth:grant-type:device_code`
- Respuesta correcta: `access_token` (empieza por `gho_`), `token_type` (`bearer`), `scope` (los permisos concedidos, separados por comas). Si la app tiene activados los tokens que caducan, también `expires_in`, `refresh_token` y `refresh_token_expires_in`.
- Respuestas de error (vienen con HTTP 200 y un campo `error`):
  - `authorization_pending`: la persona aún no ha introducido el código. Seguir esperando sin ir más rápido que `interval`.
  - `slow_down`: se ha consultado demasiado rápido. Sumar 5 segundos al intervalo. La respuesta trae el nuevo `interval`.
  - `expired_token`: pasaron los 15 minutos. Pedir un código nuevo. (La documentación menciona también `token_expired` en el texto; tratar ambos igual.)
  - `access_denied`: la persona pulsó Cancelar. El código no se puede reutilizar.
  - `unsupported_grant_type`: `grant_type` mal escrito.
  - `incorrect_client_credentials`: client_id incorrecto.
  - `incorrect_device_code`: device_code no válido.
  - `device_flow_disabled`: no se activó el device flow en la configuración de la app.

### Detalles de implementación tomados de gh (cli/oauth)

- gh arranca con un intervalo un 20 % mayor que el indicado para evitar `slow_down` por desajustes del reloj, y si recibe dos `slow_down` seguidos se rinde con un mensaje de reloj desajustado (adjuntos/repos/cli_oauth/device/device_flow.go).
- gh intenta primero el device flow y, si el servidor no lo admite (Enterprise Server antiguo), recurre al flujo web con un servidor local en 127.0.0.1.
- Tras obtener el token, gh consulta el usuario (`GET /user` o GraphQL `viewer { login }`) para saber a qué cuenta pertenece. Hay que hacerlo siempre: la persona pudo cambiar de cuenta en el navegador.
- En la app: hacer la espera en un hilo, con barra de progreso, botón Cancelar, cuenta atrás anunciada cada minuto y anuncio final («Sesión iniciada como usuario»).

### Scopes recomendados

- Los mínimos de gh son `repo read:org gist` (adjuntos/repos/cli_cli/internal/authflow/flow.go).
- Para una app «completa» recomendamos pedir: `repo read:org gist workflow notifications read:user user:email user:follow project read:packages`.
- Pedir aparte, solo cuando la persona use la función (re-autorización incremental: se repite el device flow pidiendo los scopes nuevos):
  - `delete_repo` (borrar repositorios).
  - `admin:org` o `write:org` (gestionar organizaciones y equipos).
  - `admin:public_key`, `admin:gpg_key`, `admin:ssh_signing_key` (subir claves).
  - `admin:repo_hook`, `admin:org_hook` (webhooks).
  - `write:packages`, `delete:packages`.
  - `codespace`.
  - `security_events` (code scanning en repos privados).
  - `user` (editar perfil).
- Lista completa de scopes y su significado:
  - `repo`: acceso total a repos públicos y privados. Incluye `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, `security_events`.
  - `public_repo`: solo repos públicos.
  - `workflow`: crear y modificar archivos de .github/workflows. Sin él, un push que toque workflows falla.
  - `admin:org`, `write:org`, `read:org`: organizaciones, equipos y membresías.
  - `admin:public_key`, `write:public_key`, `read:public_key`: claves SSH.
  - `admin:repo_hook`, `write:repo_hook`, `read:repo_hook`; `admin:org_hook`.
  - `gist`: crear y editar gists.
  - `notifications`: leer notificaciones, marcarlas, suscripciones y watch.
  - `user` (incluye `read:user`, `user:email`, `user:follow`).
  - `project`, `read:project`: Projects.
  - `delete_repo`.
  - `write:packages`, `read:packages`, `delete:packages`.
  - `admin:gpg_key`, `write:gpg_key`, `read:gpg_key`.
  - `admin:ssh_signing_key`: claves SSH de firma.
  - `codespace`.
  - Sin scope: solo información pública.
- GitHub «normaliza» los scopes: si se pide `user` y `user:email`, guarda solo `user`.
- Fuente: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps

### Organizaciones con restricción de OAuth Apps

- Muchas organizaciones tienen activada la «OAuth app access restriction». Una OAuth App nueva no verá los repos privados de esa organización hasta que un administrador la apruebe. La persona puede pedir la aprobación desde https://github.com/settings/connections/applications/CLIENT_ID.
- La app debe detectarlo (los repos de la organización no aparecen o la API devuelve 403) y explicarlo, ofreciendo pedir aprobación o usar un PAT o el token de gh.

### Organizaciones con SAML SSO

- Si la organización usa SAML SSO, el token debe autorizarse para esa organización.
- La API responde 403 con la cabecera `X-GitHub-SSO: required; url=https://github.com/orgs/ORG/sso?authorization_request=...`. La app debe leer esa cabecera, explicar el problema y ofrecer abrir la URL.
- Otra variante: `X-GitHub-SSO: partial-results; organizations=21955855,20582480` cuando una lista omite organizaciones no autorizadas.

### Caducidad y renovación

- Los tokens `gho_` de una OAuth App no caducan salvo que se activen los tokens que caducan («expiring user tokens», opcional en la configuración de la app) o que no se usen en un año.
- Si caducan: `POST https://github.com/login/oauth/access_token` con `client_id`, `grant_type=refresh_token` y `refresh_token`. Con tokens obtenidos por device flow no hace falta el client_secret. Los refresh tokens empiezan por `ghr_`.
- gh 2.100 ya pide tokens renovables cuando el servidor los admite (adjuntos/repos/cli_cli/internal/authflow/refresh.go). En Enterprise Server hace falta la versión 3.23 o posterior.
- Revocar: la persona lo hace en https://github.com/settings/applications. La API de revocación (`DELETE /applications/{client_id}/grant`) exige el client_secret, así que una app de escritorio no puede usarla; basta con borrar el token local y ofrecer abrir esa página.

## 2. El client_id de GitHub CLI y si se puede reutilizar

- gh usa la OAuth App «GitHub CLI», propiedad de GitHub:
  - client_id: `178c6fc778ccc68e1d6a`
  - El client_secret también está en el código fuente, con el comentario de que es seguro publicarlo (adjuntos/repos/cli_cli/internal/authflow/flow.go, líneas 22 a 27).
- Técnicamente funciona: el device flow con ese client_id devolvería un token idéntico al de gh, con su device flow ya activado.
- Por qué **no** lo recomendamos como método principal:
  - La pantalla de autorización y la lista de aplicaciones autorizadas mostrarían «GitHub CLI», no nuestra app. Eso confunde a la persona y es suplantar la identidad de otra aplicación.
  - La documentación de GitHub trata el client_id como el identificador de **tu** aplicación; no hay ninguna autorización para que terceros usen el de gh. Las condiciones de uso de la API prohíben hacerse pasar por otro. No encontré ninguna declaración oficial que lo permita.
  - GitHub podría cambiar o limitar ese client_id en cualquier momento (rotación, comprobaciones de User-Agent, límites de 2.000 peticiones de token por hora por app compartidos con todo gh).
  - Hay otras herramientas que reutilizan client_ids ajenos (se discute, por ejemplo, en https://community.openai.com/t/best-practice-for-clientid-when-using-codex-oauth/1371778), pero no es buena práctica.
- Ventaja real de gh: muchas organizaciones ya tienen aprobada la app GitHub CLI. Para aprovecharla de forma legítima, la app puede **importar el token de gh** (sección 4) con el permiso de la persona.
- Recomendación final: registrar nuestra propia OAuth App con device flow, poner su client_id en la configuración de la app (y permitir que la persona lo cambie, para Enterprise Server o por si quiere usar su propia OAuth App).

## 3. Personal Access Tokens (PAT)

### Tipos y prefijos de token

- `ghp_`: PAT clásico.
- `github_pat_`: PAT fine-grained.
- `gho_`: token de OAuth App (device flow o flujo web).
- `ghu_`: token de usuario de una GitHub App.
- `ghs_`: token de instalación de GitHub App (y el GITHUB_TOKEN de Actions).
- `ghr_`: refresh token.
- El prefijo permite a la app saber qué tipo de token ha pegado la persona y avisar si no sirve.

### PAT clásico

- Se crea en https://github.com/settings/tokens/new (Settings, Developer settings, Personal access tokens, Tokens (classic)).
- La URL admite parámetros para preseleccionar: `https://github.com/settings/tokens/new?scopes=repo,read:org,gist,workflow&description=GitHub%20Accesible`. No aparece en la documentación oficial actual, pero gh y otras herramientas lo usan; comprobar que sigue funcionando.
- Acceso a todos los repos de la persona y de sus organizaciones, según los scopes.
- Necesario todavía para: escribir en repos públicos ajenos, colaboradores externos, Packages, la API de Checks y Projects de usuario.

### PAT fine-grained

- Se crea en https://github.com/settings/personal-access-tokens/new.
- Admite parámetros en la URL: `name`, `description`, `target_name` (usuario u organización), `expires_in` (1 a 366, o `none`) y permisos como `contents=write`, `issues=write`, `pull_requests=write`, `actions=write`, `workflows=write`, `metadata=read`.
- Limitaciones actuales: un solo propietario (usuario u organización) por token, no sirve para contribuir a repos públicos ajenos ni como colaborador externo, no accede a Packages, ni a la API de Checks, ni a Projects de usuario.
- Si la organización exige aprobación, queda pendiente y solo lee recursos públicos hasta que un administrador lo apruebe.
- Fuente: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

### Cómo validar un token

- `GET https://api.github.com/user` con `Authorization: Bearer TOKEN`:
  - 200: válido. El cuerpo trae `login`, `name`, `id`, `two_factor_authentication`, etc.
  - 401: token no válido, revocado o caducado.
  - 403 con `X-GitHub-SSO`: falta autorizarlo para SAML.
- Cabeceras útiles de la respuesta:
  - `X-OAuth-Scopes`: scopes del token (solo PAT clásico y tokens OAuth). Los fine-grained no la traen o viene vacía.
  - `X-Accepted-OAuth-Scopes`: scopes que pide ese endpoint.
  - `GitHub-Authentication-Token-Expiration`: fecha de caducidad del token, si la tiene. Avisar a la persona unos días antes.
  - `X-RateLimit-Limit` y similares.
- Para un fine-grained no hay forma directa de listar permisos; se descubren por los 403. En la respuesta de un 403 por falta de permiso, la cabecera `X-Accepted-GitHub-Permissions` indica qué permiso hace falta (por ejemplo `contents=read`). Usarla para explicar el error.
- `GET /rate_limit` no gasta cuota primaria y también sirve para validar.

## 4. Reutilizar el token de GitHub CLI

- Comprobar si gh está instalado: `where gh` o rutas típicas `C:\Program Files\GitHub CLI\gh.exe` y `%LOCALAPPDATA%\Microsoft\WinGet\Links\gh.exe`, o scoop `%USERPROFILE%\scoop\shims\gh.exe`.
- Obtener el token: `gh auth token --hostname github.com` (opcionalmente `--user LOGIN` si hay varias cuentas). Sale por la salida estándar, sin salto de línea extra importante (recortar espacios).
- Estado: `gh auth status --hostname github.com` (texto; con `--json` en versiones recientes: comprobar con `gh auth status --help`).
- Dónde guarda gh los datos en Windows:
  - Configuración: `%APPDATA%\GitHub CLI\config.yml` y `%APPDATA%\GitHub CLI\hosts.yml` (o la carpeta de `GH_CONFIG_DIR`).
  - El token va en el Administrador de credenciales de Windows, con el nombre de servicio `gh:github.com` y como usuario el login (y una entrada con usuario vacío para la cuenta activa) (adjuntos/repos/cli_cli/internal/config/config.go, función keyringServiceName).
  - Solo si se hizo `gh auth login --insecure-storage`, el token aparece en hosts.yml como `oauth_token`.
  - hosts.yml lista las cuentas por host: `github.com: users: LOGIN: ...`, `user: LOGIN` (activa), `git_protocol: https`.
- Variables de entorno que gh respeta y que la app también puede leer: `GH_TOKEN`, `GITHUB_TOKEN` (github.com), `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, `GH_HOST`.
- Recomendación: no leer el almacén de credenciales de gh directamente; llamar a `gh auth token`, y solo tras preguntar a la persona («Se ha encontrado una sesión de GitHub CLI como LOGIN. ¿Quieres usarla?»). Validar después con `GET /user`. El token de gh tiene los scopes `repo read:org gist` como mínimo, más los que la persona añadiera con `gh auth refresh -s`.

## 5. Git Credential Manager (GCM)

- Viene con Git para Windows (en este equipo, GCM 2.9.0; `credential.helper=manager`).
- Pedir una credencial guardada:
  - Ejecutar `git credential fill` con esta entrada estándar (cada línea termina en salto de línea y se acaba con una línea vacía):
    - `protocol=https`
    - `host=github.com`
    - (opcional) `username=LOGIN`
  - La salida trae `protocol`, `host`, `username` y `password` (el token).
- Para que no abra ventanas ni pida nada: variables `GIT_TERMINAL_PROMPT=0` y `GCM_INTERACTIVE=never`. Si no hay credencial guardada, falla sin preguntar.
- Si se permite la interacción, GCM abre su propia ventana de inicio de sesión (navegador, device code o PAT). Su accesibilidad con lector de pantalla no está comprobada; preferir nuestro device flow.
- Si se usa la credencial, confirmar con `git credential approve`; si falla, `git credential reject` con la misma entrada para que GCM la olvide.
- El token que guarda GCM para github.com suele ser un `gho_` de la OAuth App de GCM con scopes `repo gist workflow`.
- `git credential-manager github list` lista las cuentas de GitHub que conoce GCM (comprobar con `git credential-manager github --help`).
- Usos en nuestra app: como fuente de token al iniciar, y como almacén donde dejar nuestro token para que git funcione desde fuera de la app (con `git credential approve`), solo si la persona lo pide.

## 6. GitHub App (tokens de instalación y JWT)

- No es el método principal para una app de escritorio de uso general, pero conviene conocerlo:
  - Una GitHub App tiene permisos finos y se instala en cuentas u organizaciones concretas.
  - Sus tokens de usuario (`ghu_`) solo ven los recursos donde la app está instalada. Para un cliente «de todo GitHub» eso es una limitación grande frente a una OAuth App.
- Autenticarse como la app (JWT):
  - Firmar un JWT RS256 con la clave privada .pem de la app.
  - Campos: `iat` (ahora menos 60 segundos), `exp` (máximo 10 minutos después), `iss` (el client ID de la app, recomendado, o el App ID).
  - Enviarlo como `Authorization: Bearer JWT`.
  - Con Python: `pyjwt[crypto]`.
- Token de instalación:
  - `GET /app/installations` (con JWT) para ver las instalaciones.
  - `POST /app/installations/{installation_id}/access_tokens` (con JWT). Devuelve un `ghs_` válido 1 hora. Se puede limitar a algunos repos y permisos.
- Tokens de usuario de GitHub App:
  - Se obtienen con el mismo device flow (la GitHub App también admite «Enable Device Flow»).
  - Caducan a las 8 horas; el refresh token, a los 6 meses.
- Fuente: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app

## 7. Flujo web con PKCE y redirección a 127.0.0.1

- `GET https://github.com/login/oauth/authorize` con `client_id`, `redirect_uri=http://127.0.0.1:PUERTO/callback`, `scope`, `state` aleatorio, `code_challenge` y `code_challenge_method=S256`. Opcionales: `login`, `allow_signup`, `prompt=select_account`.
- La app escucha en 127.0.0.1 en un puerto libre (el puerto no tiene que coincidir con el registrado). Usar `127.0.0.1` o `::1`, no `localhost`.
- Problema: el canje del código (`POST /login/oauth/access_token`) exige el **client_secret** en las OAuth Apps, aunque se use PKCE. Distribuirlo en una app de escritorio lo hace público (como hace gh).
- Conclusión: el device flow es mejor para nosotros. El flujo web solo como alternativa para Enterprise Server antiguos sin device flow.

## 8. SSH

### Generar claves

- Comprobar `ssh-keygen` en `C:\Windows\System32\OpenSSH\ssh-keygen.exe` (OpenSSH de Windows) o en `C:\Program Files\Git\usr\bin\ssh-keygen.exe`.
- Generar: `ssh-keygen -t ed25519 -C "correo@ejemplo.com" -f "%USERPROFILE%\.ssh\id_ed25519" -N "FRASE"`. Con `-N ""` queda sin frase de paso (preguntar a la persona).
- Pasar la frase con `-N` la expone en la línea de órdenes; alternativa: generar sin frase y luego `ssh-keygen -p` interactivo, o generar la clave con la librería `cryptography` (Ed25519PrivateKey, serialización OpenSSH con cifrado) sin procesos externos.

### Subir la clave a GitHub

- Clave de autenticación: `POST /user/keys` con `{"title": "...", "key": "ssh-ed25519 AAAA..."}`. Necesita el scope `admin:public_key` o `write:public_key`. Listar: `GET /user/keys`. Borrar: `DELETE /user/keys/{key_id}`.
- Clave de firma de commits: `POST /user/ssh_signing_keys` (scope `admin:ssh_signing_key`). Listar: `GET /user/ssh_signing_keys`.
- Claves GPG: `POST /user/gpg_keys` con `armored_public_key` (scope `admin:gpg_key`).

### ssh-agent en Windows

- El servicio «OpenSSH Authentication Agent» (`ssh-agent`) viene desactivado por defecto. Activarlo requiere administrador (`Set-Service ssh-agent -StartupType Automatic` y `Start-Service ssh-agent`). Es un cambio del sistema: la app debe explicarlo y dejar que la persona lo haga o lo confirme expresamente.
- Añadir la clave: `ssh-add %USERPROFILE%\.ssh\id_ed25519`.
- Para que git use el agente de Windows y no el ssh de Git para Windows: `git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"`.
- Probar: `ssh -T git@github.com`. Devuelve código de salida 1 aunque funcione, con el texto «successfully authenticated». Hay que comprobar el texto, no el código.
- Huella del host: obtener las claves y huellas oficiales con `GET /meta` (campos `ssh_keys` y `ssh_key_fingerprints`) y escribirlas en `known_hosts` para evitar la pregunta interactiva. Para el puerto 443: host `ssh.github.com`, puerto 443.
- Variables útiles para que ssh nunca pregunte desde la app: `GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes"`.

## 9. GitHub Enterprise Server y GHE.com

- GitHub Enterprise Server (instalado por la empresa):
  - API REST: `https://HOST/api/v3`
  - GraphQL: `https://HOST/api/graphql`
  - Subida de archivos (assets de releases): `https://HOST/api/uploads`
  - Device flow: `https://HOST/login/device/code` y `https://HOST/login/oauth/access_token`. Debe estar activado en el servidor y hace falta una OAuth App registrada **en ese servidor** (otro client_id). Por eso la app debe permitir configurar el client_id por host.
  - `GET https://HOST/api/v3/meta` devuelve `installed_version`.
  - Algunas funciones nuevas no existen en versiones antiguas: comprobar con `GET /versions` y manejar 404.
- GHE.com (Enterprise Cloud con residencia de datos): API en `https://api.SUBDOMINIO.ghe.com` y web en `https://SUBDOMINIO.ghe.com`.
- github.com: API `https://api.github.com`, GraphQL `https://api.github.com/graphql`, subidas `https://uploads.github.com`.
- La app debe manejar varias cuentas y varios hosts, como gh (cuenta activa por host).

## 10. Autenticación en dos pasos (2FA) y passkeys

- La API no usa la contraseña ni el 2FA: siempre se trabaja con tokens. El 2FA (app TOTP, SMS, llave de seguridad, passkey o GitHub Mobile) se resuelve en el navegador durante el device flow.
- Git por HTTPS no admite contraseña desde agosto de 2021: hay que usar token, GCM o SSH.
- `GET /user` devuelve `two_factor_authentication` (true o false) para la propia cuenta. Útil para avisar.
- GitHub exige 2FA a la mayoría de quienes contribuyen código; si la persona no lo tiene, GitHub se lo pedirá en la web.
- Las acciones «sudo» de la web (por ejemplo borrar un repositorio) piden reautenticación en la web, pero por la API basta con el scope adecuado (`delete_repo`).

## 11. Almacenamiento seguro del token

- Opción A: `keyring` (backend del Administrador de credenciales de Windows). Nombre de servicio propio, por ejemplo `GithubAccesible:github.com`, usuario = login.
- Opción B: cifrar con DPAPI (`CryptProtectData` mediante pywin32 o ctypes) y guardar el blob en la carpeta de datos de la app (encaja con una app portable).
- Nunca escribir el token en registros, mensajes de error, URLs ni en la configuración de git.
- Al cerrar sesión: borrar el token local, ofrecer abrir https://github.com/settings/applications para revocarlo.

## Fuentes

- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
- https://docs.github.com/en/rest/about-the-rest-api/api-versions
- https://docs.github.com/en/rest/about-the-rest-api/breaking-changes
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
- https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-cli-with-a-github-app
- https://github.com/cli/cli (internal/authflow/flow.go y refresh.go, internal/config/config.go)
- https://github.com/cli/oauth (device/device_flow.go)
- https://github.com/git-ecosystem/git-credential-manager
