"""Paleta de órdenes (Control+Mayúsculas+O): buscar cualquier orden escribiendo.

Por qué: la aplicación tiene cientos de órdenes repartidas por los menús y por
el menú de acciones de cada lista. Quien no recuerda dónde está «Hacer rama
por defecto» la encuentra escribiendo «defecto». Cada fila dice además su
tecla y su menú, así que la paleta también enseña los atajos.

Cómo:

- Recoge las órdenes de la barra de menús de la ventana activa (con sus
  submenús) y, si la ventana tiene una lista, las acciones disponibles para el
  elemento elegido (las mismas del menú Aplicaciones).
- Filtra al escribir, sin distinguir mayúsculas ni acentos: deben aparecer
  todas las palabras escritas, en cualquier orden.
- Intro (en el campo o en la lista) ejecuta la orden elegida después de
  cerrar la paleta; Escape cierra sin hacer nada.
- ``instalar(ventana)`` añade Control+Mayúsculas+O a una ventana sin tocar su
  propio manejo de teclas.
"""

from __future__ import annotations

import builtins
import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import wx

from app.ui.vistas.base import atajo_visible

log = logging.getLogger(__name__)

#: Tecla de la paleta en todas las ventanas.
TECLA = (wx.MOD_CONTROL | wx.MOD_SHIFT, ord("O"))


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class Orden:
	"""Una orden de la paleta."""

	etiqueta: str
	ruta: str
	atajo: str
	ejecutar: Callable[[], None]

	@property
	def texto(self) -> str:
		partes = [self.etiqueta]
		if self.atajo:
			partes.append(f"({atajo_visible(self.atajo)})")
		if self.ruta:
			partes.append(f"— {self.ruta}")
		return " ".join(partes)


def sin_acentos(texto: str) -> str:
	descompuesto = unicodedata.normalize("NFD", texto or "")
	return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").casefold()


def limpiar_etiqueta(etiqueta: str) -> tuple[str, str]:
	"""«&Actualizar\\tF5» → («Actualizar», «F5»); «A&brir (Intro)» → («Abrir», «Intro»)."""
	texto, _tab, atajo = (etiqueta or "").partition("\t")
	texto = texto.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()
	if not atajo and texto.endswith(")") and " (" in texto:
		base, _parentesis, dentro = texto.rpartition(" (")
		dentro = dentro[:-1]
		# Solo si parece una tecla: «(Intro)», «(Ctrl+N)», «(F5)»; no «(fork)» ni «(más de 1000)».
		if dentro and (any(m in dentro for m in ("Ctrl+", "Alt+", "Shift+", "Mayús")) or dentro in ("Intro", "Supr", "Retroceso")
			or (dentro.startswith("F") and dentro[1:].isdigit())):
			texto, atajo = base.strip(), dentro
	return texto.rstrip("…").rstrip(".").strip() + ("…" if texto.endswith("…") else ""), atajo.strip()


def filtrar(ordenes: list[Orden], busqueda: str) -> list[Orden]:
	"""Órdenes que contienen todas las palabras de ``busqueda`` (en etiqueta, menú o atajo)."""
	palabras = sin_acentos(busqueda).split()
	if not palabras:
		return list(ordenes)
	return [o for o in ordenes if all(p in sin_acentos(f"{o.etiqueta} {o.ruta} {o.atajo}") for p in palabras)]


def ordenes_de_menu(ventana: wx.Window, menu: wx.Menu, ruta: str) -> list[Orden]:
	resultado: list[Orden] = []
	for elemento in menu.GetMenuItems():
		if elemento.IsSeparator():
			continue
		etiqueta, atajo = limpiar_etiqueta(elemento.GetItemLabel())
		submenu = elemento.GetSubMenu()
		if submenu is not None:
			resultado += ordenes_de_menu(ventana, submenu, f"{ruta} > {etiqueta}" if ruta else etiqueta)
			continue
		if not elemento.IsEnabled() or not etiqueta or etiqueta.startswith("("):
			continue

		def lanzar(identificador: int = elemento.GetId()) -> None:
			evento = wx.CommandEvent(wx.wxEVT_MENU, identificador)
			evento.SetEventObject(ventana)
			ventana.GetEventHandler().ProcessEvent(evento)

		resultado.append(Orden(etiqueta, ruta, atajo, lanzar))
	return resultado


def recoger(ventana: wx.Window) -> list[Orden]:
	"""Órdenes de las acciones de la lista activa (primero) y de toda la barra de menús."""
	ordenes: list[Orden] = []
	panel = _panel_con_acciones(ventana)
	nombres_acciones: set[str] = set()
	if panel is not None:
		try:
			for accion in panel.acciones_disponibles():
				etiqueta, atajo_etiqueta = limpiar_etiqueta(accion.etiqueta)
				nombres_acciones.add(sin_acentos(etiqueta))
				ordenes.append(Orden(etiqueta, _("Acciones"), accion.atajo or atajo_etiqueta,
					lambda a=accion, p=panel: p.ejecutar(a)))
		except Exception:  # noqa: BLE001 - sin acciones de la lista, la paleta sigue con los menús
			log.debug("No se pudieron leer las acciones de la lista", exc_info=True)
	barra = ventana.GetMenuBar() if isinstance(ventana, wx.Frame) else None
	# El menú «Acciones» de la ventana principal y de la de repositorio se rehace al abrirlo con las
	# acciones de la lista: ya están arriba, recién leídas, así que ese menú (quizá viejo) se salta.
	menu_de_lista = getattr(ventana, "menu_acciones", None) if panel is not None else None
	if barra is not None:
		for indice in range(barra.GetMenuCount()):
			menu = barra.GetMenu(indice)
			if menu_de_lista is not None and menu is menu_de_lista:
				continue
			titulo, _atajo = limpiar_etiqueta(barra.GetMenuLabel(indice))
			ordenes += ordenes_de_menu(ventana, menu, titulo)
	return ordenes


