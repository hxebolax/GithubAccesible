"""Icono de la bandeja del sistema con menú accesible.

- Por defecto el icono solo existe mientras la ventana está oculta en la
  bandeja: al restaurarla se quita. Con «Icono en la bandeja todo el tiempo»
  (Preferencias, General) se queda siempre.
- Su texto (lo que lee el lector al llegar a él) dice cuántas notificaciones
  hay sin leer.
- El menú se construye en ``CreatePopupMenu`` (wx lo pide en cada clic
  derecho o tecla Aplicaciones) con etiquetas en español y ``&``; las órdenes
  las da la ventana principal en cada momento (``ordenes``), así el menú
  siempre dice lo que pasa ahora («Ocultar» o «Mostrar», cuántas notificaciones...).
- Desde el teclado: Windows+B lleva a la bandeja, las flechas al icono, e
  Intro o la tecla Aplicaciones lo activan o abren el menú.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Sequence

import wx
import wx.adv

from app.core import paths

log = logging.getLogger(__name__)

#: Orden del menú: (etiqueta con &, función) o ``None`` para un separador.
OrdenBandeja = tuple[str, Callable[[], None]] | None


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class IconoBandeja(wx.adv.TaskBarIcon):
	"""Icono de bandeja; las acciones se inyectan desde la ventana principal.

	:param al_restaurar: lo que hace un clic o Intro sobre el icono.
	:param al_salir: «Salir» del menú.
	:param ordenes: función que devuelve las órdenes del menú (entre «Mostrar» y «Salir»).
	"""

	def __init__(self, texto: str, al_restaurar: Callable[[], None], al_salir: Callable[[], None],
		ordenes: Callable[[], Sequence[OrdenBandeja]] | None = None) -> None:
		super().__init__()
		self._texto = texto
		self._al_restaurar = al_restaurar
		self._al_salir = al_salir
		self._ordenes = ordenes
		# Un clic o un doble clic restauran: la acción más frecuente, a un gesto.
		self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, self._restaurar)
		self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self._restaurar)

	@property
	def texto(self) -> str:
		return self._texto

	def mostrar(self) -> bool:
		"""Pone el icono en la bandeja. El texto emergente es lo que lee el lector."""
		return bool(self.SetIcon(_icono_aplicacion(), self._texto))

	def cambiar_texto(self, texto: str) -> None:
		"""Cambia el texto del icono (p. ej. el número de notificaciones) si ya está puesto."""
		if texto == self._texto:
			return
		self._texto = texto
		if self.IsIconInstalled():
			self.SetIcon(_icono_aplicacion(), texto)

	def quitar(self) -> None:
		"""Quita el icono y destruye el objeto (hay que llamarlo siempre al cerrar)."""
		if self.IsIconInstalled():
			self.RemoveIcon()
		self.Destroy()

	def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802 - nombre impuesto por wx
		"""Menú contextual del icono."""
		menu = wx.Menu()
		elemento_mostrar = menu.Append(wx.ID_ANY, _("&Mostrar la ventana"))
		menu.Bind(wx.EVT_MENU, self._restaurar, elemento_mostrar)
		ordenes = list(self._ordenes() if self._ordenes is not None else [])
		if ordenes:
			menu.AppendSeparator()
		for orden in ordenes:
			if orden is None:
				menu.AppendSeparator()
				continue
			etiqueta, funcion = orden
			elemento = menu.Append(wx.ID_ANY, etiqueta)
			# CallAfter: la orden puede abrir un diálogo, y no conviene hacerlo con el menú aún abierto.
			menu.Bind(wx.EVT_MENU, lambda _evento, f=funcion: wx.CallAfter(f), elemento)
		menu.AppendSeparator()
		elemento_salir = menu.Append(wx.ID_EXIT, _("&Salir"))
		menu.Bind(wx.EVT_MENU, lambda _evento: self._al_salir(), elemento_salir)
		return menu

	def _restaurar(self, _evento: wx.Event | None = None) -> None:
		self._al_restaurar()


def _icono_aplicacion() -> wx.Icon:
	"""``data/icons/app.ico`` si existe; si no, un icono genérico de wx."""
	ruta = paths.ruta_iconos() / "app.ico"
	if ruta.is_file():
		icono = wx.Icon(str(ruta), wx.BITMAP_TYPE_ICO)
		if icono.IsOk():
			return icono
		log.warning("El icono %s no es válido; se usa el genérico", ruta)
	icono = wx.Icon()
	icono.CopyFromBitmap(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16)))
	return icono
