"""Pruebas de la ventana principal, el inicio de sesión, las cuentas, la búsqueda y las preferencias."""

from __future__ import annotations

import wx

from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto


def _ventana(ctx):
	from app.ui.ventana_principal import VentanaPrincipal

	return VentanaPrincipal(ctx)


def test_ventana_se_construye_con_teclado_correcto(app_wx):
	ctx, api, _a = crear_contexto()
	ventana = _ventana(ctx)
	try:
		afirmar_teclado_correcto(ventana)
		etiquetas = [ventana.GetMenuBar().GetMenuLabelText(i) for i in range(ventana.GetMenuBar().GetMenuCount())]
		assert etiquetas == ["Archivo", "Ver", "Acciones", "Ir", "Herramientas", "Ayuda"]
		assert ventana._clave_actual() == "notificaciones"
		assert api.notificaciones.called, "la sección inicial se carga sola"
	finally:
		ventana.Destroy()


def test_cafe_justo_encima_de_acerca_de(app_wx):
	ctx, _api, _a = crear_contexto()
	ventana = _ventana(ctx)
	try:
		elementos = [e for e in ventana.menu_ayuda.GetMenuItems() if not e.IsSeparator()]
		textos = [e.GetItemLabelText() for e in elementos]
		assert textos[-1].startswith("Acerca de")
		assert textos[-2] == "Invítame a un café si te gusta mi trabajo"
	finally:
		ventana.Destroy()


def test_menu_acciones_cambia_con_la_seccion(app_wx):
	ctx, _api, _a = crear_contexto()
	ventana = _ventana(ctx)
	try:
		ventana.ir_a_seccion("locales", enfocar=False)
		ventana._rehacer_menu_acciones()
		textos = [e.GetItemLabelText() for e in ventana.menu_acciones.GetMenuItems() if not e.IsSeparator()]
		assert any("Añadir una carpeta" in t for t in textos)
		assert all("\t" not in e.GetItemLabel() for e in ventana.menu_acciones.GetMenuItems())
	finally:
		ventana.Destroy()


def test_sin_sesion_no_se_pide_nada_y_se_explica(app_wx):
	ctx, api, _a = crear_contexto(con_cuenta=False)
	ventana = _ventana(ctx)
	try:
		panel = ventana.panel_actual
		assert not api.notificaciones.called
		assert "iniciar sesión" in panel.estado.GetLabel()
		assert "sin sesión" in ventana.GetTitle()
	finally:
		ventana.Destroy()


def test_notificaciones_nuevas_se_anuncian_una_vez(app_wx):
	from app.services.github.cliente import Pagina

	ctx, api, anuncios = crear_contexto()
	notif = {"id": "1", "unread": True, "updated_at": "2026-01-01T00:00:00Z", "reason": "mention",
		"subject": {"title": "Arreglo", "type": "Issue"}, "repository": {"full_name": "a/b"}}
	api.notificaciones.return_value = Pagina([])
	ventana = _ventana(ctx)
	try:
		ventana.comprobar_notificaciones()
		api.notificaciones.return_value = Pagina([notif])
		ventana.comprobar_notificaciones()
		assert "mencion" in ctx.sonidos.eventos
		assert any("Arreglo" in a for a in anuncios)
		cantidad = len(anuncios)
		ventana.comprobar_notificaciones()
		assert len(anuncios) == cantidad, "no se repite el aviso"
		assert "(1)" in ventana.secciones.GetString(1)
	finally:
		ventana.Destroy()


def test_dialogo_de_inicio_de_sesion(app_wx):
	from app.ui.sesion import DialogoInicioSesion

	ctx, _api, _a = crear_contexto(con_cuenta=False)
	dialogo = DialogoInicioSesion(None, ctx)
	try:
		afirmar_teclado_correcto(dialogo)
		dialogo.metodo.SetSelection(1)
		dialogo._actualizar_controles()
		assert dialogo.campo_token.IsEnabled() and not dialogo.ambitos.IsEnabled()
		dialogo.metodo.SetSelection(0)
		dialogo._actualizar_controles()
		assert "identificador" in dialogo.estado.GetValue() or dialogo.ambitos.IsEnabled()
	finally:
		dialogo.Destroy()


