"""Pruebas de «Nueva issue» con plantillas y formularios, y de la plantilla de pull request (sin red).

La API es un ``MagicMock``; las tareas se ejecutan en el acto y los diálogos
modales responden con la fixture ``dialogo_modal`` (ver ``tests/test_repositorio.py``).
"""

from __future__ import annotations

import wx

from app.services import plantillas as pl
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto
from app.ui.detalle import formulario_issue as fi
from app.ui.repositorio import vistas
from app.ui.vistas.base import PanelLista
from tests.apoyo_app import crear_contexto
from tests.test_plantillas import FORMULARIO
from tests.test_repositorio import NOMBRE, REPO, api_repo

PLANTILLA_MD = "---\nname: Idea\nabout: Proponer una mejora\ntitle: '[Idea] '\nlabels: mejora\n---\n## Qué propone\n"
CONFIG = "blank_issues_enabled: false\ncontact_links:\n  - name: Foro\n    url: https://foro.example.org\n    about: Dudas\n"


def _contexto(**plantillas):
	api = api_repo()
	api.leer_plantillas_issue.return_value = (plantillas.get("archivos", []), plantillas.get("config", ""))
	api.crear_issue_con_plantilla.return_value = ({"number": 9, "title": "x"}, [])
	return crear_contexto(api)


def _panel(marco, ctx, seccion: str) -> PanelLista:
	panel = PanelLista(marco, ctx, vistas.VISTAS[seccion](NOMBRE), {"nombre": NOMBRE, "info": dict(REPO)})
	vistas.rotular(panel)
	panel.cargar()
	return panel


def _accion(panel, texto: str):
	return next(a for a in panel.acciones_disponibles() if texto in a.etiqueta.replace("&", ""))


def _mostrado(dialogo_modal) -> str:
	"""Texto del último diálogo mostrado, sin los saltos de línea que pone ``StaticText.Wrap``."""
	return " ".join(" ".join(dialogo_modal.ultimo.textos).split())


def _formulario(ctx, enviados: list | None = None) -> fi.DialogoFormularioIssue:
	plantilla = pl.leer_plantilla("fallo.yml", FORMULARIO)
	return fi.DialogoFormularioIssue(None, ctx, "Nueva issue", plantilla,
		lambda v: enviados.append(v) or {"number": 5} if enviados is not None else {"number": 5})


# ════════════════════════════════════════════════════════════════════════════
# Diálogo del formulario
# ════════════════════════════════════════════════════════════════════════════


def test_teclado_del_formulario(app_wx):
	ctx, _api, _a = _contexto()
	dialogo = _formulario(ctx)
	try:
		afirmar_teclado_correcto(dialogo, teclas_propias=["Ctrl+Intro", "F7"])
	finally:
		dialogo.Destroy()


def test_controles_del_formulario(app_wx):
	ctx, _api, _a = _contexto()
	dialogo = _formulario(ctx)
	try:
		assert dialogo.campo_titulo.GetValue() == "[Fallo]: "
		version = dialogo.controles["version"]
		hermanos = list(version.GetParent().GetChildren())
		etiqueta = hermanos[hermanos.index(version) - 1]
		assert etiqueta.GetLabel().replace("&", "") == "Versión (obligatorio):"
		assert "La que sale en Acerca de." in version.GetHelpText() and "Ejemplo: 1.0.4" in version.GetHelpText()
		assert dialogo.controles["registro"].IsMultiLine()
		assert dialogo.controles["campo_3"].GetValue() == "Al abrir…"
		sistema = dialogo.controles["sistema"]
		assert isinstance(sistema, wx.CheckListBox) and list(sistema.GetCheckedItems()) == [1]
		lector = dialogo.controles["lector"]
		assert lector.GetStrings() == ["(sin elegir)", "NVDA", "JAWS", "Narrador"] and lector.GetSelection() == 0
		normas = dialogo.controles["normas"]
		assert [c.GetLabel().replace("&", "") for c in normas] == [
			"He leído el código de conducta (obligatoria)", "Quiero ayudar a arreglarlo"]
		solo_lectura = [c for c in dialogo.panel.GetChildren() if isinstance(c, wx.TextCtrl) and not c.IsEditable()]
		assert len(solo_lectura) == 1 and solo_lectura[0].GetValue().startswith("Gracias por avisar.")
		assert not dialogo.modificado()
		dialogo.controles["version"].SetValue("2")
		assert dialogo.modificado()
	finally:
		dialogo.Destroy()


