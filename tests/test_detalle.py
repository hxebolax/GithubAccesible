"""Pruebas de las ventanas de detalle: conversación, issue, pull request, archivo, perfil y organización.

Sin red: la API es un ``MagicMock`` (``tests.apoyo_app.crear_contexto``) y las
tareas se ejecutan en el acto. Los diálogos modales se responden con la
fixture ``dialogo_modal``; ninguna ventana se muestra en pantalla.
"""

from __future__ import annotations

import pytest
import wx

from app.services.github.cliente import Pagina
from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado
from tests.apoyo_app import crear_contexto
from tests.test_git_y_diff import DIFF

REPO = "dueno/repo"

#: Teclas que atiende a mano la lista de la conversación.
TECLAS_CONVERSACION = ["Ctrl+N", "Ctrl+R", "F2", "Supr", "Ctrl+E", "Ctrl+C", "Ctrl+B", "Intro"]

ISSUE = {
	"number": 7, "title": "Fallo al abrir", "state": "open", "user": {"login": "berta"}, "body": "Pasos:\n1. Abrir",
	"labels": [{"name": "bug"}], "assignees": [], "comments": 2, "created_at": "2026-01-01T10:00:00Z",
	"updated_at": "2026-01-02T10:00:00Z", "html_url": "https://github.com/dueno/repo/issues/7", "node_id": "I_7",
	"reactions": {"+1": 2},
}
COMENTARIOS = [
	{"id": 101, "user": {"login": "ana"}, "body": "Lo miro yo", "created_at": "2026-01-01T11:00:00Z",
		"updated_at": "2026-01-01T11:00:00Z", "html_url": "https://github.com/dueno/repo/issues/7#issuecomment-101"},
	{"id": 102, "user": {"login": "berta"}, "body": "Gracias", "created_at": "2026-01-01T12:00:00Z",
		"updated_at": "2026-01-01T12:00:00Z", "html_url": "https://github.com/dueno/repo/issues/7#issuecomment-102"},
]
CRONOLOGIA = [
	{"event": "labeled", "actor": {"login": "ana"}, "label": {"name": "bug"}, "created_at": "2026-01-01T10:30:00Z"},
	{"event": "commented", "id": 101, "user": {"login": "ana"}, "body": "Lo miro yo", "created_at": "2026-01-01T11:00:00Z"},
	{"event": "subscribed", "actor": {"login": "ana"}, "created_at": "2026-01-01T11:30:00Z"},
	{"event": "cross-referenced", "actor": {"login": "carla"}, "created_at": "2026-01-01T13:00:00Z",
		"source": {"issue": {"number": 9, "title": "Otro fallo", "repository": {"full_name": REPO}, "html_url": "https://x/9"}}},
]
PR = {
	"number": 5, "title": "Mejora", "state": "open", "draft": False, "merged": False, "mergeable": True, "mergeable_state": "clean",
	"head": {"sha": "abc1234def", "ref": "mejora", "label": "dueno:mejora", "repo": {"full_name": REPO}},
	"base": {"ref": "main", "repo": {"full_name": REPO}}, "user": {"login": "berta"}, "node_id": "PR_5",
	"html_url": "https://github.com/dueno/repo/pull/5", "requested_reviewers": [], "labels": [], "assignees": [],
	"commits": 2, "changed_files": 2, "additions": 4, "deletions": 2,
}


@pytest.fixture(autouse=True)
def _registro_limpio():
	from app.ui.detalle.conversacion import VentanaDetalle

	VentanaDetalle._abiertas.clear()
	yield
	VentanaDetalle._abiertas.clear()


def _sin_errores(ventana, teclas=()):
	problemas = [p for p in revisar_teclado(ventana, teclas) if not p.aviso]
	assert not problemas, informe(problemas)


def _contexto_issue(issue=ISSUE):
	ctx, api, anuncios = crear_contexto()
	api.issue.return_value = dict(issue)
	api.comentarios.return_value = [dict(c) for c in COMENTARIOS]
	api.cronologia.return_value = [dict(e) for e in CRONOLOGIA]
	return ctx, api, anuncios


def _fila_de(panel, id_elemento):
	return next(i for i, e in enumerate(panel.elementos) if e.id == id_elemento and e.clase == "comentario")


