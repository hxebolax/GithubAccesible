"""Bandeja configurable, teclas globales, orden de secciones, paleta de órdenes y vigilancia de Actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
import wx

from app.services import vigilancia_actions as va
from app.ui import orden_secciones as os_
from app.ui import paleta
from app.ui import teclas_globales as tg
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from tests.apoyo_app import crear_contexto

# ════════════════════════════════════════════════════════════════════════════
# Teclas globales
# ════════════════════════════════════════════════════════════════════════════


def test_analizar_y_normalizar_combinaciones():
	c = tg.analizar("Ctrl+Alt+Shift+g")
	assert c == tg.Combinacion(wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT, ord("G"))
	assert c.texto == "Control+Alt+Mayúsculas+G"
	assert tg.normalizar("control + windows + f5") == "Control+Windows+F5"
	assert tg.analizar("Win+7").tecla_virtual == ord("7")
	for malo in ("", "G", "Mayúsculas+G", "Control+Pepe", "Control+Retroceso", "Super+G", "Control+F25"):
		assert tg.analizar(malo) is None, malo


def test_combinacion_desde_una_pulsacion():
	assert tg.desde_evento(ord("N"), wx.MOD_CONTROL | wx.MOD_ALT).texto == "Control+Alt+N"
	assert tg.desde_evento(wx.WXK_F12, wx.MOD_WIN).texto == "Windows+F12"
	assert tg.desde_evento(ord("N"), wx.MOD_SHIFT) is None
	assert tg.desde_evento(wx.WXK_LEFT, wx.MOD_CONTROL) is None


class VentanaFalsa:
	"""Lo justo de wx.Window para registrar teclas sin tocar las de verdad de Windows."""

	def __init__(self, ocupadas=()):
		self.ocupadas = set(ocupadas)
		self.registradas: dict[int, tuple[int, int]] = {}
		self.manejador = None

	def Bind(self, _evento, manejador):  # noqa: N802
		self.manejador = manejador

	def RegisterHotKey(self, identificador, mods, vk):  # noqa: N802
		if (mods, vk) in self.ocupadas:
			return False
		self.registradas[identificador] = (mods, vk)
		return True

	def UnregisterHotKey(self, identificador):  # noqa: N802
		self.registradas.pop(identificador, None)


def test_gestor_registra_avisa_de_las_ocupadas_y_ejecuta():
	ctx, _api, anuncios = crear_contexto()
	config = ctx.config
	config.establecer_varias({"teclas_globales.activadas": True, "teclas_globales.buscar": "Control+Alt+B",
		"teclas_globales.abrir_notificaciones": "Control+Alt+Mayúsculas+G"})  # repite la de mostrar u ocultar
	ventana = VentanaFalsa(ocupadas={(wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT, ord("N"))})
	llamadas = []
	funciones = {clave: (lambda c=clave: llamadas.append(c)) for clave, _n in tg.ORDENES}
	gestor = tg.GestorTeclasGlobales(ventana, config, funciones, avisar=anuncios.append)
	fallidas = gestor.registrar()
	assert sorted(gestor.registradas.values()) == ["buscar", "mostrar_ocultar"]
	assert {c for c, _t in fallidas} == {"decir_notificaciones", "abrir_notificaciones"}
	assert "otro programa" in anuncios[-1]
	identificador = next(i for i, c in gestor.registradas.items() if c == "buscar")
	ventana.manejador(SimpleNamespace(GetId=lambda: identificador, Skip=lambda: None))
	assert llamadas == ["buscar"]
	config.establecer("teclas_globales.activadas", False)
	assert gestor.registrar() == [] and not ventana.registradas


# ════════════════════════════════════════════════════════════════════════════
# Orden de las secciones
# ════════════════════════════════════════════════════════════════════════════


def test_ordenar_secciones():
	fabrica = ["a", "b", "c", "d"]
	assert os_.ordenar(fabrica) == fabrica
	assert os_.ordenar(fabrica, ["c", "a", "x"], ["b"]) == ["c", "a", "d"], "las nuevas (d) van al final; las que no existen, fuera"
	assert os_.ordenar(fabrica, [], ["a", "b"], obligatorias=["a"]) == ["a", "c", "d"]
	assert os_.ordenar(fabrica, [], fabrica) == ["a"], "nunca se quedan todas ocultas"
	assert os_.orden_completo(fabrica, ["d", "b"]) == ["d", "b", "a", "c"]


def test_ventana_principal_con_secciones_ocultas_y_reordenadas(app_wx):
	from app.ui.ventana_principal import VentanaPrincipal

	ctx, _api, anuncios = crear_contexto()
	ventana = VentanaPrincipal(ctx)
	try:
		ctx.config.establecer_varias({"secciones.principal_orden": ["repositorios", "notificaciones"],
			"secciones.principal_ocultas": ["inicio", "codespaces", "busqueda"]})
		ventana.aplicar_secciones()
		claves = [c for c, _d in ventana.definiciones]
		assert claves[:2] == ["repositorios", "notificaciones"]
		assert "inicio" not in claves and "codespaces" not in claves and "busqueda" in claves, "la búsqueda no se oculta"
		assert ventana.secciones.GetString(0) == "Mis repositorios"
		ver = ventana.GetMenuBar().GetMenu(ventana.GetMenuBar().FindMenu("Ver"))
		primera = ver.GetMenuItems()[0].GetItemLabel()
		assert primera.startswith("&1 Mis repositorios") and primera.endswith("Alt+1")
		afirmar_teclado_correcto(ventana)
		ventana.marcar_contador_notificaciones(3)
		assert ventana.secciones.GetString(1).endswith("(3)")
		ventana.ir_a_seccion("inicio", enfocar=False)
		assert any("oculta" in texto for texto in anuncios) and ventana._clave_actual() == "repositorios"
		ctx.config.establecer("secciones.principal_ocultas", ["notificaciones"])
		ventana.aplicar_secciones()
		ventana.marcar_contador_notificaciones(2)  # oculta: no falla
	finally:
		ventana.Destroy()


def test_ventana_de_repositorio_con_secciones_reordenadas(app_wx, monkeypatch):
	from app.ui.repositorio import ventana as v

	monkeypatch.setattr(v.VentanaRepositorio, "Show", lambda self, mostrar=True: True)
	monkeypatch.setattr(v, "_VENTANAS", {})
	ctx, _api, anuncios = crear_contexto()
	ctx.config.establecer_varias({"secciones.repositorio_orden": ["actions", "acciones", "issues"],
		"secciones.repositorio_ocultas": ["webhooks", "resumen"]})
	ventana = v.abrir_ventana_repositorio(ctx, "ana/p")
	try:
		assert ventana.ids[:2] == ["acciones", "issues"] and "webhooks" not in ventana.ids and "resumen" in ventana.ids
		assert ventana.lista_secciones.GetString(0) == "Actions"
		ventana.mostrar_seccion("webhooks", enfocar=False)
		assert "oculta" in anuncios[-1] and ventana.actual == "resumen"
		ventana.cambiar_seccion(1)
		afirmar_teclado_correcto(ventana, teclas_propias=["F6"])
		etiquetas = [e for _p, _s, e in v.etiquetas_menu_ir(ventana.secciones_visibles)]
		assert etiquetas[0].startswith("&1 Actions")
	finally:
		ventana.Destroy()
		wx.Yield()


# ════════════════════════════════════════════════════════════════════════════
# Bandeja
# ════════════════════════════════════════════════════════════════════════════


def test_cerrar_deja_en_la_bandeja_y_salir_sale(app_wx, monkeypatch):
	from app.ui.ventana_principal import VentanaPrincipal

	ctx, _api, _a = crear_contexto()
	ctx.config.establecer("general.cerrar_a_bandeja", True)
	ventana = VentanaPrincipal(ctx)
	ocultada = []
	monkeypatch.setattr(ventana, "ocultar_en_bandeja", lambda: ocultada.append(1) or True)
	evento = wx.CloseEvent(wx.wxEVT_CLOSE_WINDOW)
	evento.SetCanVeto(True)
	ventana._al_cerrar(evento)
	assert ocultada and evento.GetVeto() and ventana
	ventana._forzar_salida = True
	ventana.teclas_globales.quitar()
	ventana.Destroy()


def test_texto_y_ordenes_de_la_bandeja(app_wx):
	from app.ui.ventana_principal import VentanaPrincipal

	ctx, _api, anuncios = crear_contexto()
	ventana = VentanaPrincipal(ctx)
	try:
		assert ventana.texto_bandeja() == "GitHub Accesible"
		ventana._ultimas_notificaciones = [{"repository": {"full_name": "a/b"}, "subject": {"title": "Fallo"}}]
		ventana.marcar_contador_notificaciones(1)
		assert ventana.texto_bandeja().endswith("1 notificaciones sin leer")
		assert ventana.texto_sin_leer() == "1 notificación sin leer. a/b: Fallo"
		ventana.decir_notificaciones()
		assert anuncios[-1].startswith("1 notificación sin leer")
		textos = [o[0] for o in ventana.ordenes_bandeja() if o]
		assert "&Notificaciones (1 sin leer)" in textos and "&Comprobar notificaciones ahora" in textos
	finally:
		ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Paleta de órdenes
# ════════════════════════════════════════════════════════════════════════════


def test_limpiar_y_filtrar_ordenes():
	assert paleta.limpiar_etiqueta("&Actualizar\tF5") == ("Actualizar", "F5")
	assert paleta.limpiar_etiqueta("A&brir (Intro)") == ("Abrir", "Intro")
	assert paleta.limpiar_etiqueta("Bifurcar (for&k)") == ("Bifurcar (fork)", "")
	assert paleta.limpiar_etiqueta("Pull && push") == ("Pull & push", "")
	ordenes = [paleta.Orden("Hacer rama por defecto", "Acciones", "", lambda: None),
		paleta.Orden("Clonar…", "Archivo", "Ctrl+Shift+K", lambda: None)]
	assert [o.etiqueta for o in paleta.filtrar(ordenes, "defécto RAMA")] == ["Hacer rama por defecto"]
	assert [o.etiqueta for o in paleta.filtrar(ordenes, "shift+k")] == ["Clonar…"]
	assert len(paleta.filtrar(ordenes, "  ")) == 2


def test_paleta_recoge_menus_y_acciones_y_ejecuta(app_wx):
	from app.ui.ventana_principal import VentanaPrincipal

	ctx, _api, _a = crear_contexto()
	ventana = VentanaPrincipal(ctx)
	try:
		ventana.ir_a_seccion("locales", enfocar=False)
		ordenes = paleta.recoger(ventana)
		etiquetas = {o.etiqueta for o in ordenes}
		assert {"Preferencias…", "Paleta de órdenes…", "Añadir una carpeta…"} <= etiquetas
		assert all(o.ruta != "Acciones" or o.etiqueta for o in ordenes)
		# Ejecutar una orden de menú lanza su evento como si se eligiera en el menú.
		marco = wx.Frame(ventana)
		barra, menu, llamadas = wx.MenuBar(), wx.Menu(), []
		elemento = menu.Append(wx.ID_ANY, "&Probar\tCtrl+Shift+J")
		marco.Bind(wx.EVT_MENU, lambda _e: llamadas.append(1), elemento)
		barra.Append(menu, "&Pruebas")
		marco.SetMenuBar(barra)
		orden = next(o for o in paleta.recoger(marco) if o.etiqueta == "Probar")
		assert (orden.ruta, orden.atajo) == ("Pruebas", "Ctrl+Shift+J")
		orden.ejecutar()
		assert llamadas == [1]
		dialogo = paleta.DialogoPaleta(ventana, ordenes)
		try:
			dialogo.filtrar("preferen")
			assert dialogo.lista.GetCount() == 1
			afirmar_teclado_correcto(dialogo)
		finally:
			dialogo.Destroy()
	finally:
		ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Vigilancia de Actions
# ════════════════════════════════════════════════════════════════════════════


class ApiFalsa:
	def __init__(self):
		self.runs: dict[int, dict] = {}
		self.lista: list[dict] = []

	def ejecucion(self, repo, identificador):
		if identificador == 404:
			raise type("NoEncontrado", (Exception,), {"codigo_http": 404})()
		return self.runs[identificador]

	def ejecuciones(self, repo, numero=1, sha=""):
		return SimpleNamespace(elementos=[r for r in self.lista if not sha or r.get("head_sha") == sha])


def test_vigilar_una_ejecucion_un_commit_y_un_repositorio():
	api = ApiFalsa()
	ahora = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
	api.runs[1] = {"id": 1, "name": "CI", "status": "in_progress"}
	vigiladas = [va.nueva_ejecucion("a/b", {"id": 1, "name": "CI"}), va.nuevo_commit("a/b", "abc", ahora),
		va.nuevo_repositorio("a/b", ahora), va.nueva_ejecucion("a/b", {"id": 404})]
	avisos, siguen = va.comprobar(api, vigiladas, ahora)
	assert avisos == [] and len(siguen) == 3, "la borrada (404) se quita; las demás siguen"
	api.runs[1] = {"id": 1, "name": "CI", "status": "completed", "conclusion": "failure", "head_branch": "main"}
	api.lista = [
		{"id": 7, "name": "Pruebas", "status": "completed", "conclusion": "success", "head_sha": "abc",
			"updated_at": "2026-11-22T12:05:00Z"},
		{"id": 8, "name": "Vieja", "status": "completed", "conclusion": "success", "head_sha": "zzz",
			"updated_at": "2026-11-22T11:00:00Z"},
	]
	avisos, siguen = va.comprobar(api, siguen, ahora + timedelta(minutes=6))
	textos = [a.texto for a in avisos]
	assert textos[0] == "Actions de a/b: «CI» en main ha terminado: fallida."
	assert textos.count("Actions de a/b: «Pruebas» ha terminado: correcta.") == 2, "por el commit y por el repositorio"
	assert all("Vieja" not in t for t in textos), "lo terminado antes de empezar a vigilar no se avisa"
	assert [v["tipo"] for v in siguen] == ["repositorio"]
	avisos, _siguen = va.comprobar(api, siguen, ahora + timedelta(minutes=7))
	assert avisos == [], "no se repiten avisos"


def test_commit_sin_ejecuciones_se_deja_de_esperar():
	api = ApiFalsa()
	ahora = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
	_avisos, siguen = va.comprobar(api, [va.nuevo_commit("a/b", "abc", ahora)], ahora + timedelta(minutes=3))
	assert siguen
	_avisos, siguen = va.comprobar(api, siguen, ahora + timedelta(minutes=va.ESPERA_COMMIT_MIN + 1))
	assert siguen == []


def test_ventana_principal_vigila_y_avisa(app_wx):
	from app.ui.ventana_principal import VentanaPrincipal

	ctx, api, anuncios = crear_contexto()
	ventana = VentanaPrincipal(ctx)
	try:
		elemento = va.nueva_ejecucion("a/b", {"id": 5, "name": "CI"})
		ventana.vigilar(elemento)
		assert ventana.esta_vigilado(elemento) and ventana._temporizador_actions.IsRunning()
		assert "Vigilando" in anuncios[-1]
		ventana.vigilar(elemento)
		assert "Ya se está vigilando" in anuncios[-1] and len(ventana.vigiladas) == 1
		api.ejecucion.return_value = {"id": 5, "name": "CI", "status": "completed", "conclusion": "success"}
		ventana.comprobar_vigiladas()
		assert anuncios[-1] == "Actions de a/b: «CI» ha terminado: correcta."
		assert "accion_exito" in ctx.sonidos.eventos and ventana.vigiladas == []
		assert not ventana._temporizador_actions.IsRunning()
	finally:
		ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Preferencias
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def preferencias(app_wx):
	from app.ui.preferencias import DialogoPreferenciasGitHub

	ctx, _api, anuncios = crear_contexto()
	dialogo = DialogoPreferenciasGitHub(None, ctx, [])
	yield dialogo, ctx, anuncios
	dialogo.Destroy()


def test_campo_de_tecla_recoge_la_combinacion(preferencias):
	dialogo, ctx, anuncios = preferencias
	campo = dialogo.control_de("teclas_globales.buscar")
	assert dialogo.capturar_tecla(campo, ord("B"), wx.MOD_CONTROL | wx.MOD_ALT) is True
	assert campo.GetValue() == "Control+Alt+B" and anuncios[-1] == "Control+Alt+B"
	assert dialogo.capturar_tecla(campo, ord("B"), wx.MOD_SHIFT) is True and "no vale" in anuncios[-1]
	assert campo.GetValue() == "Control+Alt+B"
	assert dialogo.capturar_tecla(campo, wx.WXK_TAB, wx.MOD_NONE) is False, "Tabulador sigue moviendo el foco"
	assert dialogo.capturar_tecla(campo, wx.WXK_BACK, wx.MOD_NONE) is True and campo.GetValue() == ""
	dialogo.capturar_tecla(campo, ord("G"), wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT)
	assert dialogo.teclas_repetidas() == ["teclas_globales.buscar"]
	with mock.patch("app.ui.dialogo_preferencias.mostrar_aviso") as aviso:
		assert dialogo.aplicar() is False
	assert "ya la tiene otra" in aviso.call_args.args[1]
	dialogo.capturar_tecla(campo, wx.WXK_F9, wx.MOD_WIN)
	assert dialogo.aplicar() and ctx.config.obtener("teclas_globales.buscar") == "Windows+F9"


def test_pagina_de_secciones(preferencias):
	dialogo, ctx, _a = preferencias
	titulos = [dialogo.libro.GetPageText(i) for i in range(dialogo.libro.GetPageCount())]
	assert {"Teclas globales", "Actions", "Secciones"} <= set(titulos)
	dialogo.selector_ventana.SetSelection(1)
	dialogo._mostrar_secciones()
	lista = dialogo.lista_secciones_pref
	assert lista.GetString(0) == "Resumen"
	lista.SetSelection(1)  # Código
	dialogo._mover_seccion(-1)
	assert lista.GetString(0) == "Código"
	indice = [lista.GetString(i) for i in range(lista.GetCount())].index("Webhooks")
	wx.CheckListBox.Check(lista, indice, False)
	evento = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, lista.GetId())
	evento.SetInt(indice)
	dialogo._al_marcar_seccion(evento)
	assert dialogo.aplicar()
	assert ctx.config.obtener("secciones.repositorio_orden")[:2] == ["codigo", "resumen"]
	assert ctx.config.obtener("secciones.repositorio_ocultas") == ["webhooks"]
	for indice in range(dialogo.libro.GetPageCount()):
		dialogo.libro.SetSelection(indice)
		afirmar_teclado_correcto(dialogo.libro.GetPage(indice))
