"""Teclado: atajos, menú contextual y Escape en ventanas principales.

Reglas:

- Toda acción del ratón o de una barra de herramientas tiene equivalente de
  teclado (menú con acelerador ``"&Abrir...\\tCtrl+O"`` o tabla de atajos).
- El menú contextual se abre con ``EVT_CONTEXT_MENU`` (tecla Aplicaciones y
  Mayús+F10), NUNCA solo con ``EVT_RIGHT_UP``.
- ``EVT_CHAR_HOOK`` siempre termina en ``evento.Skip()`` para lo que no se
  gestiona; si no, deja de funcionar todo el teclado de la ventana.

PLANTILLA del agente «accesibilidad-wx».
"""

from __future__ import annotations

import logging

from collections.abc import Callable, Sequence

import wx


def vincular_menu_contextual(control: wx.Window, crear_menu: Callable[[], wx.Menu | None]) -> None:
	"""Abre el menú contextual con ratón, tecla Aplicaciones o Mayús+F10.

	Si el evento viene del teclado, la posición es ``wx.DefaultPosition``: el
	menú se coloca junto al elemento enfocado (en listas y árboles) para que
	el lector lo asocie con él.
	"""

	def al_pedir_menu(evento: wx.ContextMenuEvent) -> None:
		menu = crear_menu()
		if menu is None:
			return
		posicion = evento.GetPosition()
		if posicion == wx.DefaultPosition:
			posicion = wx.Point(0, 0)
			if isinstance(control, wx.ListCtrl) and control.GetFocusedItem() != wx.NOT_FOUND:
				posicion = control.GetItemRect(control.GetFocusedItem()).GetBottomLeft()
			elif isinstance(control, wx.TreeCtrl) and control.GetFocusedItem().IsOk():
				rectangulo = control.GetBoundingRect(control.GetFocusedItem())
				if rectangulo:
					posicion = rectangulo.GetBottomLeft()
		else:
			posicion = control.ScreenToClient(posicion)
		control.PopupMenu(menu, posicion)
		menu.Destroy()

	control.Bind(wx.EVT_CONTEXT_MENU, al_pedir_menu)
	# Marca para las pruebas: «este control tiene menú contextual».
	control.crear_menu_contextual = crear_menu


def menu_de_acciones(
	control: wx.Window, acciones: Sequence[tuple[str, Callable[[], object]] | None],
) -> wx.Menu:
	"""Menú con ``(etiqueta, acción)``; ``None`` es un separador.

	Las etiquetas llevan su atajo tras un tabulador (``"&Copiar\tCtrl+C"``):
	cada orden del menú existe también fuera de él.
	"""
	menu = wx.Menu()
	for elemento in acciones:
		if elemento is None:
			menu.AppendSeparator()
			continue
		etiqueta, accion = elemento
		item = menu.Append(wx.ID_ANY, etiqueta)
		control.Bind(wx.EVT_MENU, lambda _evento, a=accion: a(), item)
	return menu


def copiar_texto(texto: str) -> bool:
	"""Copia ``texto`` al portapapeles; ``False`` si Windows no deja abrirlo (otro programa lo tiene).

	``Flush`` deja el texto en el portapapeles aunque después se cierre la aplicación.
	"""
	portapapeles = wx.TheClipboard
	if not portapapeles.Open():
		logging.getLogger(__name__).warning("No se pudo abrir el portapapeles para copiar")
		return False
	try:
		correcto = bool(portapapeles.SetData(wx.TextDataObject(texto)))
		portapapeles.Flush()
	finally:
		portapapeles.Close()
	return correcto


def instalar_atajos(ventana: wx.Window, atajos: Sequence[tuple[int, int, Callable[[], None]]]) -> list[int]:
	"""Crea una tabla de aceleradores para acciones sin elemento de menú.

	::

		instalar_atajos(self, [
			(wx.ACCEL_CTRL, ord("F"), self.buscar),
			(wx.ACCEL_NORMAL, wx.WXK_F5, self.actualizar),
		])

	Documente cada atajo en la ayuda o en la lista de teclas del manual.
	Una segunda llamada SUSTITUYE la tabla anterior: pase todos los atajos de
	la ventana de una vez. Los atajos quedan anotados en
	``ventana._atajos_accesibles`` para que ``revisar_teclado`` busque
	repeticiones y teclas reservadas. Devuelve los ids creados.
	"""
	entradas, ids, anotados = [], [], []
	for modificadores, tecla, accion in atajos:
		identificador = wx.NewIdRef()
		ventana.Bind(wx.EVT_MENU, lambda _e, a=accion: a(), id=identificador)
		entradas.append(wx.AcceleratorEntry(modificadores, tecla, identificador))
		ids.append(int(identificador))
		anotados.append((modificadores, tecla, int(identificador)))
	ventana.SetAcceleratorTable(wx.AcceleratorTable(entradas))
	ventana._atajos_accesibles = anotados
	return ids


def cerrar_con_escape(ventana: wx.TopLevelWindow) -> None:
	"""Escape cierra una ventana que no es diálogo (los diálogos: ``preparar_dialogo``)."""

	def al_pulsar(evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
			ventana.Close()
			return
		evento.Skip()

	ventana.Bind(wx.EVT_CHAR_HOOK, al_pulsar)