def _editor_falso(monkeypatch, valores):
	"""Sustituye el editor modal: «escribe» ``valores`` y envía en el acto."""
	llamadas = []

	def editar(padre, ctx, titulo, enviar, **opciones):
		llamadas.append((titulo, opciones))
		return enviar(dict(valores))

	monkeypatch.setattr("app.ui.editor.editar", editar)
	return llamadas


# ════════════════════════════════════════════════════════════════════════════
# Conversación
# ════════════════════════════════════════════════════════════════════════════


def test_construir_elementos_ordena_y_no_repite():
	from app.ui.detalle.conversacion import construir_elementos

	elementos = construir_elementos(ISSUE, COMENTARIOS, CRONOLOGIA, "ana")
	assert [e.clase for e in elementos] == ["descripcion", "evento", "comentario", "comentario", "evento"]
	assert elementos[1].resumen == "añadió la etiqueta «bug»"
	assert "Otro fallo" in elementos[4].resumen and elementos[4].url == "https://x/9"
	assert elementos[2].propio and not elementos[3].propio and not elementos[0].propio


def test_panel_conversacion_muestra_y_actualiza_texto(app_wx, marco):
	from app.ui.detalle.conversacion import PanelConversacion

	ctx, api, _a = _contexto_issue()
	panel = PanelConversacion(marco, ctx, REPO, 7)
	hijos = list(panel.GetChildren())
	assert isinstance(hijos[hijos.index(panel.lista) - 1], wx.StaticText), "la etiqueta va justo antes de la lista"
	panel.cargar()
	assert panel.lista.numero_filas() == 5
	assert [panel.lista.GetColumn(i).GetText() for i in range(4)] == ["Autor", "Fecha", "Tipo", "Texto"]
	assert panel.lista.texto_celda(0, 2) == "Descripción"
	assert "Fallo al abrir" in panel.info.GetValue() and "Etiquetas: bug" in panel.info.GetValue()
	panel.lista.enfocar_fila(_fila_de(panel, 101), anunciar=False)
	panel.actualizar_texto()
	assert "Lo miro yo" in panel.texto.GetValue() and "ana" in panel.texto.GetValue()
	_sin_errores(panel, TECLAS_CONVERSACION)


def test_cronologia_que_falla_no_impide_ver_la_conversacion(app_wx, marco):
	from app.ui.detalle.conversacion import PanelConversacion

	ctx, api, _a = _contexto_issue()
	api.cronologia.side_effect = RuntimeError("sin permiso")
	panel = PanelConversacion(marco, ctx, REPO, 7)
	panel.cargar()
	assert panel.lista.numero_filas() == 3


def test_comentar_responder_y_borrar(app_wx, marco, dialogo_modal, monkeypatch):
	from app.ui.detalle.conversacion import PanelConversacion

	ctx, api, anuncios = _contexto_issue()
	panel = PanelConversacion(marco, ctx, REPO, 7)
	panel.cargar()
	llamadas = _editor_falso(monkeypatch, {"cuerpo": "Nuevo"})
	panel.comentar()
	api.comentar.assert_called_with(REPO, 7, "Nuevo")
	panel.lista.enfocar_fila(_fila_de(panel, 102), anunciar=False)
	panel.responder_citando()
	assert llamadas[-1][1]["cuerpo"].startswith("@berta") and "> Gracias" in llamadas[-1][1]["cuerpo"]
	# Borrar un comentario ajeno: no se permite.
	panel.borrar_mio()
	api.borrar_comentario.assert_not_called()
	assert anuncios[-1] == "Solo puede borrar sus propios comentarios."
	# Borrar uno propio, confirmando.
	panel.lista.enfocar_fila(_fila_de(panel, 101), anunciar=False)
	dialogo_modal.responder(wx.ID_YES)
	panel.borrar_mio()
	api.borrar_comentario.assert_called_once_with(REPO, 101)


