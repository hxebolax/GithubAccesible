# Librerías de Python candidatas y compatibilidad con Python 3.15

Comprobado el 21 de noviembre de 2026 en este equipo (Windows 11, Python 3.15.0 de 64 bits en `C:\Python315`), con tres métodos:

- El índice JSON de PyPI de cada paquete (versión, fecha, ruedas publicadas y clasificadores).
- `pip install --dry-run` con Python 3.15 para ver qué archivo elige pip realmente (rueda binaria o código fuente).
- Instalación en un entorno virtual de 3.15 y prueba de importación de cada librería.

## Conclusión rápida

- **wxPython 4.3.2 tiene ruedas oficiales para Python 3.15** en PyPI: `wxpython-4.3.2-cp315-cp315-win_amd64.whl`, también `win32` y `win_arm64`. Publicada el 16 de octubre de 2026, basada en wxWidgets 3.3.4. Ya está instalada en `C:\Python315` y funciona (`wx.version()` devuelve «4.3.2 msw (phoenix) wxWidgets 3.3.4»).
- **cx_Freeze 8.7.4 es compatible con Python 3.15** (27 de octubre de 2026; `requires_python <3.16,>=3.10`; clasificador 3.15). Es una rueda `py3-none-any`: la parte compilada está en la dependencia `freeze-core 0.8.1`, que sí tiene rueda `cp315-cp315-win_amd64`. Prueba hecha: se congeló un script que importa wx, ssl, json y sqlite3; el .exe funcionó y ocupa 69 MB sin optimizar.
- Todas las demás librerías necesarias instalan sin compilar nada en 3.15 (ruedas binarias cp315 o abi3, o Python puro).
- Las únicas que no tienen ruedas para 3.15 son cytolk (última de 2023, hasta 3.12) y, con menos importancia, accessible_output2 y sound_lib, que no lo necesitan porque son Python puro con DLL incluidas.

## Interfaz y empaquetado

### wxPython

- Versión 4.3.2 (16 de octubre de 2026). `requires_python >=3.10`. Clasificadores de 3.10 a 3.15.
- Ruedas para 3.15: win32, win_amd64 y win_arm64. Comprobado en https://pypi.org/project/wxPython/#files y en el índice JSON.
- wxWidgets 3.3: modo oscuro en Windows, mejoras de alto DPI y de accesibilidad (MSAA mediante wx.Accessible).
- Recomendación: usarla. Fijar `wxPython==4.3.2` en requirements.

### cx_Freeze

- Versión 8.7.4 (27 de octubre de 2026). Requiere Python de 3.10 a 3.15 incluido.
- Dependencias en Windows: `freeze-core>=0.8.1` (para 3.15), `lief`, `python-msilib` (para crear instaladores MSI en 3.13 o posterior, porque msilib salió de la biblioteca estándar), `setuptools<85`, `packaging`.
- `freeze-core 0.8.1` tiene ruedas cp315 para win32, win_amd64 y win_arm64 (en la lista corta de PyPI solo se veían hasta cp314; pip eligió `freeze_core-0.8.1-cp315-cp315-win_amd64.whl`).
- Prueba real: `python -m cx_Freeze --script hola.py --target-dir dist` creó `hola.exe`, `python315.dll` y `lib`. El ejecutable imprimió «wx 4.3.2 ... python 3.15.0 ssl OpenSSL 3.5.9».
- Aviso normal durante la congelación: falta `api-ms-win-core-path-l1-1-0.dll` (no es necesaria en Windows 10 y 11).
- Recomendación: usarla para la versión portable y, si se quiere, `bdist_msi` para instalador.

### comtypes

- Versión 1.5.0 (9 de noviembre de 2026). Python puro. Funciona en 3.15.
- Útil para COM (por ejemplo la API de JAWS `FreedomSci.JawsApi` o UI Automation).

### pywin32

