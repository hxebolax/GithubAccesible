# Instrucciones para una IA que trabaje en GitHub Accesible

Aplicación de escritorio Python 3.15 + wxPython 4.3 para Windows, accesible con lector de pantalla, para manejar GitHub y git local. Todo en español de España.

## Convenciones

- Sigue `E:\Antigravity\Agentes\compartido\perfil-desarrollador.md` y los agentes de `E:\Antigravity\Agentes\agentes` (accesibilidad-wx, configuracion, actualizador, pruebas, etc.).
- Tabulaciones, `ruff` (`.venv\Scripts\ruff.exe check .`), docstrings y comentarios en español que expliquen el porqué.
- Todo lo que genera la aplicación va en `data/` (portable). Los tokens, cifrados en `data/config/secretos.dat`.
- Accesibilidad: `StaticText` justo antes de cada control, letras de acceso únicas por pantalla (pruébalo con `app.ui.accesibilidad.revision_teclado.afirmar_teclado_correcto`), botones en español, nada de trabajo en el hilo de la interfaz.
- El foco solo lo mueve la persona: elegir en una lista de secciones, un desplegable o unos botones de opción no cambia el foco. Si cambias de página un `Notebook`/`Simplebook` o rehaces controles en esa respuesta, envuélvelo en `app.ui.accesibilidad.foco.conservar_foco` (wx da el foco a la página nueva). Para dar el foco por programa usa `app.ui.accesibilidad.foco.enfocar` (no hace nada si la ventana no se ve; con NVDA, enfocar un RichEdit oculto provoca el aviso COM 0x8001010D).
- Las explicaciones (`SetHelpText`) se leen con Control+H mediante `texto_ayuda()`; el lector solo las oye si lo permiten `accesibilidad.explicacion_controles` y `accesibilidad.explicacion_filas` (lo decide `ProveedorAyuda`). No leas la ayuda con `GetHelpText()`.

## Piezas que hay que reutilizar

- API de GitHub: `app/services/github/` (`ctx.api()` devuelve `ApiGitHub`, con todas las operaciones). Si falta una, añádela ahí con su prueba.
- Listas: `app/ui/vistas/base.py` (`DefinicionVista`, `Columna`, `Accion`, `PanelLista`). Etiqueta común «&Lista de …».
- Trabajo en segundo plano y avisos: `app/ui/comunes.py` (`en_segundo_plano`, `elegir_uno`, `elegir_varios`, `confirmar_peligro`).
- Editor Markdown con borradores: `app/ui/editor.py`. Visor de diferencias: `app/ui/detalle/diferencias.py`. Abrir cualquier cosa: `app/ui/abrir.py`.
- Contexto compartido: `app/core/contexto.py` (configuración, cuentas, tareas, sonidos, voz, almacén SQLite).

## Comprobaciones

```
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe main.py --comprobar-arranque
.venv\Scripts\python.exe tools\prueba_actualizacion_real.py
```

## Publicar

`APP_VERSION` en `app/core/version.py` y `pyproject.toml`, entrada en `docs/changelog.md` y `.venv\Scripts\python.exe tools\publicar.py`. La clave privada de firma está en `tools/claves/` y nunca se sube.