def test_editar_mi_comentario_y_reaccionar(app_wx, marco, dialogo_modal, monkeypatch):
	from app.ui.detalle.conversacion import PanelConversacion

	ctx, api, _a = _contexto_issue()
	panel = PanelConversacion(marco, ctx, REPO, 7)
	panel.cargar()
	panel.lista.enfocar_fila(_fila_de(panel, 101), anunciar=False)
	_editor_falso(monkeypatch, {"cuerpo": "Lo miro mañana"})
	panel.editar_mio()
	api.editar_comentario.assert_called_once_with(REPO, 101, "Lo miro mañana")

	def elegir_corazon(dialogo):
		dialogo.lista.SetSelection(4)
		return wx.ID_OK

	dialogo_modal.responder(elegir_corazon)
	panel.reaccionar()
	api.reaccionar_comentario.assert_called_once_with(REPO, 101, "heart")
	panel.lista.enfocar_fila(0, anunciar=False)
	dialogo_modal.responder(elegir_corazon)
	panel.reaccionar()
	api.reaccionar_issue.assert_called_once_with(REPO, 7, "heart")


# ════════════════════════════════════════════════════════════════════════════
# Issue
# ════════════════════════════════════════════════════════════════════════════


def test_ventana_issue_teclado_estado_y_etiquetas(app_wx, marco, dialogo_modal):
	from app.ui.detalle.issue import VentanaIssue

	ctx, api, _a = _contexto_issue()
	ventana = VentanaIssue(None, ctx, REPO, 7)
	ventana.cargar()
	assert "Fallo al abrir" in ventana.GetTitle()
	_sin_errores(ventana, TECLAS_CONVERSACION)
	assert ventana.menu["cerrar_completada"].IsEnabled() and not ventana.menu["reabrir"].IsEnabled()
	ventana.cerrar("not_planned")
	api.cerrar_issue.assert_called_once_with(REPO, 7, "not_planned")
	api.etiquetas.return_value = [{"name": "bug"}, {"name": "docs", "description": "Documentación"}]

	def marcar_docs(dialogo):
		assert dialogo.lista.IsChecked(0) and not dialogo.lista.IsChecked(1)
		wx.CheckListBox.Check(dialogo.lista, 1, True)
		return wx.ID_OK

	dialogo_modal.responder(marcar_docs)
	ventana.etiquetas()
	api.poner_etiquetas.assert_called_once_with(REPO, 7, ["bug", "docs"])
	ventana.Destroy()


def test_issue_hito_bloqueo_y_suscripcion(app_wx, marco, dialogo_modal):
	from app.ui.detalle.issue import VentanaIssue

	ctx, api, _a = _contexto_issue()
	ventana = VentanaIssue(None, ctx, REPO, 7)
	ventana.cargar()
	api.hitos.return_value = [{"number": 3, "title": "v1.0"}]

	def elegir(indice):
		def responder(dialogo):
			dialogo.lista.SetSelection(indice)
			return wx.ID_OK
		return responder

	dialogo_modal.responder(elegir(1))
	ventana.hito()
	api.editar_issue.assert_called_with(REPO, 7, milestone=3)
	dialogo_modal.responder(elegir(3))
	ventana.bloquear()
	api.bloquear_issue.assert_called_once_with(REPO, 7, "resolved")
	dialogo_modal.responder(elegir(2))
	ventana.suscripcion()
	consulta, variables = api.c.graphql.call_args[0]
	assert "updateSubscription" in consulta and variables == {"id": "I_7", "estado": "IGNORED"}
	ventana.Destroy()


def test_abrir_issue_trae_al_frente_la_ya_abierta(app_wx, marco, monkeypatch):
	from app.ui.detalle.conversacion import VentanaDetalle
	from app.ui.detalle.issue import VentanaIssue, abrir_issue

	monkeypatch.setattr(VentanaDetalle, "mostrar", lambda self: self.ctx.sonar("abrir"))
	ctx, api, _a = _contexto_issue()
	abrir_issue(ctx, marco, REPO, 7)
	abrir_issue(ctx, marco, REPO, 7)
	ventanas = [v for v in wx.GetTopLevelWindows() if isinstance(v, VentanaIssue) and v]
	assert len(ventanas) == 1
	assert ventanas[0].GetParent() is marco
	assert ctx.sonidos.eventos.count("abrir") == 2
	assert api.issue.call_count == 1