def test_inicio_con_token_valida_y_guarda_la_cuenta(app_wx, monkeypatch):
	from app.services.github import autenticacion as auth
	from app.ui import sesion

	ctx, _api, _a = crear_contexto(con_cuenta=False)
	monkeypatch.setattr(auth, "validar_token", lambda token, host, metodo: auth.Cuenta("luis", host, metodo=metodo))
	dialogo = sesion.DialogoInicioSesion(None, ctx)
	try:
		dialogo.metodo.SetSelection(1)
		dialogo._actualizar_controles()
		dialogo.campo_token.SetValue("ghp_x123456")
		dialogo._al_iniciar(None)
		assert dialogo.cuenta.usuario == "luis"
		assert ctx.cuentas.token(dialogo.cuenta) == "ghp_x123456"
	finally:
		dialogo.Destroy()


def test_dialogo_de_cuentas(app_wx):
	from app.ui.sesion import DialogoCuentas

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoCuentas(None, ctx)
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.lista.numero_filas() == 1 and dialogo.lista.texto_celda(0, 3) == "Sí"
	finally:
		dialogo.Destroy()


def test_dialogo_de_busqueda(app_wx):
	from app.ui.busqueda import DialogoBusqueda

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoBusqueda(None, ctx)
	try:
		afirmar_teclado_correcto(dialogo)
		dialogo.consulta.SetValue("language:python accesible")
		dialogo.tipo.SetSelection(0)
		assert dialogo.valores()["tipo"] == "repositories"
	finally:
		dialogo.Destroy()


def test_preferencias_teclado_y_guardado(app_wx):
	from app.ui.preferencias import DialogoPreferenciasGitHub
	from app.ui.vistas import principales

	ctx, _api, _a = crear_contexto()
	vistas = [f() for _c, f in principales.SECCIONES]
	dialogo = DialogoPreferenciasGitHub(None, ctx, vistas)
	try:
		afirmar_teclado_correcto(dialogo)
		titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
		assert "Sonidos" in titulos and "Columnas de las listas" in titulos and "Actualizaciones" in titulos
		indice = list(dialogo._eventos).index("error")
		wx.CheckListBox.Check(dialogo.lista_eventos, indice, False)
		dialogo.selector_vista.SetSelection([v.id for v in vistas].index("repositorios"))
		dialogo._mostrar_columnas()
		dialogo.lista_columnas.SetSelection(1)
		dialogo._mover(-1)
		assert dialogo.aplicar()
		assert ctx.config.obtener("sonidos.desactivados") == ["error"]
		assert ctx.config.obtener("listas.columnas")["repositorios"][0] == "descripcion"
	finally:
		dialogo.Destroy()


def test_origen_de_actualizaciones():
	from app.services import actualizador

	assert actualizador.urls_de_origen("servidor") == [actualizador.URL_MANIFIESTO]
	assert actualizador.urls_de_origen("github") == [actualizador.URL_MANIFIESTO_GITHUB]
	assert actualizador.urls_de_origen("ambos") == [actualizador.URL_MANIFIESTO, actualizador.URL_MANIFIESTO_GITHUB]
	assert actualizador.urls_de_origen("personalizada", "https://x.es/v.json") == ["https://x.es/v.json"]
	assert actualizador.urls_de_origen("personalizada", "") == [actualizador.URL_MANIFIESTO, actualizador.URL_MANIFIESTO_GITHUB]


def test_borradores_se_guardan_y_se_recuperan(tmp_path):
	from app.services.borradores import Almacen

	almacen = Almacen(tmp_path / "app.db")
	try:
		almacen.guardar_borrador("comentario:a/b#1", "", "Texto a medias")
		assert almacen.borrador("comentario:a/b#1")[1] == "Texto a medias"
		almacen.guardar_borrador("comentario:a/b#1", "", "   ")
		assert almacen.borrador("comentario:a/b#1") is None, "vacío = sin borrador"
		almacen.marcar_avisadas("github.com:ana", [("1", "f1"), ("2", "f2")])
		assert almacen.avisadas("github.com:ana") == {"1": "f1", "2": "f2"}
	finally:
		almacen.cerrar()


def test_busqueda_guiada_como_el_buscador_html():
	from app.ui.busqueda import construir_consulta

	assert construir_consulta("", "repositories", "populares", "500", "python", "mit") == "stars:>500 license:mit language:python"
	assert construir_consulta("lector", "repositories", "lector") == "lector topic:screen-reader"
	assert construir_consulta("x", "repositories", "populares", "") == "x", "sin valor no se añade el calificador"
	assert construir_consulta("bug", "issues", "populares", "5", "rust", "mit") == "bug language:rust", "categoría y licencia solo en repositorios"
