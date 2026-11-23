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


def _definicion_orden(elementos):
	from app.services import formato as f

	return DefinicionVista(
		"orden", "Orden",
		[
			Columna("titulo", "Título", lambda e, c: e["titulo"]),
			Columna("fecha", "Fecha", lambda e, c: f.fecha(e.get("fecha"), True)),
			Columna("estrellas", "Estrellas", lambda e, c: f.numero(e.get("estrellas"))),
		],
		lambda api, n, p: list(elementos),
	)


def _titulos(panel):
	return [panel.lista.texto_celda(i, 0) for i in range(panel.lista.numero_filas())]


ELEMENTOS_ORDEN = [
	{"titulo": "Issue 10", "fecha": "2026-11-20T10:00:00Z", "estrellas": 1500},
	{"titulo": "issue 2", "fecha": "2026-11-22T09:00:00Z", "estrellas": 999},
	{"titulo": "Sin fecha", "fecha": None, "estrellas": None},
	{"titulo": "Issue 1", "fecha": "2025-01-01T00:00:00Z", "estrellas": 20},
]


def test_ordenar_por_columnas_con_valores_reales(app_wx, marco):
	"""Ordena por el valor (no por «hace 3 días» ni «1.500»), con orden natural y los vacíos al final."""
	ctx, _api, anuncios = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion_orden(ELEMENTOS_ORDEN))
	panel.cargar()
	assert _titulos(panel) == ["Issue 10", "issue 2", "Sin fecha", "Issue 1"], "sin orden, el de GitHub"
	panel.ordenar_por("titulo")
	assert _titulos(panel) == ["Issue 1", "issue 2", "Issue 10", "Sin fecha"]
	assert anuncios[-1] == "Ordenada por Título, ascendente."
	panel.ordenar_por("fecha", descendente=True)
	assert _titulos(panel) == ["issue 2", "Issue 10", "Issue 1", "Sin fecha"], "la más reciente primero; sin fecha, al final"
	panel.ordenar_por("estrellas")
	assert _titulos(panel) == ["Issue 1", "issue 2", "Issue 10", "Sin fecha"], "999 antes que 1.500"
	assert "ordenada por Estrellas, ascendente" in panel.estado.GetLabel()
	panel.ordenar_por(None)
	assert _titulos(panel) == ["Issue 10", "issue 2", "Sin fecha", "Issue 1"]


def test_ordenar_conserva_el_elemento_y_se_recuerda(app_wx, marco):
	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion_orden(ELEMENTOS_ORDEN))
	panel.cargar()
	panel.lista.enfocar_fila(3, anunciar=False)
	panel.ordenar_por("titulo")
	assert panel.elemento["titulo"] == "Issue 1" and panel.lista.fila_actual() == 0, "el foco sigue al elemento"
	assert ctx.config.obtener("listas.orden") == {"orden": ["titulo", False]}
	otro = PanelLista(marco, ctx, _definicion_orden(ELEMENTOS_ORDEN))
	otro.cargar()
	assert _titulos(otro) == ["Issue 1", "issue 2", "Issue 10", "Sin fecha"], "una lista nueva usa el orden guardado"


def test_control_j_y_cabecera_alternan_el_orden(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion_orden(ELEMENTOS_ORDEN))
	panel.cargar()
	evento = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
	evento.SetKeyCode(ord("J"))
	evento.SetControlDown(True)
	for esperado in ("Ordenada por Título, ascendente.", "Ordenada por Título, descendente.", "Orden original, el que da GitHub."):
		panel.lista.GetEventHandler().ProcessEvent(evento)
		assert anuncios[-1] == esperado
	cabecera = wx.ListEvent(wx.wxEVT_LIST_COL_CLICK, panel.lista.GetId())
	cabecera.SetColumn(2)
	panel._al_pulsar_cabecera(cabecera)
	assert panel.orden == ("estrellas", False)
	etiquetas = [a.etiqueta for a in panel.acciones_disponibles()]
	assert "Ordenar por columna &y sentido…" in etiquetas


def test_ordenar_mantiene_el_orden_al_cargar_mas(app_wx, marco):
	ctx, _api, _a = crear_contexto()
	paginas = {1: Pagina([{"titulo": "b"}, {"titulo": "d"}], siguiente="x"), 2: Pagina([{"titulo": "a"}, {"titulo": "c"}])}
	definicion = _definicion_orden([])
	definicion.cargar = lambda api, n, p: paginas[n]
	panel = PanelLista(marco, ctx, definicion)
	panel.cargar()
	panel.ordenar_por("titulo", descendente=True)
	panel.cargar_mas()
	assert _titulos(panel) == ["d", "c", "b", "a"]


def test_elegir_el_orden_en_un_dialogo(app_wx, marco, dialogo_modal):
	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, _definicion_orden(ELEMENTOS_ORDEN))
	panel.cargar()

	def elegir(dialogo):
		# 0 original, 1 título asc, 2 título desc, 3 fecha asc...
		dialogo.lista.SetSelection(4)
		return wx.ID_OK

	dialogo_modal.responder(elegir)
	panel.pedir_orden()
	assert panel.orden == ("fecha", True)


def test_marcar_todas_las_notificaciones_tiene_atajo():
	"""Incidencia 3: «Marcar todas como leídas» con Control+Mayúsculas+A, sin elegir ninguna."""
	from app.ui.vistas import principales

	accion = next(a for a in principales.vista_notificaciones().acciones if "todas como leídas" in a.etiqueta)
	assert accion.atajo == "Ctrl+Shift+A" and not accion.requiere_elemento