def test_subissues_en_lista_no_modal(app_wx, marco):
	from app.ui.detalle.conversacion import DialogoLista
	from app.ui.detalle.issue import VentanaIssue

	ctx, api, _a = _contexto_issue()
	api.subissues.return_value = [{"number": 8, "title": "Parte A", "state": "open", "assignees": []}]
	ventana = VentanaIssue(None, ctx, REPO, 7)
	mostrados = []
	original = DialogoLista.mostrar
	DialogoLista.mostrar = lambda self: mostrados.append(self)
	try:
		ventana.subissues()
	finally:
		DialogoLista.mostrar = original
	dialogo = mostrados[0]
	assert dialogo.lista.numero_filas() == 1 and dialogo.lista.texto_celda(0, 1) == "Parte A"
	_sin_errores(dialogo)
	dialogo.Destroy()
	ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Pull request
# ════════════════════════════════════════════════════════════════════════════


def _contexto_pr():
	issue = dict(ISSUE, number=5, title="Mejora", pull_request={"url": "x"}, html_url=PR["html_url"])
	ctx, api, anuncios = _contexto_issue(issue)
	api.pr.return_value = dict(PR)
	api.archivos_pr.return_value = [{"filename": "app/uno.py", "status": "modified", "additions": 3, "deletions": 2},
		{"filename": "nuevo.txt", "status": "added", "additions": 1, "deletions": 0}]
	api.diff_pr.return_value = DIFF
	api.comentarios_revision.return_value = [{"path": "app/uno.py", "line": 2, "side": "RIGHT", "user": {"login": "carla"},
		"body": "¿Seguro?", "created_at": "2026-01-03T10:00:00Z"}]
	return ctx, api, anuncios


def _ventana_pr(ctx):
	from app.ui.detalle.pull_request import VentanaPullRequest

	ventana = VentanaPullRequest(None, ctx, REPO, 5)
	ventana.cargar()
	return ventana


def test_funciones_puras_del_pr():
	from app.ui.detalle.pull_request import comentarios_por_linea, explicar_fusion, remoto_coincide

	assert explicar_fusion(PR)[1] is True
	texto, posible = explicar_fusion(dict(PR, mergeable=False, mergeable_state="dirty"))
	assert not posible and "conflictos" in texto
	assert explicar_fusion(dict(PR, draft=True))[1] is False
	assert explicar_fusion(dict(PR, mergeable_state="unknown"))[1] is True
	marcas = comentarios_por_linea([{"path": "a.py", "line": 3, "side": "LEFT", "user": {"login": "x"}, "body": "hola"}],
		[{"path": "a.py", "line": 4, "side": "RIGHT", "body": "pendiente"}])
	assert list(marcas) == [("a.py", "LEFT", 3), ("a.py", "RIGHT", 4)]
	assert remoto_coincide("https://github.com/Dueno/Repo.git", REPO)
	assert remoto_coincide("git@github.com:dueno/repo.git", REPO)
	assert not remoto_coincide("https://github.com/otro/repo-x.git", REPO)


def test_ventana_pr_teclado_y_datos(app_wx, marco):
	ctx, api, _a = _contexto_pr()
	ventana = _ventana_pr(ctx)
	assert "Mejora" in ventana.GetTitle()
	assert "Ramas: dueno:mejora hacia main" in ventana.conversacion.info.GetValue()
	_sin_errores(ventana, TECLAS_CONVERSACION)
	assert ventana.libro.GetPageCount() == 5
	ventana.Destroy()


