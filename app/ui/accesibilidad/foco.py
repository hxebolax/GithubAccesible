"""Regla de la aplicación: el foco solo lo mueve la persona.

Elegir algo en un desplegable, una lista de secciones o unos botones de opción
cambia lo que se ve, pero el foco se queda en el control donde se eligió. Es la
persona quien decide cuándo ir al contenido (Tabulador, Intro, F6...).

Problema que resuelve: en Windows, cambiar la página de un ``wx.Notebook`` o un
``wx.Simplebook`` (``ChangeSelection``/``SetSelection``) le da el foco a la página
nueva aunque estuviera en otro control. Por ejemplo, en la búsqueda, al bajar con
la flecha en «Buscar» el foco saltaba a la lista «Buscar el texto en».

``conservar_foco`` lo devuelve en el acto (dentro del mismo manejador, antes de
que el lector de pantalla procese el evento de foco intermedio, que descarta por
no seguir vigente), así que no se oye nada.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import wx


def devolver_foco(ventana: wx.Window, foco: wx.Window | None) -> None:
	"""Devuelve el foco a ``foco`` si se movió solo dentro de la misma ventana.

	No hace nada si ``foco`` ya no existe, está oculto o desactivado, o pertenece a
	otra ventana de nivel superior (no se roba el foco a otra ventana o diálogo).
	"""
	if not foco or not ventana:
		return
	if wx.GetTopLevelParent(foco) is not wx.GetTopLevelParent(ventana):
		return
	if wx.Window.FindFocus() is foco:
		return
	if foco.IsShownOnScreen() and foco.IsEnabled():
		foco.SetFocus()


def enfocar(control: wx.Window | None) -> bool:
	"""Da el foco a ``control`` solo si se ve en pantalla. Devuelve si lo hizo.

	Enfocar un control de una ventana oculta no le sirve a nadie y, con NVDA en
	marcha, en un campo RichEdit (``TE_RICH``/``TE_RICH2``) hace que el ayudante
	que NVDA inyecta en el proceso llame a COM mientras Windows despacha el
	mensaje síncrono del cambio de foco. COM lo rechaza con 0x8001010D
	(RPC_E_CANTCALLOUT_ININPUTSYNCCALL); se recupera solo, pero ``faulthandler``
	lo imprime como «Windows fatal exception». Con la ventana visible no ocurre.
	"""
	if not control or not control.IsShownOnScreen():
		return False
	control.SetFocus()
	return True


@contextmanager
def conservar_foco(ventana: wx.Window) -> Iterator[None]:
	"""Ejecuta el bloque y deja el foco donde estaba antes de él.

	Uso::

		with conservar_foco(self):
			self.libro.ChangeSelection(indice)
	"""
	foco = wx.Window.FindFocus()
	try:
		yield
	finally:
		devolver_foco(ventana, foco)
