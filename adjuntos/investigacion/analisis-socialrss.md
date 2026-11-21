# Análisis de SocialRSS (E:\Antigravity\ClienteMastodonRSS)

Patrones de SocialRSS que GitHub Accesible replica. Rutas relativas al proyecto SocialRSS.

## Lista multicolumna accesible

- Clase `AccessibleListCtrl` en `app/ui/accessible_controls.py:94`. Normal o virtual (`OnGetItemText`).
- Guarda el texto íntegro de cada celda en un diccionario (`_celdas`), porque Windows corta a unos 511 caracteres.
- Teclas: Izquierda y Derecha cambian de columna y la leen; Ctrl+1 a Ctrl+9 leen la columna N; Intro activa; Espacio se consume.
- Lectura de columna (`_speak_cell`, línea 723): lee las preferencias en cada anuncio:
  - `accessibility.colnav_row_num`: decir «Fila N».
  - `accessibility.colnav_col_header`: decir el nombre de la columna.
  - `accessibility.colnav_cell_value`: decir el contenido.
  - Si las tres están desactivadas, se dice el contenido igualmente.
  - Orden fijo: «Fila N, cabecera, contenido», unido con comas, con interrupción.
- Sin doble lectura: al moverse arriba y abajo la fila la lee el propio lector; la app solo habla al moverse por columnas.
- Inserción silenciosa de novedades con una propiedad de ventana que lee un complemento de NVDA.

## Lista de casillas accesible

- `AccessibleCheckListBox` (`accessible_controls.py:906-967`) con `wx.Accessible`: rol `ROLE_SYSTEM_CHECKBUTTON` y estado `CHECKED` por elemento (childId empieza en 1).
- Al marcar: `NotifyWinEvent(EVENT_OBJECT_STATECHANGE=0x800A, hwnd, OBJID_CLIENT=-4, idx+1)` y además anuncia «etiqueta, marcado/desmarcado».
- No tiene preferencias sobre qué se lee. GitHub Accesible lo mejora: preferencias para decir el estado, la posición («3 de 10») y el orden (estado antes o después del texto).
- Nota: wxPython 4.3 ya expone el estado de casilla de serie en CheckListBox.

## Diálogo de preferencias

- Árbol (`wx.TreeCtrl`, raíz oculta) a la izquierda y `wx.Simplebook` a la derecha; al cambiar de página el foco vuelve al árbol; Tab entra al panel.
- Botones «&Guardar» y «&Cancelar»; guardado por lotes (una sola escritura).
- Página Accesibilidad: modo lector, sonidos, anuncios de voz, modo de avisos (voz, mensaje o ambos), notificación de Windows, braille, retardo de voz (0 a 600 ms, 120 por defecto) y la sección «Navegación por columnas» con las tres casillas y la nota «Si desactivas las tres, se dirá igualmente el contenido de la celda».
- Página Sonidos: volumen (deslizador 0 a 100), silenciar todo, paquete de sonidos, dispositivo de salida y una lista de casillas con los eventos (marcados = activos; se guarda `disabled_events`).
- Las preferencias de voz, sonidos y columnas se leen en cada uso, por lo que se aplican sin reiniciar.

## Sonidos

- `app/services/audio/sound_manager.py`, con BASS (basskit) en Windows.
- WAV mono 16 bits 44100 Hz; si faltan, se sintetizan con el módulo `wave` (`sound_generator.py`).
- Carpeta `data/sounds/<paquete>/`; el paquete `default` es el de respaldo.
- Diccionario evento → archivo; no suena si los sonidos están desactivados, silenciados o el evento está desactivado.
- Reproducción en un único hilo con cola; el volumen se lee en cada sonido.
- Diálogo para probar sonidos.

## Actualizador

- `URL_BASE = "https://xebolax.synology.me/SocialRSS"`; la carpeta local sincronizada es `C:\Users\xebol\SynologyDrive\web\SocialRSS`.
- `version.json`: `version`, `file`, `sha256`, `size`, `date`, `firma_ed25519`.
- Firma Ed25519 en base64 del mensaje `"{version}:{sha256}"`; clave pública en hexadecimal incrustada en el código.
- Clave privada en `tools/claves/<app>_ed25519.key` (excluida por `.gitignore`).
- `comprimir_build.py` comprime `build/<App>` (carpeta raíz dentro del zip), calcula sha256, escribe y firma `version.json`. La subida al servidor es manual.
- Script `.bat` que espera al proceso, copia con robocopy sin purgar, relanza y se borra.

## Otros patrones

- Voz: `accessible_output2.outputs.auto.Auto()`, hilo único, agrupación de mensajes, retardo configurable, braille opcional.
- Ayuda Ctrl+H con nombre y ayuda del control enfocado.
- Visor de registro: lista virtual con Hora, Nivel, Módulo, Mensaje; filtro por nivel; búsqueda F3; seguir en vivo.
- Visor HTML: WebView Edge, HTML saneado, enlaces al navegador del sistema, Escape cierra.
- Gestor de tareas con `ThreadPoolExecutor`, claves únicas, cancelación, progreso, sonidos de éxito y error.
- Instancia única que trae al frente la ventana existente.