def test_pr_archivos_comentario_pendiente_y_revision(app_wx, marco, dialogo_modal, monkeypatch):
	from app.services import diferencias as d
	from app.ui.detalle.pull_request import PAGINA_ARCHIVOS

	ctx, api, anuncios = _contexto_pr()
	ventana = _ventana_pr(ctx)
	ventana._cargar_pagina(PAGINA_ARCHIVOS)
	assert ventana.lista_archivos.numero_filas() == 2
	assert ventana.diferencias.lista.GetColumnCount() == 4, "columna de comentarios"
	linea = next(x for x in ventana.diferencias.lineas if x.tipo == d.AÑADIDA and x.nueva == 2)
	assert ventana.diferencias.comentarios_de(linea)
	# Comentario añadido a la revisión pendiente; la persona sigue en la misma línea.
	indice = ventana.diferencias.lineas.index(linea)
	ventana.diferencias.lista.enfocar_fila(indice, anunciar=False)
	_editor_falso(monkeypatch, {"cuerpo": "Revisar esto", "pendiente": True})
	ventana.comentar_linea(linea)
	assert ventana.pendientes == [{"path": "app/uno.py", "line": 2, "side": "RIGHT", "body": "Revisar esto"}]
	assert ventana.diferencias.actual == indice
	assert len(ventana.diferencias.comentarios_de(ventana.diferencias.lineas[indice])) == 2
	assert "Comentarios en línea pendientes de enviar: 1" in ventana.conversacion.info.GetValue()
	api.comentar_linea.assert_not_called()
	# Comentario inmediato en una línea eliminada (lado izquierdo).
	eliminada = next(x for x in ventana.diferencias.lineas if x.tipo == d.ELIMINADA)
	_editor_falso(monkeypatch, {"cuerpo": "Ya", "pendiente": False})
	ventana.comentar_linea(eliminada)
	api.comentar_linea.assert_called_once_with(REPO, 5, "abc1234def", "app/uno.py", eliminada.antigua, "Ya", "LEFT")

	def aprobar(dialogo):
		assert "Revisar esto" in dialogo.pendientes.GetValue()
		dialogo.tipo.SetSelection(1)
		dialogo.cuerpo.SetValue("Bien hecho")
		return wx.ID_OK

	dialogo_modal.responder(aprobar)
	ventana.revisar()
	api.crear_revision.assert_called_once_with(REPO, 5, "APPROVE", "Bien hecho",
		[{"path": "app/uno.py", "line": 2, "side": "RIGHT", "body": "Revisar esto"}], "abc1234def")
	assert ventana.pendientes == []
	ventana.Destroy()


def test_pr_pedir_cambios_sin_texto_no_se_envia(app_wx, marco, dialogo_modal):
	ctx, api, _a = _contexto_pr()
	ventana = _ventana_pr(ctx)

	def pedir_cambios(dialogo):
		dialogo.tipo.SetSelection(2)
		return wx.ID_OK

	dialogo_modal.responder(pedir_cambios, wx.ID_OK)
	ventana.revisar()
	api.crear_revision.assert_not_called()
	assert dialogo_modal.ultimo.titulo == "Falta el texto"
	ventana.Destroy()


def test_pr_fusionar_y_conflictos(app_wx, marco, dialogo_modal):
	from app.ui.detalle.pull_request import DialogoFusion

	ctx, api, _a = _contexto_pr()
	ventana = _ventana_pr(ctx)
	dialogo = DialogoFusion(None, PR, True)
	_sin_errores(dialogo)
	dialogo.Destroy()

	def squash(dialogo):
		dialogo.metodo.SetSelection(1)
		dialogo.borrar_rama.SetValue(True)
		return wx.ID_OK

	dialogo_modal.responder(squash)
	ventana.fusionar()
	argumentos = api.fusionar_pr.call_args[0]
	assert argumentos[:3] == (REPO, 5, "squash") and argumentos[-1] == "abc1234def"
	api.borrar_rama.assert_called_once_with(REPO, "mejora")
	assert "fusionado" in ctx.sonidos.eventos
	# Con conflictos no se abre el diálogo: se explica por qué.
	ventana.pr = dict(PR, mergeable=False, mergeable_state="dirty")
	ventana.fusionar()
	assert dialogo_modal.ultimo.titulo == "No se puede fusionar"
	assert api.fusionar_pr.call_count == 1
	ventana.Destroy()


def test_pr_checks_abre_actions_y_vuelve_a_pedir(app_wx, marco, monkeypatch):
	from app.ui.detalle.pull_request import PAGINA_CHECKS

	ctx, api, _a = _contexto_pr()
	api.checks_de.return_value = [{"id": 11, "name": "pruebas", "status": "completed", "conclusion": "failure",
		"details_url": "https://github.com/dueno/repo/actions/runs/999/job/1", "app": {"name": "GitHub Actions"},
		"started_at": "2026-01-01T10:00:00Z", "completed_at": "2026-01-01T10:02:05Z", "output": {"title": "2 fallos"}}]
	api.estado_combinado.return_value = {"state": "failure", "statuses": [
		{"context": "ci/externo", "state": "success", "target_url": "https://ci.example/1", "description": "ok"}]}
	abiertas = []
	monkeypatch.setattr("app.ui.abrir.ejecucion", lambda ctx_, padre, nombre, id_: abiertas.append((nombre, id_)))
	ventana = _ventana_pr(ctx)
	ventana._cargar_pagina(PAGINA_CHECKS)
	assert ventana.lista_checks.numero_filas() == 2
	assert ventana.lista_checks.texto_celda(0, 3) == "2 min 5 s"
	assert "1 correctos, 1 fallidos" in ventana.resumen_checks.GetValue()
	ventana.lista_checks.enfocar_fila(0, anunciar=False)
	ventana.abrir_check()
	assert abiertas == [(REPO, 999)]
	ventana.volver_a_pedir_check()
	api.volver_a_pedir_check.assert_called_once_with(REPO, 11)
	ventana.Destroy()


