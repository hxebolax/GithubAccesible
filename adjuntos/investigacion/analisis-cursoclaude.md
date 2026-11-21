# Análisis del uso de HTML en CursoClaude (E:\Antigravity\CursoClaude)

Cómo usa HTML una aplicación wxPython accesible. Rutas relativas a `version-wxpython/`.

## Tecnología

- `wx.html2.WebView` con el motor Edge (WebView2). Nunca `wx.html.HtmlWindow` (poco accesible).
- Markdown a HTML con la librería `markdown` (extensiones `extra`, `sane_lists`, `toc`).
- Enlaces externos al navegador del sistema con `wx.LaunchDefaultBrowser` (solo https, http y mailto).
- Perfil de WebView2 portable: `WEBVIEW2_USER_DATA_FOLDER = data/cache/webview` antes de crear ningún WebView.
- Páginas grandes: se escriben en `data/cache/paginas` y se cargan con `LoadURL(archivo.as_uri())` para evitar el límite de unos 2 MB de `SetPage`.
- Compilado: `WebView2Loader.dll` junto al exe.

## Accesibilidad

- Un único `<h1 tabindex="-1">` por página; secciones con `aria-labelledby`; tablas en una región con nombre; código en `<pre tabindex="0">`.
- `<html lang="es">`, CSP estricta, CSS con foco visible, temas claro, oscuro y alto contraste, `forced-colors`.
- Nombre accesible del WebView con `SetName` o con una subclase de `wx.Accessible`.
- Foco inicial: la página avisa «lista» por `postMessage` y Python responde con `SetFocus()` y un guion que enfoca el h1.
- Teclas: Edge se queda con el teclado, así que un guion en `keydown` (fase de captura) traduce la tecla a un nombre («Escape», «Ctrl+f»), y si está en el mapa la envía a Python con `window.chrome.webview.postMessage`. Python la atiende con `wx.CallAfter`.
- Canal: `AddScriptMessageHandler("nombre")` y `EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED`.
- Se desactivan DevTools, las teclas aceleradoras del navegador y el menú contextual de Edge.
- Escape puede llegar dos veces: una guarda `_cerrado` lo evita.

## Respaldo sin WebView2

- `WebView.IsBackendAvailable(WebViewBackendEdge)` dentro de try/except, o preferencia «Usar el modo de texto».
- Temporizador de guarda de 30 s: si Edge no carga, se pasa a modo texto.
- Modo texto: lista de secciones (`wx.ListBox`) y `wx.TextCtrl` multilínea de solo lectura con `TE_RICH2`.
- Búsqueda: `web.Find` en HTML; `find` + `SetSelection` en texto.

## Plantilla a copiar

- `app/ui/visor_ayuda.py` (es la plantilla del agente documentacion-usuario, ya copiada en GitHub Accesible).
- De `app/ui/vista_contenido.py`: `edge_disponible`, `fijar_perfil_portable`, `clasificar_navegacion`, temporizador de guarda.
