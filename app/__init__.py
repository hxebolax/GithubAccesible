"""Paquete principal de la aplicación.

- ``core``: rutas, versión, configuración, registro, instancia única, voz.
- ``services``: lógica sin wx (se puede probar sin interfaz).
- ``ui``: ventanas y diálogos.
"""

# Instala _, N_, ngettext... en builtins (en español mientras no se elija idioma): así
# cualquier módulo de la aplicación puede marcar textos aunque se importe antes del arranque.
from app.core import i18n  # noqa: E402, F401
