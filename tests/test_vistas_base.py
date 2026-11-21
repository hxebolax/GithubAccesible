"""Pruebas del marco de listas (PanelLista), del visor de diferencias y del editor."""

from __future__ import annotations

import wx

from app.services.github.cliente import Pagina
from app.ui.vistas.base import Accion, Columna, DefinicionVista, PanelLista, normalizar_atajo
from tests.apoyo_app import crear_contexto


def _definicion(cargar, acciones=()):
	return DefinicionVista(
		"prueba", "Prueba",
		[Columna("nombre", "Nombre", lambda e, c: e["nombre"]), Columna("extra", "Extra", lambda e, c: e.get("extra", ""), visible=False)],
		cargar, acciones=list(acciones), url=lambda e: e.get("url", ""),
	)


def test_panel_carga_pagina_y_anuncia(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()
	paginas = {1: Pagina([{"nombre": "uno"}, {"nombre": "dos"}], siguiente="x"), 2: Pagina([{"nombre": "tres"}])}
	panel = PanelLista(marco, ctx, _definicion(lambda api, n, p: paginas[n]))
	hijos = list(panel.GetChildren())
	assert isinstance(hijos[hijos.index(panel.lista) - 1], wx.StaticText), "la etiqueta va justo antes de la lista"
	panel.cargar()
	assert panel.lista.numero_filas() == 2 and panel.hay_mas
	assert panel.lista.GetColumnCount() == 1, "solo columnas visibles por defecto"
	assert "listo" in ctx.sonidos.eventos
	panel.cargar_mas()
	assert [panel.lista.texto_celda(i, 0) for i in range(3)] == ["uno", "dos", "tres"]
	assert not panel.hay_mas and "pagina" in ctx.sonidos.eventos


def test_columnas_configurables_y_aplicadas_en_caliente(app_wx, marco):
	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion(lambda api, n, p: [{"nombre": "a", "extra": "b"}]))
	panel.cargar()
	ctx.config.establecer("listas.columnas", {"prueba": ["extra", "nombre"]})
	panel.rehacer_columnas()
	assert panel.lista.GetColumnCount() == 2
	assert panel.lista.texto_celda(0, 0) == "b" and panel.lista.texto_celda(0, 1) == "a"


def test_error_de_carga_se_anuncia(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()

	def falla(api, n, p):
		raise RuntimeError("sin conexión")

	panel = PanelLista(marco, ctx, _definicion(falla))
	panel.cargar()
	assert "error" in ctx.sonidos.eventos
	assert any("sin conexión" in a for a in anuncios)
	assert "sin conexión" in panel.estado.GetLabel()


def test_filtro_local(app_wx, marco, dialogo_modal):
	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion(lambda api, n, p: [{"nombre": "rojo"}, {"nombre": "verde"}, {"nombre": "rojizo"}]))
	panel.cargar()

	def escribir(dialogo):
		pendientes = list(dialogo.GetChildren())
		while pendientes:
			hijo = pendientes.pop(0)
			if isinstance(hijo, wx.TextCtrl):
				hijo.SetValue("roj")
				break
			pendientes.extend(hijo.GetChildren())
		return wx.ID_OK

	dialogo_modal.responder(escribir)
	panel.pedir_filtro()
	assert panel.lista.numero_filas() == 2
	panel.quitar_filtro()
	assert panel.lista.numero_filas() == 3


def test_acciones_y_atajos(app_wx, marco):
	ctx, _api, _a = crear_contexto()
	hechas = []
	acciones = [
		Accion("&Borrar", lambda p, e: hechas.append(("borrar", e["nombre"])), "Supr"),
		Accion("&Solo a veces", lambda p, e: None, disponible=lambda p, e: False),
	]
	panel = PanelLista(marco, ctx, _definicion(lambda api, n, p: [{"nombre": "x"}], acciones))
	panel.cargar()
	etiquetas = [a.etiqueta for a in panel.acciones_disponibles()]
	assert "&Borrar" in etiquetas and "&Solo a veces" not in etiquetas
	menu = panel.crear_menu(en_barra=True)
	textos = [i.GetItemLabel() for i in menu.GetMenuItems() if not i.IsSeparator()]
	assert all("\t" not in t for t in textos), "en la barra de menús no se registran atajos globales"
	assert any("(Supr)" in t for t in textos)
	evento = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
	evento.SetKeyCode(wx.WXK_DELETE)
	panel.lista.GetEventHandler().ProcessEvent(evento)
	assert hechas == [("borrar", "x")]
	menu.Destroy()


def test_normalizar_atajo():
	assert normalizar_atajo("Ctrl+Mayús+c") == "Ctrl+Shift+C"
	assert normalizar_atajo("Shift+Ctrl+F") == "Ctrl+Shift+F"


def test_visor_de_diferencias_navega_y_suena(app_wx, marco):
	from app.ui.detalle.diferencias import PanelDiferencias
	from tests.test_git_y_diff import DIFF

	ctx, _api, anuncios = crear_contexto()
	panel = PanelDiferencias(marco, ctx, comentarios={("app/uno.py", "RIGHT", 2): ["¿Por qué 3?"]})
	panel.mostrar(DIFF)
	assert panel.lista.GetColumnCount() == 4
	assert panel.lista.texto_celda(0, 0) == "Archivo"
	panel.siguiente_cambio()
	linea = panel.linea_actual()
	assert linea.tipo == "eliminada" and linea.texto == "b = 2"
	assert panel.lista.texto_celda(panel.actual, 0) == "Eliminada"
	panel.siguiente_cambio()
	assert panel.linea_actual().texto == "y"
	panel.siguiente_archivo()
	assert panel.linea_actual().archivo == "nuevo.txt"
	panel.siguiente_archivo()
	assert anuncios[-1] == "No hay más archivos."
	assert panel.comentarios_de(panel.lineas[4]) == ["¿Por qué 3?"]


def test_visor_respeta_preferencias_de_columnas(app_wx, marco):
	from app.ui.detalle.diferencias import PanelDiferencias

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("accesibilidad.diff_decir_tipo", False)
	panel = PanelDiferencias(marco, ctx)
	panel.mostrar("@@ -1 +1 @@\n-a\n+b", "x.txt")
	assert panel.lista.GetColumnCount() == 2


def test_editor_no_pierde_el_texto_si_falla(app_wx):
	from app.ui.editor import DialogoEditor

	ctx, _api, _a = crear_contexto()
	errores = []

	def enviar(valores):
		raise RuntimeError("fallo de red")

	import app.ui.editor as editor

	original = editor.mostrar_error
	editor.mostrar_error = lambda padre, mensaje, titulo="": errores.append(mensaje)
	try:
		dialogo = DialogoEditor(None, ctx, "Comentar", enviar, con_titulo=True)
		dialogo.campo_titulo.SetValue("Título")
		dialogo.campo_cuerpo.SetValue("Texto importante")
		dialogo._al_aceptar(None)
		assert errores == ["fallo de red"]
		assert dialogo.campo_cuerpo.GetValue() == "Texto importante" and dialogo.boton_enviar.IsEnabled()
		dialogo.Destroy()
	finally:
		editor.mostrar_error = original


def test_casillas_configurables():
	from app.ui.comunes import componer_casilla

	assert componer_casilla("Etiqueta", True, 2, 10) == "Etiqueta, marcada"
	assert componer_casilla("Etiqueta", False, 2, 10, estado_primero=True, decir_posicion=True) == "no marcada, Etiqueta, 3 de 10"
	assert componer_casilla("Etiqueta", True, 0, 1, decir_estado=False) == "Etiqueta"
