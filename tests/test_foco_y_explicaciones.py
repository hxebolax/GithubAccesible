"""Regla del foco (solo lo mueve la persona) y explicaciones que oye el lector de pantalla."""

from __future__ import annotations

import sys

import pytest
import wx

from app.ui.accesibilidad.ayuda import ProveedorAyuda, ayuda_efectiva, texto_ayuda
from app.ui.accesibilidad.casillas import CheckListBoxAccesible
from tests.apoyo_app import crear_contexto
from tests.ayudas_wx import procesar_eventos, propiedades_msaa


class ConfigFalsa:
	def __init__(self, **valores):
		self.valores = {f"accesibilidad.{clave}": valor for clave, valor in valores.items()}

	def obtener(self, clave, defecto=None):
		return self.valores.get(clave, defecto)


@pytest.fixture
def proveedor(app_wx):
	"""Instala un ``ProveedorAyuda`` solo durante la prueba (y deja el de siempre después)."""
	nuevo = ProveedorAyuda(ConfigFalsa())
	anterior = wx.HelpProvider.Set(nuevo)
	yield nuevo
	wx.HelpProvider.Set(anterior or wx.SimpleHelpProvider())


def test_proveedor_filtra_lo_que_oye_el_lector_pero_no_control_h(proveedor, panel):
	casillas = CheckListBoxAccesible(panel, "lista", ["uno", "dos"])
	casillas.SetHelpText("Explicación de la lista")
	boton = wx.Button(panel, label="Botón")
	boton.SetHelpText("Explicación del botón")
	# Por defecto: la lista de casillas no repite la explicación; el botón sí la da.
	assert casillas.GetHelpText() == "" and boton.GetHelpText() == "Explicación del botón"
	assert texto_ayuda(casillas) == "Explicación de la lista", "Control+H la dice siempre"
	assert ayuda_efectiva(casillas) == "Explicación de la lista"
	proveedor.config = ConfigFalsa(explicacion_filas=True, explicacion_controles=False)
	assert casillas.GetHelpText() == "Explicación de la lista" and boton.GetHelpText() == ""
	assert texto_ayuda(boton) == "Explicación del botón"


@pytest.mark.skipif(sys.platform != "win32", reason="MSAA solo existe en Windows")
def test_el_lector_no_recibe_la_explicacion_en_cada_fila(proveedor, panel):
	casillas = CheckListBoxAccesible(panel, "lista", ["uno", "dos"])
	casillas.SetHelpText("Explicación de la lista")
	assert not propiedades_msaa(casillas, 1)["descripcion"], "la fila 1 no debe llevar la explicación"
	proveedor.config = ConfigFalsa(explicacion_filas=True)
	assert propiedades_msaa(casillas, 1)["descripcion"] == "Explicación de la lista"


def _en_primer_plano(ventana) -> bool:
	import ctypes

	return int(ctypes.windll.user32.GetForegroundWindow()) == int(ventana.GetTopLevelParent().GetHandle())


def _foco_real():
	"""El control con el foco; si la aplicación perdió el primer plano, la prueba no puede decir nada."""
	foco = wx.Window.FindFocus()
	if foco is None:
		pytest.skip("Otra aplicación tomó el primer plano durante la prueba.")
	return foco


def _enfocar(control):
	marco = control.GetTopLevelParent()
	marco.Raise()
	control.SetFocus()
	procesar_eventos()
	if not _en_primer_plano(control) or wx.Window.FindFocus() is not control:
		pytest.skip("La ventana de pruebas no está en primer plano; el foco real no se puede comprobar.")


@pytest.mark.interfaz
def test_cambiar_el_tipo_de_busqueda_no_mueve_el_foco(app_wx):
	from app.ui.busqueda import DialogoBusqueda

	ctx, _api, _a = crear_contexto()
	dialogo = DialogoBusqueda(None, ctx)
	dialogo.Show()
	try:
		_enfocar(dialogo.tipo)
		for indice in range(1, dialogo.tipo.GetCount()):
			dialogo.tipo.SetSelection(indice)
			dialogo._al_cambiar_tipo()
			procesar_eventos()
			assert _foco_real() is dialogo.tipo, f"el foco se movió al elegir {dialogo.tipo.GetString(indice)}"
		# Cargar una búsqueda del historial tampoco lo mueve.
		dialogo.cargar({"tipo": "code", "texto": "hola"})
		procesar_eventos()
		assert _foco_real() is dialogo.tipo
	finally:
		dialogo.Destroy()


@pytest.mark.interfaz
@pytest.mark.skipif(not __import__("app.services.git_local", fromlist=["x"]).git_disponible(), reason="git no está instalado")
def test_secciones_de_git_no_mueven_el_foco(app_wx, tmp_path):
	from app.services import git_local as g
	from app.ui.git.ventana_git import VentanaGit

	carpeta = tmp_path / "repo"
	g.iniciar(carpeta)
	ctx, _api, _a = crear_contexto()
	ventana = VentanaGit(ctx, str(carpeta))
	ventana.Show()
	try:
		_enfocar(ventana.secciones)
		for indice in range(1, ventana.secciones.GetCount()):
			ventana.secciones.SetSelection(indice)
			ventana.mostrar_seccion(indice)
			procesar_eventos()
			foco = _foco_real()
			assert foco is ventana.secciones, f"sección {indice}: foco en {type(foco).__name__} {foco.GetName() if foco else None}"
	finally:
		ventana.Destroy()


def test_enfocar_solo_si_se_ve(app_wx, marco):
	"""Enfocar en una ventana oculta no hace nada (con NVDA, en RichEdit, provocaba el aviso COM 0x8001010D)."""
	import wx

	from app.ui.accesibilidad.foco import enfocar

	campo = wx.TextCtrl(marco, style=wx.TE_MULTILINE | wx.TE_RICH2)
	assert not marco.IsShown()
	assert enfocar(campo) is False and wx.Window.FindFocus() is not campo
	assert enfocar(None) is False
