# Activar el inicio de sesión con el navegador

Desde la versión 1.0.1 la aplicación ya trae el Client ID de la aplicación OAuth «Accesible para GitHub» del autor, así que el inicio con el navegador funciona sin configurar nada. Esta guía sirve para mantener esa aplicación, para usar una propia o para GitHub Enterprise Server.

El inicio de sesión «con el navegador y un código» usa el flujo de dispositivo de OAuth de GitHub. Para funcionar necesita una aplicación OAuth registrada en GitHub y su identificador público (Client ID). Este documento explica cómo registrarla, cómo probarla y cómo dejarla fija en la aplicación para que nadie tenga que configurar nada.

El Client ID **no es secreto**: el flujo de dispositivo no usa el secreto de cliente (Client secret), así que no hace falta generarlo ni guardarlo. Puede ir escrito en el código y en el repositorio público.

## 1. Registrar la aplicación OAuth (una sola vez)

1. Inicie sesión en GitHub en el navegador y abra <https://github.com/settings/applications/new>. Es lo mismo que ir a Settings, Developer settings, OAuth Apps y pulsar «New OAuth App».
   - Si prefiere que la aplicación pertenezca a una organización, use `https://github.com/organizations/NOMBRE/settings/applications/new`.
2. Rellene el formulario:
   - **Application name**: `Accesible para GitHub`. Es el nombre que verá cada persona en la página de autorización. GitHub no admite nombres que empiecen por «GitHub» o «Gist» (en mayúsculas o minúsculas), así que no vale «GitHub Accesible» ni «GithubAccesible».
   - **Homepage URL**: `https://github.com/hxebolax/GithubAccesible`.
   - **Application description** (opcional): `Aplicación de escritorio accesible con lector de pantalla para manejar GitHub y git.`
   - **Redirect URI** (en formularios antiguos, «Authorization callback URL»): `https://github.com/hxebolax/GithubAccesible`. El flujo de dispositivo no lo usa, pero GitHub obliga a rellenarlo.
   - **Allow wildcard matching**: sin marcar.
   - **Enable Device Flow**: márquela. Sin esta casilla GitHub responde «device_flow_disabled» y el inicio con el navegador no funciona.
   - **Expire user access tokens**: mejor sin marcar. Si se marca, el token caduca a las 8 horas y la aplicación lo renueva sola con el token de renovación (que dura 6 meses sin uso); funciona, pero sin marcar hay menos que pueda fallar.
3. Pulse «Register application».
4. En la página que aparece, copie el **Client ID** (empieza por `Ov23` o `Iv1.` y tiene unos 20 caracteres). No pulse «Generate a new client secret»: no se necesita.

Si se le olvidó marcar «Enable Device Flow», vuelva a esa página (Settings, Developer settings, OAuth Apps, Accesible para GitHub), marque la casilla y pulse «Update application».

Opcionalmente puede subir el icono de la aplicación (`data/icons/app.ico` convertido a PNG) en «Upload new logo»: se muestra en la página de autorización.

## 2. Probarlo sin compilar nada

1. Abra GitHub Accesible, vaya a Herramientas, Preferencias (Control+P), pestaña **Cuentas**.
2. Pegue el Client ID en «Identificador de la aplicación OAuth (Client ID)» y pulse Aceptar.
3. Abra Archivo, «Iniciar sesión con otra cuenta» (Control+Mayúsculas+L), elija «Con el navegador y un código» y pulse «Iniciar sesión».
4. La aplicación copia y deletrea el código y abre <https://github.com/login/device>. Péguelo, pulse «Continue» y después «Authorize».
5. La ventana de inicio de sesión se completa sola y la cuenta aparece en la barra de estado.

Lo que se escribe en Preferencias tiene prioridad sobre el valor del código, así que sirve también para probar otra aplicación OAuth o para GitHub Enterprise.

## 3. Dejarlo fijo en la aplicación (para todo el mundo)

1. En `app/services/github/autenticacion.py`, escriba el Client ID en `ID_CLIENTE_OAUTH`:

   ```python
   ID_CLIENTE_OAUTH = "Ov23xxxxxxxxxxxxxxxx"
   ```

2. Vacíe el campo de Preferencias, Cuentas en su propia instalación para comprobar que se usa el del código.
3. Suba la versión (por ejemplo, 1.0.1) en `app/core/version.py` y `pyproject.toml`, y añada en `docs/changelog.md` algo como: «Ya se puede iniciar sesión con el navegador y un código sin configurar nada».
4. Ejecute las comprobaciones y publique:

   ```
   .venv\Scripts\python.exe -m pytest
   .venv\Scripts\python.exe tools\publicar.py
   ```

Las instalaciones existentes recibirán la versión nueva con el actualizador y el inicio con el navegador funcionará sin tocar nada.

## GitHub Enterprise Server

Las aplicaciones OAuth de github.com no sirven en un servidor de empresa. Quien use GitHub Enterprise Server debe registrar su propia aplicación en `https://SU-SERVIDOR/settings/applications/new` con los mismos datos y la casilla «Enable Device Flow» marcada (el administrador del servidor tiene que tener activado el flujo de dispositivo), y escribir su Client ID en Preferencias, Cuentas.

## Si algo falla

- **«device_flow_disabled»**: falta marcar «Enable Device Flow» en la aplicación OAuth.
- **«incorrect_client_credentials»** o «Not Found»: el Client ID está mal copiado o es de otro servidor.
- **La organización no muestra sus repositorios**: si la organización restringe las aplicaciones OAuth, en la página de autorización pulse «Request» (o «Grant» si es propietario) junto a su nombre. También puede hacerlo después en Settings, Applications, Authorized OAuth Apps, Accesible para GitHub.
- **El código caducó**: dura 15 minutos. Vuelva a pulsar «Iniciar sesión».