def test_obligatorios_avisan_y_llevan_el_foco(app_wx, dialogo_modal, monkeypatch):
	ctx, _api, _a = _contexto()
	enviados: list = []
	enfocados: list = []
	monkeypatch.setattr(fi.foco_ui, "enfocar", lambda control: enfocados.append(control) or True)
	dialogo = _formulario(ctx, enviados)
	try:
		dialogo.enviar()
		assert "Faltan 3 campos obligatorios" in _mostrado(dialogo_modal)
		assert enfocados == [dialogo.controles["version"]] and enviados == []

		dialogo.controles["version"].SetValue("1.0.4")
		dialogo.controles["lector"].SetSelection(1)
		dialogo.enviar()
		assert "«Normas: He leído el código de conducta»" in _mostrado(dialogo_modal)
		assert enfocados[-1] is dialogo.controles["normas"][0], "el foco va a la casilla obligatoria sin marcar"

		dialogo.controles["normas"][0].SetValue(True)
		dialogo.campo_titulo.SetValue("  ")
		dialogo.enviar()
		assert enfocados[-1] is dialogo.campo_titulo and enviados == []
	finally:
		if dialogo:
			dialogo.Destroy()


def test_enviar_compone_el_cuerpo_y_vista_previa(app_wx, monkeypatch):
	ctx, _api, _a = _contexto()
	enviados: list = []
	vistos: list = []
	from app.ui import visor_ayuda

	monkeypatch.setattr(visor_ayuda, "mostrar_documento", lambda padre, titulo, texto, **k: vistos.append((titulo, texto)))
	dialogo = _formulario(ctx, enviados)
	dialogo.campo_titulo.SetValue("[Fallo]: no abre")
	dialogo.controles["version"].SetValue("1.0.4")
	dialogo.controles["registro"].SetValue("error 5")
	dialogo.controles["lector"].SetSelection(1)
	dialogo.controles["normas"][0].SetValue(True)
	dialogo.vista_previa()
	assert vistos[0][0] == "Vista previa: [Fallo]: no abre" and "```shell\nerror 5\n```" in vistos[0][1]
	dialogo.enviar()
	assert enviados == [{"titulo": "[Fallo]: no abre", "cuerpo": vistos[0][1]}]
	assert "### Lector de pantalla\n\nNVDA" in enviados[0]["cuerpo"] and "### Sistema\n\nWindows 11" in enviados[0]["cuerpo"]
	assert "- [x] He leído el código de conducta" in enviados[0]["cuerpo"]


def test_letras_de_acceso_sin_repetir():
	ocupadas = set(fi.LETRAS_FIJAS)
	assert fi.poner_letra("Versión", ocupadas) == "V&ersión", "la V es de «Vista previa»"
	assert fi.poner_letra("Texto largo", ocupadas) == "Texto &largo", "antes el inicio de una palabra libre"
	assert fi.poner_letra("A & B", ocupadas) == "&A && B"
	assert fi.poner_letra("ttt", ocupadas) == "ttt", "sin letra libre, sin letra"


# ════════════════════════════════════════════════════════════════════════════
# Flujo «Nueva issue» desde la sección Issues
# ════════════════════════════════════════════════════════════════════════════


def test_elegir_plantilla_markdown_abre_el_editor_con_titulo_y_etiquetas(app_wx, marco, dialogo_modal):
	ctx, api, anuncios = _contexto(archivos=[("fallo.yml", FORMULARIO), ("idea.md", PLANTILLA_MD)], config=CONFIG)
	panel = _panel(marco, ctx, "issues")
	opciones: list = []

	def elegir_idea(dialogo):
		opciones.extend(dialogo.lista.GetStrings())
		dialogo.lista.SetSelection(1)
		return wx.ID_OK

	def editor(dialogo):
		assert dialogo.campo_titulo.GetValue() == "[Idea] " and dialogo.campo_cuerpo.GetValue() == "## Qué propone\n"
		dialogo.campo_titulo.SetValue("[Idea] modo oscuro")
		dialogo._al_aceptar(None)
		return wx.ID_OK

	dialogo_modal.responder(elegir_idea, editor)
	panel.ejecutar(_accion(panel, "Nueva issue"))
	assert opciones == [
		"Informe de fallo (formulario): Algo no funciona como debería.",
		"Idea: Proponer una mejora",
		"Foro (abre el navegador): Dudas",
	], "sin «Issue en blanco» porque config.yml lo desactiva"
	api.crear_issue_con_plantilla.assert_called_once_with(NOMBRE, "[Idea] modo oscuro", "## Qué propone\n", ["mejora"], [], "")
	assert "Issue #9 creada." in anuncios