def test_pr_hilos_resolver_y_responder(app_wx, marco, monkeypatch):
	from app.ui.detalle.pull_request import PAGINA_HILOS

	ctx, api, _a = _contexto_pr()
	api.hilos_revision.return_value = [{"id": "T1", "isResolved": False, "isOutdated": True, "path": "app/uno.py", "line": 2,
		"diffSide": "RIGHT", "comments": {"nodes": [{"id": "C1", "databaseId": 55, "body": "Cambia esto",
		"createdAt": "2026-01-01T10:00:00Z", "author": {"login": "berta"}}]}}]
	ventana = _ventana_pr(ctx)
	ventana._cargar_pagina(PAGINA_HILOS)
	assert ventana.lista_hilos.texto_celda(0, 2) == "Sin resolver, desactualizado"
	assert "Cambia esto" in ventana.texto_hilo.GetValue()
	ventana.resolver_hilo()
	api.resolver_hilo.assert_called_once_with("T1", True)
	_editor_falso(monkeypatch, {"cuerpo": "Hecho"})
	ventana.responder_hilo()
	api.responder_comentario_revision.assert_called_once_with(REPO, 5, 55, "Hecho")
	ventana.Destroy()


def test_pr_checkout_sin_repositorio_local_lo_explica(app_wx, marco, dialogo_modal):
	ctx, api, _a = _contexto_pr()
	ventana = _ventana_pr(ctx)
	ventana.checkout_local()
	assert dialogo_modal.ultimo.titulo == "Checkout local"
	assert any("pull/5/head:pr-5" in t for t in dialogo_modal.ultimo.textos)
	ventana.Destroy()


def test_dialogo_revision_teclado(app_wx):
	from app.ui.detalle.pull_request import DialogoRevision

	dialogo = DialogoRevision(None, [{"path": "a.py", "line": 1, "side": "RIGHT", "body": "x"}])
	try:
		_sin_errores(dialogo)
		assert dialogo.valores() == ("COMMENT", "")
	finally:
		dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Archivo
# ════════════════════════════════════════════════════════════════════════════


def _responder_texto(texto):
	def responder(dialogo):
		dialogo.campo.SetValue(texto)
		return wx.ID_OK
	return responder


def test_funciones_puras_de_archivo():
	from app.ui.detalle.archivos import buscar_en, con_numeros, es_binario, linea_de

	assert es_binario(b"\x89PNG\r\n\x1a\n\0\0") and not es_binario("añadir".encode())
	assert con_numeros("a\nb") == "1: a\n2: b"
	assert linea_de("a\nb\nc", 4) == 3
	assert buscar_en("Uno dos UNO", "uno", 1) == (8, False)
	assert buscar_en("Uno dos", "uno", 3) == (0, True)
	assert buscar_en("Uno dos uno", "uno", 8, atras=True) == (0, False)


def test_visor_de_archivo_ir_a_linea_y_buscar(app_wx, marco, dialogo_modal, monkeypatch):
	from app.ui.detalle.archivos import VentanaArchivo

	monkeypatch.setattr(VentanaArchivo, "numeros_por_defecto", False)
	ctx, api, anuncios = crear_contexto()
	api.leer_archivo.return_value = (b"uno\r\ndos\r\ntres\r\ncuatro\r\ncinco", "sha1")
	ventana = VentanaArchivo(None, ctx, REPO, "docs/LEEME.md")
	ventana.cargar()
	assert ventana.contenido.GetValue() == "uno\ndos\ntres\ncuatro\ncinco" and ventana.saltos == "\r\n"
	_sin_errores(ventana)
	dialogo_modal.responder(_responder_texto("3"))
	ventana.ir_a_linea()
	assert anuncios[-1] == "Línea 3 de 5" and ventana.linea_actual() == 3
	dialogo_modal.responder(_responder_texto("CUATRO"))
	ventana.buscar()
	assert anuncios[-1] == "Línea 4: cuatro"
	ventana.buscar_siguiente()
	assert anuncios[-1] == "Se ha vuelto al principio. Línea 4: cuatro"
	ventana.numeros.SetValue(True)
	ventana._al_cambiar_numeros()
	assert ventana.contenido.GetValue().startswith("1: uno\n2: dos")
	ventana.Destroy()


