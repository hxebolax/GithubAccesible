"""Secciones que se actualizan solas (incidencia #14): recarga silenciosa, cuándo toca y Preferencias."""

from __future__ import annotations

from unittest import mock

import wx

from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from app.ui.vistas.base import Columna, DefinicionVista, PanelLista
from tests.apoyo_app import crear_contexto


def _panel(marco, ctx, datos: dict):
	definicion = DefinicionVista("prueba", "Prueba", [Columna("nombre", "Nombre", lambda e, c: e["nombre"])],
		lambda api, n, p: list(datos["lista"]), paginada=False, requiere_sesion=False)
	panel = PanelLista(marco, ctx, definicion)
	panel.cargar()
	return panel


def _filas(panel) -> list[str]:
	return [panel.lista.texto_celda(i, 0) for i in range(panel.lista.numero_filas())]


def test_recarga_silenciosa_sigue_en_el_mismo_elemento_y_avisa_de_los_nuevos(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()
	datos = {"lista": [{"id": 1, "nombre": "uno"}, {"id": 2, "nombre": "dos"}, {"id": 3, "nombre": "tres"}]}
	panel = _panel(marco, ctx, datos)
	panel.lista.enfocar_fila(1, anunciar=False)
	anuncios.clear()
	ctx.sonidos.eventos.clear()

	datos["lista"] = [{"id": 9, "nombre": "nuevo"}, {"id": 8, "nombre": "otro"}] + datos["lista"]
	assert panel.actualizar_en_silencio()
	assert _filas(panel) == ["nuevo", "otro", "uno", "dos", "tres"]
	assert panel.lista.fila_actual() == 3, "el foco sigue en «dos» aunque hayan llegado dos encima"
	assert anuncios == ["2 elementos nuevos en Prueba."] and ctx.sonidos.eventos == ["pagina"]
	assert "listo" not in ctx.sonidos.eventos


def test_sin_cambios_no_se_repinta_ni_se_dice_nada(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()
	datos = {"lista": [{"id": 1, "nombre": "uno"}]}
	panel = _panel(marco, ctx, datos)
	anuncios.clear()
	with mock.patch.object(panel.lista, "reemplazar_filas") as repintar:
		assert panel.actualizar_en_silencio()
	repintar.assert_not_called()
	assert anuncios == []
	ctx.config.establecer("listas.anunciar_nuevos", False)
	datos["lista"] = [{"id": 2, "nombre": "dos"}, {"id": 1, "nombre": "uno"}]
	panel.actualizar_en_silencio()
	assert _filas(panel) == ["dos", "uno"] and anuncios == [], "se puede pedir que cambie en silencio"


def test_un_fallo_de_la_actualizacion_automatica_no_interrumpe(app_wx, marco):
	ctx, _api, anuncios = crear_contexto()
	datos = {"lista": [{"id": 1, "nombre": "uno"}]}
	panel = _panel(marco, ctx, datos)
	anuncios.clear()
	ctx.sonidos.eventos.clear()
	datos["lista"] = None

	def falla():
		raise RuntimeError("sin conexión")

	panel.definicion.cargar = lambda api, n, p: falla()
	assert panel.actualizar_en_silencio()
	assert anuncios == [] and ctx.sonidos.eventos == []
	assert _filas(panel) == ["uno"] and not panel.cargando, "se queda lo que había"


def test_no_se_actualiza_si_se_cargaron_mas_paginas_o_nunca_se_cargo(app_wx, marco):
	ctx, _api, _a = crear_contexto()
	panel = _panel(marco, ctx, {"lista": [{"id": 1, "nombre": "uno"}]})
	panel.pagina = 2
	assert not panel.actualizar_en_silencio(), "recargar la primera página quitaría lo que se está leyendo"
	panel.pagina = 1
	panel.cargado = False
	assert not panel.actualizar_en_silencio()


def _ventana(ctx):
	from app.ui.ventana_principal import VentanaPrincipal

	return VentanaPrincipal(ctx)


def test_la_ventana_actualiza_la_seccion_a_la_vista_cuando_toca(app_wx):
	ctx, _api, _a = crear_contexto()
	ventana = _ventana(ctx)
	# Sin mostrarla de verdad (con un lector de pantalla abierto, enseñar ventanas en las pruebas da guerra):
	# lo que importa es que la aplicación crea que está a la vista o en la bandeja.
	a_la_vista = {"valor": True}
	ventana.IsShown = lambda: a_la_vista["valor"]
	try:
		panel = ventana.ir_a_seccion("estrellas", enfocar=False)
		assert panel.cargado
		with mock.patch.object(PanelLista, "actualizar_en_silencio", return_value=True) as actualizar:
			assert not ventana.actualizar_seccion_sola(), "recién cargada: aún no toca"
			panel.ultima_carga -= 6 * 60
			assert ventana.actualizar_seccion_sola()
			assert actualizar.call_count == 1

			ctx.config.establecer("listas.actualizar_secciones", ["inicio"])
			assert not ventana.actualizar_seccion_sola(), "solo las secciones marcadas"
			ctx.config.establecer("listas.actualizar_secciones", ["estrellas"])
			ctx.config.establecer("listas.actualizar_sola", False)
			assert not ventana.actualizar_seccion_sola()
			ctx.config.establecer("listas.actualizar_sola", True)
			a_la_vista["valor"] = False
			assert not ventana.actualizar_seccion_sola(), "oculta en la bandeja no gasta peticiones"
			a_la_vista["valor"] = True

			# Al volver a una sección con datos viejos se pone al día sola.
			ventana.ir_a_seccion("repositorios", enfocar=False)
			actualizar.reset_mock()
			ventana.ir_a_seccion("estrellas", enfocar=False)
			assert actualizar.call_count == 1
			ctx.config.establecer("listas.actualizar_al_volver", False)
			ventana.ir_a_seccion("repositorios", enfocar=False)
			ventana.ir_a_seccion("estrellas", enfocar=False)
			assert actualizar.call_count == 1

		ctx.config.establecer("listas.actualizar_secciones", ["notificaciones"])
		ventana.ir_a_seccion("notificaciones", enfocar=False)
		ventana.panel_actual.ultima_carga -= 3600
		assert not ventana.actualizar_seccion_sola(), "Notificaciones ya tiene su propia comprobación"
		ventana.programar_actualizacion_listas()  # al arrancar se programa con CallAfter
		assert ventana._temporizador_listas.IsRunning()
		ctx.config.establecer("listas.actualizar_sola", False)
		ventana.programar_actualizacion_listas()
		assert not ventana._temporizador_listas.IsRunning()
		ctx.config.establecer("listas.actualizar_sola", True)
		ventana.programar_actualizacion_listas()
		temporizador = ventana._temporizador_listas
		assert temporizador.IsRunning()
	finally:
		ventana.Destroy()
	assert not temporizador.IsRunning(), "al destruir la ventana se para su temporizador"


def test_preferencias_de_la_actualizacion(app_wx):
	from app.ui.preferencias import TITULO_LISTAS, DialogoPreferenciasGitHub

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoPreferenciasGitHub(None, ctx, [])
	try:
		titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
		indice = titulos.index(TITULO_LISTAS)
		dialogo.libro.SetSelection(indice)
		afirmar_teclado_correcto(dialogo.libro.GetPage(indice))
		claves = [c for c, _t in dialogo._secciones_auto]
		assert "notificaciones" not in claves and "busqueda" not in claves and "inicio" in claves
		marcadas = [c for i, c in enumerate(claves) if dialogo.lista_actualizar.IsChecked(i)]
		assert marcadas == ["inicio", "estrellas", "vigilados"]
		wx.CheckListBox.Check(dialogo.lista_actualizar, claves.index("issues"), True)
		wx.CheckListBox.Check(dialogo.lista_actualizar, claves.index("inicio"), False)
		dialogo.control_de("listas.actualizar_cada_min").SetValue(10)
		assert dialogo.aplicar()
		assert ctx.config.obtener("listas.actualizar_secciones") == ["estrellas", "issues", "vigilados"]
		assert ctx.config.obtener("listas.actualizar_cada_min") == 10
		dialogo.restablecer_controles()
		assert [c for i, c in enumerate(claves) if dialogo.lista_actualizar.IsChecked(i)] == ["inicio", "estrellas", "vigilados"]
	finally:
		dialogo.Destroy()