def test_formulario_crea_la_issue_y_avisa_de_lo_descartado(app_wx, marco, dialogo_modal):
	ctx, api, _a = _contexto(archivos=[("fallo.yml", FORMULARIO)])
	api.crear_issue_con_plantilla.return_value = ({"number": 9}, ["etiquetas", "asignados"])
	panel = _panel(marco, ctx, "issues")
	opciones: list = []

	def elegir_formulario(dialogo):
		opciones.extend(dialogo.lista.GetStrings())
		return wx.ID_OK

	def rellenar(dialogo):
		assert isinstance(dialogo, fi.DialogoFormularioIssue)
		dialogo.campo_titulo.SetValue("[Fallo]: se cierra")
		dialogo.controles["version"].SetValue("1.0.4")
		dialogo.controles["lector"].SetSelection(2)
		dialogo.controles["normas"][0].SetValue(True)
		dialogo.enviar()
		return wx.ID_OK

	dialogo_modal.responder(elegir_formulario, rellenar)
	panel.ejecutar(_accion(panel, "Nueva issue"))
	assert opciones[-1] == "Issue en blanco: sin plantilla"
	argumentos = api.crear_issue_con_plantilla.call_args.args
	assert argumentos[:2] == (NOMBRE, "[Fallo]: se cierra") and "### Lector de pantalla\n\nJAWS" in argumentos[2]
	assert argumentos[3:] == (["fallo", "por clasificar"], ["ana"], "Bug")
	assert "las etiquetas y los asignados" in _mostrado(dialogo_modal)


def test_enlace_de_contacto_abre_el_navegador(app_wx, marco, dialogo_modal, monkeypatch):
	ctx, api, anuncios = _contexto(archivos=[("idea.md", PLANTILLA_MD)], config=CONFIG)
	abiertas: list = []
	monkeypatch.setattr(fi, "abrir_url", abiertas.append)
	panel = _panel(marco, ctx, "issues")

	def elegir_foro(dialogo):
		dialogo.lista.SetSelection(1)
		return wx.ID_OK

	dialogo_modal.responder(elegir_foro)
	panel.ejecutar(_accion(panel, "Nueva issue"))
	assert abiertas == ["https://foro.example.org"] and any("Foro" in a for a in anuncios)
	api.crear_issue_con_plantilla.assert_not_called()


def test_sin_plantillas_abre_la_issue_en_blanco(app_wx, marco, dialogo_modal):
	ctx, api, _a = _contexto()
	panel = _panel(marco, ctx, "issues")
	vistos: list = []

	def editor(dialogo):
		vistos.append(dialogo.GetTitle())
		dialogo.campo_titulo.SetValue("Algo")
		dialogo._al_aceptar(None)
		return wx.ID_OK

	dialogo_modal.responder(editor)
	panel.ejecutar(_accion(panel, "Nueva issue"))
	assert vistos == [f"Nueva issue en {NOMBRE}"]
	api.crear_issue_con_plantilla.assert_called_once_with(NOMBRE, "Algo", "")


# ════════════════════════════════════════════════════════════════════════════
# Plantilla de pull request
# ════════════════════════════════════════════════════════════════════════════


def test_nuevo_pull_request_con_varias_plantillas(app_wx, marco, dialogo_modal):
	ctx, api, _a = _contexto()
	api.plantillas_pr.return_value = [(".github/PULL_REQUEST_TEMPLATE/a.md", "Plantilla A"), ("docs/pull_request_template.md", "B")]
	panel = _panel(marco, ctx, "prs")
	cuerpos: list = []

	def elegir_b(dialogo):
		assert dialogo.lista.GetStrings()[-1] == "Sin plantilla (descripción vacía)"
		dialogo.lista.SetSelection(1)
		return wx.ID_OK

	def editor(dialogo):
		cuerpos.append(dialogo.campo_cuerpo.GetValue())
		return wx.ID_CANCEL

	dialogo_modal.responder(elegir_b, editor)
	panel.ejecutar(_accion(panel, "Nuevo pull request"))
	assert cuerpos == ["B"]

	api.plantillas_pr.return_value = [("pull_request_template.md", "Única")]
	dialogo_modal.responder(editor)
	panel.ejecutar(_accion(panel, "Nuevo pull request"))
	assert cuerpos[-1] == "Única", "con una sola plantilla no se pregunta"

	api.plantillas_pr.side_effect = RuntimeError("sin red")
	dialogo_modal.responder(editor)
	panel.ejecutar(_accion(panel, "Nuevo pull request"))
	assert cuerpos[-1] == "", "si no se pueden leer las plantillas, la descripción empieza vacía"