def test_archivo_binario_ofrece_descargar(app_wx, marco):
	from app.ui.detalle.archivos import VentanaArchivo

	ctx, api, _a = crear_contexto()
	api.leer_archivo.return_value = (b"\x89PNG\r\n\x1a\n\0\0datos", "s")
	ventana = VentanaArchivo(None, ctx, REPO, "img/logo.png")
	ventana.cargar()
	assert not ventana.mostrable and "binario" in ventana.contenido.GetValue() and "Descargar" in ventana.contenido.GetValue()
	assert not ventana.boton_formateado.IsShown()
	ventana.Destroy()


def test_editar_archivo_en_rama_nueva_con_pr(app_wx):
	from app.ui.detalle.archivos import DialogoEditarArchivo

	ctx, api, _a = crear_contexto()
	api.rama.return_value = {"commit": {"sha": "base1"}}
	api.guardar_archivo.return_value = {"content": {"sha": "nuevo"}}
	api.crear_pr.return_value = {"number": 12}
	dialogo = DialogoEditarArchivo(None, ctx, REPO, "docs/LEEME.md", "uno\ndos", "sha1", "main", "\r\n")
	try:
		_sin_errores(dialogo)
		dialogo.contenido.SetValue("uno\ndos\ntres")
		dialogo.mensaje.SetValue("Añadir tres")
		dialogo.crear_rama.SetValue(True)
		dialogo._sincronizar()
		dialogo.rama_nueva.SetValue("cambio")
		dialogo.abrir_pr.SetValue(True)
		dialogo._al_guardar(None)
		api.crear_rama.assert_called_once_with(REPO, "cambio", "base1")
		api.guardar_archivo.assert_called_once_with(REPO, "docs/LEEME.md", b"uno\r\ndos\r\ntres", "Añadir tres", sha="sha1", rama="cambio")
		assert api.crear_pr.call_args[0][:4] == (REPO, "Añadir tres", "cambio", "main")
		assert dialogo.resultado["pr"]["number"] == 12 and dialogo.resultado["sha"] == "nuevo"
	finally:
		dialogo.Destroy()


def test_blame_e_historial_en_listas(app_wx, marco):
	from app.ui.detalle.archivos import VentanaArchivo
	from app.ui.detalle.conversacion import DialogoLista

	ctx, api, _a = crear_contexto()
	api.leer_archivo.return_value = (b"a\nb", "s")
	api.blame.return_value = [{"startingLine": 1, "endingLine": 2, "commit": {"abbreviatedOid": "abc1234",
		"messageHeadline": "Primero", "committedDate": "2026-01-01T10:00:00Z", "author": {"name": "Ana", "user": {"login": "ana"}}}}]
	api.commits.return_value = Pagina([{"sha": "abc1234ffff", "commit": {"message": "Primero\n\nDetalle",
		"author": {"name": "Ana", "date": "2026-01-01T10:00:00Z"}}, "author": {"login": "ana"}}])
	ventana = VentanaArchivo(None, ctx, REPO, "a.txt", "main")
	ventana.cargar()
	mostrados = []
	original = DialogoLista.mostrar
	DialogoLista.mostrar = lambda self: mostrados.append(self)
	try:
		ventana.blame()
		ventana.historial()
	finally:
		DialogoLista.mostrar = original
	api.blame.assert_called_once_with(REPO, "main", "a.txt")
	assert mostrados[0].lista.valores_fila(0)[:2] == ["1-2", "ana"]
	assert mostrados[1].lista.valores_fila(0)[:2] == ["abc1234", "Primero"]
	for dialogo in mostrados:
		_sin_errores(dialogo)
		dialogo.Destroy()
	ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Perfil
