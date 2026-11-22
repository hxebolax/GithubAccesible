"""Diálogo «Acerca de»: nombre, versión y datos técnicos útiles para soporte.

No se usa ``wx.adv.AboutBox``: su ventana nativa mezcla etiquetas estáticas
que el lector no siempre recorre y no deja copiar el texto. Aquí va todo en
un campo de solo lectura con «Copiar al portapapeles», que es lo que el
usuario necesita para pegar en un correo de soporte.
"""

from __future__ import annotations

import builtins
import platform
import sys

import wx

from app.core import paths
from app.core.version import ANIO_COPYRIGHT, APP_VERSION, AUTOR, LICENCIA, NOMBRE_APLICACION, URL_PROYECTO
from app.ui.dialogo_texto import mostrar_texto


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# Para el catálogo: es el texto de LICENCIA (version.py se importa antes que la traducción y no puede marcarlo).
N_("GPL (Licencia Pública General de GNU), versión 3")


def texto_acerca_de() -> str:
	"""Compone el texto del diálogo (sin wx en la lógica, para poder probarlo)."""
	lineas = [
		f"{NOMBRE_APLICACION}",
		_("Versión: {version}").format(version=APP_VERSION),
		_("Autor: {autor}").format(autor=AUTOR),
		f"Copyright (C) {ANIO_COPYRIGHT} {AUTOR}",
		_("Licencia: {licencia}").format(licencia=_(LICENCIA)),
		_("Página del proyecto: {url}").format(url=URL_PROYECTO),
		"",
		_(
			"Aplicación accesible para Windows con la que manejar GitHub entero desde el teclado y con lector "
			"de pantalla (NVDA, JAWS, Narrador): repositorios, código, issues, pull requests con revisión línea a "
			"línea, GitHub Actions, releases, gists, discusiones, proyectos, organizaciones, notificaciones, "
			"seguridad y git local (cambios, commits, ramas, conflictos), con varias cuentas y GitHub Enterprise."
		),
		"",
		_("Datos técnicos:"),
		_("Versión de Python: {version} ({bits})").format(version=platform.python_version(), bits=platform.architecture()[0]),
		_("Versión de wxPython: {version}").format(version=wx.version()),
		_("Sistema: {sistema}").format(sistema=platform.platform()),
		_("Versión compilada: {valor}").format(valor=_("sí") if paths.CONGELADA else _("no")),
		_("Carpeta de datos: {ruta}").format(ruta=paths.ruta_datos()),
		_("Ejecutable: {ruta}").format(ruta=sys.executable),
	]
	return "\n".join(lineas)


def mostrar_acerca_de(padre: wx.Window | None) -> None:
	"""Abre el diálogo «Acerca de» de forma modal."""
	mostrar_texto(
		padre,
		_("Acerca de {nombre}").format(nombre=NOMBRE_APLICACION),
		_("&Información:"),
		texto_acerca_de(),
		copiable=True,
	)