def _panel_con_acciones(ventana: wx.Window) -> Any:
	panel = getattr(ventana, "panel_actual", None)
	if callable(panel):
		panel = panel()
	if panel is not None and hasattr(panel, "acciones_disponibles"):
		return panel
	# Ventanas de detalle: la lista que tenga el foco, si es una PanelLista.
	foco = wx.Window.FindFocus()
	while foco is not None and foco is not ventana:
		if hasattr(foco, "acciones_disponibles") and hasattr(foco, "ejecutar"):
			return foco
		foco = foco.GetParent()
	return None


class DialogoPaleta(wx.Dialog):
	"""Campo de búsqueda y lista de órdenes filtrada."""

	def __init__(self, padre: wx.Window, ordenes: list[Orden]) -> None:
		super().__init__(padre, title=_("Paleta de órdenes"), size=(640, 460), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.ordenes = ordenes
		self.visibles: list[Orden] = list(ordenes)
		self.elegida: Orden | None = None
		raiz = wx.BoxSizer(wx.VERTICAL)
		raiz.Add(wx.StaticText(self, label=_("&Buscar una orden:")), 0, wx.LEFT | wx.TOP | wx.RIGHT, 8)
		self.campo = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		self.campo.SetHelpText(_("Escriba parte del nombre de la orden, de su menú o de su tecla. Flecha abajo pasa a la lista; "
			"Intro ejecuta la primera orden encontrada o la elegida."))
		raiz.Add(self.campo, 0, wx.EXPAND | wx.ALL, 8)
		raiz.Add(wx.StaticText(self, label=_("&Órdenes:")), 0, wx.LEFT | wx.RIGHT, 8)
		self.lista = wx.ListBox(self, choices=[o.texto for o in ordenes], style=wx.LB_SINGLE)
		self.lista.SetHelpText(_("Órdenes de esta ventana con su tecla y su menú. Intro la ejecuta."))
		raiz.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_ejecutar = wx.Button(self, wx.ID_OK, _("&Ejecutar"))
		botones.Add(self.boton_ejecutar, 0, wx.ALL, 4)
		botones.Add(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")), 0, wx.ALL, 4)
		raiz.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
		self.SetSizer(raiz)
		self.SetEscapeId(wx.ID_CANCEL)
		if self.visibles:
			self.lista.SetSelection(0)
		self.campo.Bind(wx.EVT_TEXT, lambda _e: self.filtrar(self.campo.GetValue()))
		self.campo.Bind(wx.EVT_TEXT_ENTER, lambda _e: self.ejecutar())
		self.campo.Bind(wx.EVT_KEY_DOWN, self._al_tecla_campo)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda _e: self.ejecutar())
		self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
		self.boton_ejecutar.Bind(wx.EVT_BUTTON, lambda _e: self.ejecutar())
		self.CentreOnParent()
		self.campo.SetFocus()

	def filtrar(self, busqueda: str) -> None:
		self.visibles = filtrar(self.ordenes, busqueda)
		self.lista.Set([o.texto for o in self.visibles])
		if self.visibles:
			self.lista.SetSelection(0)

	def ejecutar(self) -> None:
		indice = self.lista.GetSelection()
		if not self.visibles:
			wx.Bell()
			return
		self.elegida = self.visibles[indice if 0 <= indice < len(self.visibles) else 0]
		self.EndModal(wx.ID_OK)

	def _al_tecla_campo(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_DOWN, wx.WXK_UP) and not evento.HasAnyModifiers() and self.visibles:
			self.lista.SetFocus()
			return
		evento.Skip()

	def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.ejecutar()
			return
		evento.Skip()


def abrir(ventana: wx.Window) -> None:
	"""Muestra la paleta de ``ventana`` y ejecuta la orden elegida."""
	ordenes = recoger(ventana)
	if not ordenes:
		wx.Bell()
		return
	dialogo = DialogoPaleta(ventana, ordenes)
	try:
		resultado = dialogo.ShowModal()
		elegida = dialogo.elegida
	finally:
		dialogo.Destroy()
	if resultado == wx.ID_OK and elegida is not None:
		# Después de cerrar la paleta: la orden puede abrir otro diálogo o mover el foco.
		wx.CallAfter(_ejecutar_seguro, elegida)


def _ejecutar_seguro(orden: Orden) -> None:
	try:
		orden.ejecutar()
	except Exception:  # noqa: BLE001 - una orden que falla no debe cerrar la aplicación
		log.exception("Falló la orden «%s» de la paleta", orden.etiqueta)


def instalar(ventana: wx.Window) -> None:
	"""Añade Control+Mayúsculas+O a ``ventana`` (se suma a su propio EVT_CHAR_HOOK)."""
	def al_tecla(evento: wx.KeyEvent) -> None:
		if (evento.GetModifiers(), evento.GetKeyCode()) == TECLA:
			abrir(ventana)
			return
		evento.Skip()

	ventana.Bind(wx.EVT_CHAR_HOOK, al_tecla)