# ════════════════════════════════════════════════════════════════════════════


def _contexto_usuario(login="berta"):
	ctx, api, anuncios = crear_contexto()
	api.usuario.return_value = {"login": login, "name": "Berta", "type": "User", "public_repos": 3, "followers": 1,
		"following": 2, "created_at": "2020-01-01T00:00:00Z", "html_url": f"https://github.com/{login}", "bio": "Hola"}
	api.fijados.return_value = [{"nameWithOwner": f"{login}/x", "description": "d", "stargazerCount": 4}]
	api.contribuciones.return_value = {"totalCommitContributions": 10, "contributionCalendar": {"totalContributions": 20}}
	api.sigo_a.return_value = False
	api.bloqueados.return_value = []
	api.repositorios_de.return_value = Pagina([{"full_name": f"{login}/x", "description": "d"}])
	return ctx, api, anuncios


def test_perfil_de_otra_persona(app_wx, marco):
	from app.ui.detalle.usuario import VentanaUsuario

	ctx, api, _a = _contexto_usuario()
	ventana = VentanaUsuario(None, ctx, "berta")
	ventana.cargar()
	assert "Contribuciones del último año: 20" in ventana.datos.GetValue() and "Biografía: Hola" in ventana.datos.GetValue()
	assert ventana.lista_fijados.texto_celda(0, 0) == "berta/x"
	_sin_errores(ventana)
	ventana.seguir()
	api.seguir.assert_called_once_with("berta")
	assert ventana.boton_seguir.GetLabel() == "Dejar de &seguir"
	ventana._cargar_pagina(1)
	assert ventana.paneles[1].lista.numero_filas() == 1
	api.repositorios_de.assert_called_once_with("berta", 1)
	ventana.Destroy()


def test_perfil_propio_permite_editarlo(app_wx, marco, dialogo_modal):
	from app.ui.detalle.usuario import VentanaUsuario

	ctx, api, _a = _contexto_usuario("ana")
	ventana = VentanaUsuario(None, ctx, "ana")
	ventana.cargar()
	assert ventana.boton_seguir is None
	_sin_errores(ventana)

	def cambiar_nombre(dialogo):
		_sin_errores(dialogo)
		dialogo.controles["name"].SetValue("Ana Pérez")
		return wx.ID_OK

	dialogo_modal.responder(cambiar_nombre)
	ventana.editar_perfil()
	assert api.actualizar_perfil.call_args.kwargs["name"] == "Ana Pérez"
	ventana.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Organización
# ════════════════════════════════════════════════════════════════════════════


def test_organizacion_miembros_e_invitaciones(app_wx, marco, dialogo_modal):
	from app.ui.detalle.organizacion import VentanaOrganizacion

	ctx, api, _a = crear_contexto()
	api.organizacion.return_value = {"login": "acme", "name": "ACME", "public_repos": 2, "html_url": "https://github.com/acme"}

	def miembros(org, pagina=1, rol="all"):
		return [{"login": "ana"}] if rol == "admin" else Pagina([{"login": "ana"}, {"login": "berta"}])

	api.miembros.side_effect = miembros
	ventana = VentanaOrganizacion(None, ctx, "acme")
	ventana.cargar()
	assert "ACME" in ventana.GetTitle() and "Repositorios públicos: 2" in ventana.datos.GetValue()
	_sin_errores(ventana)
	panel = ventana.paneles[2]
	panel.cargar()
	assert [panel.lista.texto_celda(i, 1) for i in range(2)] == ["Propietario", "Miembro"]
	invitaciones = ventana.paneles[4]

	def invitar(dialogo):
		dialogo.controles["correo"].SetValue("nueva@ejemplo.es")
		return wx.ID_OK

	dialogo_modal.responder(invitar)
	invitaciones.definicion.acciones[0].funcion(invitaciones, None)
	api.invitar.assert_called_once_with("acme", "nueva@ejemplo.es", "direct_member")
	dialogo_modal.responder(wx.ID_YES)
	invitaciones.definicion.acciones[1].funcion(invitaciones, {"id": 33, "email": "x@y.es"})
	api.c.delete.assert_called_once_with("/orgs/acme/invitations/33")
	ventana.Destroy()