- Versión 312 (4 de junio de 2026). Ruedas cp315 para win32, win_amd64 y win_arm64.
- Útil para DPAPI (`win32crypt.CryptProtectData`), Job Objects (matar árboles de procesos de git), notificaciones, registro de Windows.

## Voz y sonido (accesibilidad)

### accessible_output2

- Versión 0.17 (julio de 2022). Rueda `py2.py3-none-any`: Python puro con las DLL de los lectores incluidas (nvdaControllerClient, SAAPI de System Access, Dolphin, etc.).
- Depende de `libloader`, `platform_utils` y `pywin32`.
- Probado en 3.15: importa y crea `Auto()`. Salidas detectadas: SystemAccess, NVDA, Dolphin, PCTalker, ZDSR y SAPI5. JAWS no aparece en la lista porque su salida necesita que JAWS esté instalado (se carga por COM).
- Sin mantenimiento desde 2022, pero estable y muy usado en apps accesibles. Revisar que el nvdaControllerClient incluido sea de 64 bits y reciente; si no, sustituir la DLL por la del último NVDA (está en https://github.com/nvaccess/nvda, carpeta extras/controllerClient).
- Recomendación: usarla para anunciar por voz y braille mensajes breves («Commit realizado», «Push terminado»). Siempre como complemento de la interfaz, nunca como única forma de dar la información.

### cytolk

- Versión 0.1.13 (2023). Solo ruedas hasta cp312. **No sirve para 3.15** sin compilar. Descartada.

### Alternativas de voz

- Hablar directamente con NVDA mediante `nvdaControllerClient.dll` y ctypes (función `nvdaController_speakText`), y con JAWS mediante comtypes. Es lo que hace accessible_output2 por dentro.
- SAPI5 mediante comtypes (`SAPI.SpVoice`) como último recurso.
- Los anuncios de wxPython: en wx 3.3 no hay una API general de «live regions»; lo más fiable sigue siendo el lector mediante accessible_output2. (Comprobar si wx 4.3 expone notificaciones de UIA.)

### sound_lib

- Versión 0.83 (septiembre de 2022). Rueda `py2.py3-none-any` con bass.dll incluida.
- Probado en 3.15: importa y abre la salida de audio (`sound_lib.output.Output()`).
- Para sonidos cortos (línea añadida, línea eliminada, error, fin de tarea). Alternativa sin dependencias: `winsound.PlaySound` con archivos WAV (biblioteca estándar, asíncrono con `SND_ASYNC`, pero sin mezcla ni volumen).
- Recomendación: `winsound` para empezar; sound_lib si se necesita volumen, panorama o sonidos superpuestos. Revisar la licencia de BASS (gratuita para software no comercial).

## Cliente de la API de GitHub

### PyGithub

- Versión 2.10.0 (20 de agosto de 2026). Python puro. Clasificadores hasta 3.15. Depende de requests, PyJWT[crypto], PyNaCl, urllib3, typing-extensions.
- Ya define la versión de API 2026-03-10 (constante `API_VERSION_2026_03_10` en github/Consts.py) además de 2022-11-28, y lee la cabecera `x-github-api-version-selected`.
- Ventajas: muy conocida, documentación y ejemplos abundantes, paginación automática (`PaginatedList`), cifrado de secretos de Actions incluido (por eso depende de PyNaCl), autenticación de GitHub App.
- Inconvenientes: solo REST (GraphQL casi nada: Projects v2, Discussions y resolver hilos habría que hacerlos aparte); los objetos «perezosos» hacen peticiones ocultas al leer atributos, lo que complica controlar el límite de uso y el progreso; síncrona.
- Tiempo de importación medido: 0,23 s.

### githubkit

- Versión 0.17.1 (6 de noviembre de 2026). Python puro. `requires_python >=3.10,<4`. Sin clasificadores, pero instala y funciona en 3.15.
- Generada a partir de la descripción OpenAPI oficial: cubre **todos** los endpoints REST con tipos (modelos pydantic) y la versión 2026-03-10 (paquete `githubkit-schemas-2026-03-10`).
- Incluye: GraphQL, síncrona y asíncrona, paginación, reintentos automáticos ante límites de uso, caché HTTP con ETag (mediante hishel), estrategias de autenticación (token, OAuth device flow con `OAuthDeviceAuthStrategy`, GitHub App con JWT, Actions), webhooks.
- Inconvenientes: muchas dependencias (httpx, anyio, pydantic, pydantic_core, hishel, anysqlite) y tamaño: los esquemas ocupan unos 60 MB instalados (aumentará el ejecutable congelado). Importación medida: 0,12 a 0,24 s (los módulos se cargan bajo demanda).
- pydantic_core 2.50.5 tiene rueda cp315 para Windows.

### ghapi

- Versión 2.1.5 (27 de octubre de 2026). Python puro, de fast.ai. También generada desde OpenAPI pero sin tipos, depende de fastcore. Menos usada. No recomendada como base.

### Cliente propio sobre requests o httpx

- requests 2.34.2 (mayo de 2026): Python puro, clasificadores hasta 3.15. Cabecera `Link` ya interpretada (`response.links`).
- httpx 0.28.1 (diciembre de 2024): Python puro, funciona en 3.15 aunque sus clasificadores llegan a 3.12. Sin versiones nuevas desde hace casi dos años: vigilar su mantenimiento. Admite HTTP/2 y async.
- Un cliente propio pequeño (unos cientos de líneas: sesión, cabeceras, ETag, paginación por Link, límites de uso, errores traducidos, GraphQL) da control total del progreso, de la cola de peticiones y de los mensajes en español.

### Recomendación para la API

- Opción recomendada: **cliente propio fino sobre requests** para el núcleo (control de la cola, la caché ETag, los límites y los anuncios), con módulos por área (repos, issues, PR, Actions...) y consultas GraphQL escritas a mano para Projects, Discussions e hilos de revisión.
- Usar **githubkit** como referencia de esquemas y, si el tamaño no importa, como implementación de las áreas menos frecuentes (administración de organizaciones, seguridad, Codespaces). Es la única librería con cobertura completa y tipada de la versión 2026-03-10.
- PyGithub es buena opción si se quiere avanzar rápido en REST, pero no cubre GraphQL y sus peticiones ocultas son un problema para una app que anuncia todo lo que hace.
- En cualquier caso, PyNaCl es necesaria para crear secretos de Actions, Dependabot y Codespaces.

## Git

- dulwich 1.2.21 (5 de noviembre de 2026): ruedas cp315 y cp315t para Windows (y rueda pura de respaldo). Probado: `dulwich.porcelain` importa en 3.15. Porcelain muy completo (ver git-local.md). Recomendado como respaldo si no hay git.
- pygit2 1.21.0 (4 de noviembre de 2026; libgit2 1.9.7): ruedas cp315 y cp315t para Windows. Probado: importa. Comprobado en este equipo que la rueda de Windows **no incluye SSH** (el indicador `pygit2.features` no tiene el bit de SSH): solo HTTPS. Sin rebase de alto nivel ni LFS.
- GitPython 3.2.1 (14 de octubre de 2026): Python puro, hasta 3.15, pero necesita el ejecutable git. No aporta frente a un envoltorio propio con subprocess.
- Recomendación: subprocess con git (envoltorio propio) como motor principal, dulwich como respaldo.

## Markdown y HTML

- Markdown 3.11.3 (5 de noviembre de 2026): Python puro, requiere 3.11 o posterior, hasta 3.15. Extensiones para tablas, código, notas al pie.
- mistune 3.4.0 (19 de octubre de 2026): Python puro, hasta 3.15. Más rápido; con plugins para tablas, tachado, listas de tareas y notas al pie (más cercano a GitHub Flavored Markdown).
- Para que el resultado sea idéntico a GitHub (menciones, referencias #123, alertas `> [!NOTE]`, emojis), lo más fiable es pedir el HTML a GitHub: `POST /markdown` en modo `gfm`, o pedir los cuerpos con `Accept: application/vnd.github.html+json`. Usar una librería local solo para la vista previa sin conexión.
- Mostrar el HTML en `wx.html2.WebView` (Edge WebView2, accesible con NVDA y JAWS en modo exploración) o, para texto sencillo, `wx.html.HtmlWindow` (más limitado para lectores). El visor accesible de la app ya existe en el proyecto relacionado wx-accessible-webview (instalado en este Python desde E:\Antigravity\LaSalaAntigravity\adjuntos\wx-accessible-webview).

## Seguridad y credenciales

- cryptography 50.0.2 (30 de septiembre de 2026): ruedas `cp315-abi3.abi3t-win_amd64` y `cp311-abi3`. Funciona en 3.15. Para generar claves SSH ed25519 sin ssh-keygen y para cifrado local.
- keyring 25.7.0 (noviembre de 2025): Python puro. Probado en 3.15: usa `WinVaultKeyring` (Administrador de credenciales de Windows). Para guardar tokens por cuenta y host. Nota: en una app portable el token quedaría en el equipo, no en la carpeta de la app; si se quiere portabilidad total, usar DPAPI y guardar el blob en la carpeta de datos (sigue ligado al usuario de Windows).
- PyNaCl 1.6.2 (enero de 2026): rueda `cp38-abi3-win_amd64` (abi3, vale para 3.15). Probado: importa. Necesaria para cifrar secretos (sealed box con la clave pública del repo).
- PyJWT 2.15.1: Python puro. Para firmar JWT de GitHub App (con `cryptography`).
- certifi 2026.11.20 y truststore 0.10.5 (Python puro, hasta 3.15). truststore hace que Python use el almacén de certificados de Windows: importante en empresas con proxy que inspecciona TLS. Recomendado: `truststore.inject_into_ssl()` al arrancar.

## Otras útiles

- send2trash: mover archivos a la papelera en vez de borrarlos (verificar versión para 3.15; es Python puro).
- pywin32 o ctypes para Job Objects y DPAPI.
- pytest para pruebas.

## Resumen de recomendación

- Interfaz: wxPython 4.3.2.
- Empaquetado: cx_Freeze 8.7.4 (con freeze-core 0.8.1).
- HTTP y API: cliente propio sobre requests 2.34 + truststore; consultas GraphQL propias; githubkit 0.17 como referencia o complemento; PyNaCl para secretos.
- Git: subprocess con git; dulwich 1.2 como respaldo.
- Voz: accessible_output2 0.17 (con DLL de NVDA actualizada); sonidos con winsound o sound_lib.
- Markdown: HTML de la API de GitHub; mistune 3.4 para vista previa local.
- Credenciales: keyring (Administrador de credenciales) o DPAPI con pywin32; cryptography para claves SSH.

## Fuentes

- https://pypi.org/project/wxPython/#files y https://pypi.org/simple/wxpython/
- https://pypi.org/project/cx-Freeze/ y https://pypi.org/project/freeze-core/
- https://pypi.org/project/PyGithub/ , https://pypi.org/project/githubkit/ , https://pypi.org/project/ghapi/
- https://pypi.org/project/requests/ , https://pypi.org/project/httpx/
- https://pypi.org/project/dulwich/ , https://pypi.org/project/pygit2/ , https://pypi.org/project/GitPython/
- https://pypi.org/project/Markdown/ , https://pypi.org/project/mistune/
- https://pypi.org/project/accessible-output2/ , https://pypi.org/project/sound-lib/ , https://pypi.org/project/cytolk/
- https://pypi.org/project/cryptography/ , https://pypi.org/project/keyring/ , https://pypi.org/project/PyNaCl/ , https://pypi.org/project/comtypes/ , https://pypi.org/project/pywin32/ , https://pypi.org/project/truststore/
- Pruebas locales: entorno virtual de Python 3.15 en el directorio temporal de la sesión (importaciones, keyring, BASS, accessible_output2, pygit2.features) y congelación de prueba con cx_Freeze.
