# Investigación para GitHub Accesible

Carpeta de consulta permanente. Investigación hecha el 21 de noviembre de 2026 para una aplicación de escritorio Windows en Python 3.15 y wxPython, accesible con NVDA y JAWS, en español, que gestione GitHub por completo (web y gh CLI) y git local.

## Archivos de investigación

- autenticacion.md: todas las formas de iniciar sesión. Device flow (endpoints, parámetros, errores, scopes), client_id de gh y por qué no reutilizarlo, PAT clásico y fine-grained y cómo validarlos, token de gh, Git Credential Manager, GitHub App, flujo web con PKCE, SSH, Enterprise Server, 2FA, versiones de la API (la más reciente es 2026-03-10) y almacenamiento seguro del token.
- api-rest-graphql.md: inventario por áreas de los endpoints REST (método y ruta), paginación, límites de uso, ETag y 304, y consultas y mutaciones GraphQL clave (Projects v2, Discussions, hilos de revisión, auto-merge, blame, contribuciones, elementos fijados).
- git-local.md: operaciones que debe ofrecer el cliente, cómo invocarlas con subprocess (porcelain v2, -z, variables de entorno, CREATE_NO_WINDOW, progreso, cancelación), detección de git, cómo pasar el token sin guardarlo y alternativas sin git (dulwich, pygit2, API).
- necesidades-usuarios.md: lo que piden las personas ciegas y los usuarios en general, problemas de accesibilidad de la web de GitHub, GitHub Desktop y gh, con propuesta de solución y 40 funciones priorizadas. Con fuentes. (Escrito por un subagente; varias fuentes como foros de NVDA, program-l, AudioGames y Reddit no dieron resultado y así consta.)
- clientes-existentes.md: GitHub Desktop, gh CLI 2.100.0 (lista completa de comandos), GitKraken, Fork, Sourcetree, TortoiseGit, lazygit, Sublime Merge, Git Extensions, VS Code, GitHub Mobile, Tower y clientes de la comunidad ciega, con una lista de verificación de funciones agrupada en 27 áreas. (Escrito por un subagente.)
- librerias-python.md: compatibilidad real con Python 3.15 comprobada en este equipo (PyPI, pip --dry-run, importación en un entorno virtual y una congelación de prueba con cx_Freeze) y recomendación.

## Archivos que ya estaban en la carpeta

- analisis-cursoclaude.md y analisis-socialrss.md: análisis de otros proyectos propios (uso de HTML en CursoClaude y patrones de SocialRSS) que no forman parte de esta tanda de investigación.

## Repositorios de referencia clonados

Están en D:\Antigravity\GithubAccesible\adjuntos\repos\ con `git clone --depth 1` (solo la última versión, sin historial). Para actualizarlos: `git -C CARPETA pull --depth 1`.

- cli_cli: GitHub CLI (https://github.com/cli/cli), commit de06af2 del 20 de noviembre de 2026, unos 46 MB. Archivos útiles:
  - internal/authflow/flow.go: client_id de gh, scopes mínimos y flujo de inicio de sesión.
  - internal/authflow/refresh.go: renovación de tokens que caducan.
  - internal/config/config.go: dónde guarda gh el token (servicio `gh:HOST` en el almacén de credenciales).
  - pkg/cmd/: implementación de cada comando de gh (pr, issue, run, release...), útil para ver qué endpoints y consultas GraphQL usa cada función.
- cli_oauth: librería OAuth de gh (https://github.com/cli/oauth), 20 de noviembre de 2026, 262 KB. device/device_flow.go muestra el sondeo con margen del 20 % y el manejo de slow_down.
- PyGithub_PyGithub: PyGithub (https://github.com/PyGithub/PyGithub), 20 de noviembre de 2026, unos 32 MB. github/Consts.py, Requester.py (límites, reintentos) y los módulos por objeto como referencia de endpoints.
- Ambro86_Accessible-github-assistant-in-wxpython: «Accessible GitHub Assistant» de una persona ciega, hecho en wxPython (https://github.com/Ambro86/Accessible-github-assistant-in-wxpython), último commit del 13 de julio de 2025, unos 8 MB. Usa un árbol de órdenes (wx.TreeCtrl), PAT cifrado con contraseña maestra (cryptography Fernet), sonidos de éxito y fallo e interfaz en italiano con traducciones. Útil como antecedente directo: qué funciona y qué no. No tiene licencia visible: solo para consulta, no copiar código.

No se clonó github/rest-api-description por su tamaño.
