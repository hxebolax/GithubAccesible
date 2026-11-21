"""Pruebas de la ventana de un repositorio, sus secciones y sus diálogos (sin red).

La API es un ``MagicMock`` con respuestas realistas; las tareas se ejecutan en
el acto (``tests.apoyo_app``) y los diálogos modales responden con la fixture
``dialogo_modal``. La ventana nunca se muestra (``Show`` se sustituye).
"""

from __future__ import annotations

import sys
import types
from unittest import mock

import pytest
import wx

from app.services.github.cliente import ErrorGitHub, Pagina
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto, letra_de_acceso, normalizar_atajo
from app.ui.repositorio import dialogos as d
from app.ui.repositorio import paneles as p
from app.ui.repositorio import ventana as v
from app.ui.repositorio import vistas
from app.ui.vistas.base import PanelLista
from tests.apoyo_app import crear_contexto

NOMBRE = "ana/proyecto"

REPO = {
	"full_name": NOMBRE, "name": "proyecto", "description": "Antigua", "homepage": "", "default_branch": "main",
	"visibility": "public", "private": False, "stargazers_count": 12, "forks_count": 1, "topics": ["wx"],
	"has_issues": True, "has_wiki": False, "has_projects": False, "has_discussions": False, "is_template": False,
	"html_url": "https://github.com/ana/proyecto", "clone_url": "https://github.com/ana/proyecto.git",
	"permissions": {"admin": True},
}
ISSUE = {"number": 7, "title": "Falla al abrir", "state": "open", "user": {"login": "luis"}, "labels": [{"name": "error"}],
	"assignees": [], "comments": 2, "html_url": "https://github.com/ana/proyecto/issues/7"}
PR_EN_ISSUES = {"number": 8, "title": "Arreglo", "state": "open", "pull_request": {"url": "x"}}
PR = {"number": 8, "title": "Arreglo", "state": "open", "user": {"login": "ana"}, "head": {"ref": "arreglo"}, "base": {"ref": "main"}}
RAMA = {"name": "main", "protected": False, "commit": {"sha": "abc1234567"}}


def api_repo() -> mock.MagicMock:
	api = mock.MagicMock(name="ApiGitHub")
	api.repositorio.return_value = dict(REPO)
	api.lenguajes.return_value = {"Python": 900, "C": 100}
	api.ultima_release.return_value = {"tag_name": "v1.0", "name": "Primera", "published_at": "2025-01-01T00:00:00Z"}
	api.contenido.return_value = [
		{"type": "file", "name": "README.md", "path": "README.md", "size": 120, "sha": "s1"},
		{"type": "dir", "name": "app", "path": "app"},
	]
	api.issues.return_value = Pagina([ISSUE, PR_EN_ISSUES])
	api.prs.return_value = Pagina([PR])
	api.discusiones.return_value = ([{"id": "D1", "number": 3, "title": "Ideas", "closed": False, "category": {"name": "Ideas"},
		"comments": {"totalCount": 1}, "url": "https://github.com/ana/proyecto/discussions/3"}], None)
	api.ejecuciones.return_value = Pagina([{"id": 99, "name": "CI", "display_title": "Pruebas", "status": "completed",
		"conclusion": "failure", "head_branch": "main", "event": "push"}])
	api.releases.return_value = Pagina([{"id": 4, "name": "Primera", "tag_name": "v1.0", "draft": True, "assets": []}])
	api.ramas.return_value = Pagina([RAMA, {"name": "desarrollo", "protected": True, "commit": {"sha": "def"}}])
	api.todas_las_ramas.return_value = [RAMA, {"name": "desarrollo", "commit": {"sha": "def"}}]
	api.etiquetas_git.return_value = Pagina([{"name": "v1.0", "commit": {"sha": "abc1234"}}])
	api.commits.return_value = Pagina([{"sha": "abc1234567", "commit": {"message": "Primer commit\n\nDetalle",
		"author": {"name": "Ana", "date": "2025-01-01T00:00:00Z"}}, "author": {"login": "ana"}}])
	api.proyectos_repo.return_value = [{"title": "Plan", "number": 1, "items": {"totalCount": 3}, "url": "https://x"}]
	api.hitos.return_value = [{"number": 1, "title": "Versión 1", "state": "open", "open_issues": 1, "closed_issues": 3}]
	api.etiquetas.return_value = [{"name": "error", "color": "d73a4a", "description": "Algo falla"}]
	api.colaboradores.return_value = Pagina([{"login": "ana", "role_name": "admin"}])
	api.invitaciones_repo.return_value = [{"id": 5, "invitee": {"login": "luis"}, "permissions": "write"}]
	api.bifurcaciones.return_value = Pagina([{"full_name": "luis/proyecto", "owner": {"login": "luis"}}])
	api.observadores_estrella.return_value = Pagina([{"login": "luis", "type": "User"}])
	api.alertas_dependabot.return_value = [{"number": 1, "state": "open", "security_advisory": {"summary": "Fallo en lib",
		"severity": "high"}, "dependency": {"package": {"name": "lib"}, "manifest_path": "requirements.txt"}}]
	api.alertas_codigo.side_effect = ErrorGitHub("El escaneo de código no está activado.", 404)
	api.alertas_secretos.return_value = []
	api.entornos.return_value = [{"name": "production", "protection_rules": [{"type": "wait_timer", "wait_timer": 5}]}]
	api.secretos.return_value = [{"name": "TOKEN"}]
	api.variables.return_value = [{"name": "MODO", "value": "pruebas"}]
	api.webhooks.return_value = [{"id": 6, "config": {"url": "https://ejemplo.org/gancho", "content_type": "json"},
		"events": ["push"], "active": True}]
	api.claves_despliegue.return_value = [{"id": 3, "title": "servidor", "read_only": True, "key": "ssh-ed25519 AAAA"}]
	api.reglas.return_value = [{"id": 1, "name": "principal", "target": "branch", "enforcement": "active"}]
	api.despliegues.return_value = Pagina([{"id": 2, "environment": "production", "ref": "main", "sha": "abcdef1"}])
	api.visitas.return_value = {"count": 10, "uniques": 4, "views": []}
	api.clonados.return_value = {"count": 3, "uniques": 2, "clones": []}
	api.referentes.return_value = [{"referrer": "google.com", "count": 5, "uniques": 3}]
	api.rutas_populares.return_value = []
	api.participacion.return_value = {"all": [1, 2, 3], "owner": [1, 1, 1]}
	api.estadisticas_contribuyentes.return_value = [{"author": {"login": "ana"}, "total": 6, "weeks": [{"a": 10, "d": 2}]}]
	api.pages.return_value = None
	return api


@pytest.fixture
def entorno(app_wx, marco, monkeypatch):
	"""Contexto con la API simulada, ventanas sin mostrar y registro de ventanas limpio."""
	monkeypatch.setattr(v.VentanaRepositorio, "Show", lambda self, mostrar=True: True)
	monkeypatch.setattr(v, "_VENTANAS", {})
	monkeypatch.setattr(p, "ESPERA_ESTADISTICAS", 0)
	ctx, api, anuncios = crear_contexto(api_repo())
	return ctx, api, anuncios


def _panel(marco, ctx, seccion: str, **datos) -> PanelLista:
	definicion = vistas.VISTAS[seccion](NOMBRE)
	panel = PanelLista(marco, ctx, definicion, {"nombre": NOMBRE, "info": dict(REPO), **datos})
	vistas.rotular(panel)
	panel.cargar()
	return panel


def _accion(panel, texto: str):
	for accion in panel.acciones_disponibles():
		if texto in accion.etiqueta.replace("&", ""):
			return accion
	raise AssertionError(f"No hay ninguna acción con «{texto}»: {[a.etiqueta for a in panel.acciones_disponibles()]}")


def _tecla(control: wx.Window, codigo: int, ctrl: bool = False, mayus: bool = False, tipo=wx.wxEVT_KEY_DOWN) -> None:
	evento = wx.KeyEvent(tipo)
	evento.SetKeyCode(codigo)
	evento.SetControlDown(ctrl)
	evento.SetShiftDown(mayus)
	evento.SetEventObject(control)
	control.GetEventHandler().ProcessEvent(evento)


# ════════════════════════════════════════════════════════════════════════════
# Ventana
# ════════════════════════════════════════════════════════════════════════════


def test_abrir_reutiliza_la_ventana_y_cambia_de_seccion(entorno):
	ctx, api, _anuncios = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "issues")
	assert ventana.GetTitle() == "ana/proyecto — GitHub Accesible"
	assert ventana.actual == "issues" and "abrir" in ctx.sonidos.eventos
	assert "Rama por defecto: main" in ventana.GetStatusBar().GetStatusText()
	assert "12 estrellas" in ventana.GetStatusBar().GetStatusText()
	panel = ventana.paginas["issues"]
	assert panel.lista.numero_filas() == 1, "los pull requests no salen entre las issues"
	assert "resumen" not in ventana.paginas, "cada sección se crea al elegirla"
	otra = v.abrir_ventana_repositorio(ctx, "Ana/Proyecto/", "ramas")
	assert otra is ventana and ventana.actual == "ramas"
	assert ventana.lista_secciones.GetStringSelection() == "Ramas"
	ventana.Close()
	assert "cerrar" in ctx.sonidos.eventos and not v.ventanas_abiertas()


def test_nombre_no_valido_avisa(entorno, dialogo_modal):
	ctx, _api, _a = entorno
	assert v.abrir_ventana_repositorio(ctx, "solo-un-nombre") is None
	assert "dueño/nombre" in " ".join(dialogo_modal.ultimo.textos)


def test_teclado_de_la_ventana_y_de_todas_las_secciones(entorno):
	ctx, _api, _a = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE)
	for seccion in v.IDS:
		ventana.mostrar_seccion(seccion, enfocar=False)
		# El menú «Acciones» se rehace con las acciones del elemento enfocado: se revisan sus letras.
		ventana.reconstruir_menu_acciones()
		afirmar_teclado_correcto(ventana, teclas_propias=["F6"])
	assert set(ventana.paginas) == set(v.IDS)


def test_menu_acciones_sin_tabulador_y_con_atajos(entorno):
	ctx, _api, _a = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "issues")
	textos = [i.GetItemLabel() for i in ventana.menu_acciones.GetMenuItems() if not i.IsSeparator()]
	assert all("\t" not in t for t in textos), "con tabulador serían atajos de toda la ventana"
	assert "A&brir (Intro)" in textos and any("(Ctrl+N)" in t for t in textos)


def test_ctrl_tab_y_f6(entorno):
	ctx, _api, anuncios = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "resumen")
	_tecla(ventana, wx.WXK_TAB, ctrl=True, tipo=wx.wxEVT_CHAR_HOOK)
	assert ventana.actual == "codigo" and anuncios[-1] == "Código"
	_tecla(ventana, wx.WXK_TAB, ctrl=True, mayus=True, tipo=wx.wxEVT_CHAR_HOOK)
	_tecla(ventana, wx.WXK_TAB, ctrl=True, mayus=True, tipo=wx.wxEVT_CHAR_HOOK)
	assert ventana.actual == "pages", "da la vuelta al llegar al principio"
	ventana.alternar_foco()  # no debe fallar aunque la ventana no esté visible


def test_seccion_configuracion_abre_el_dialogo(entorno, monkeypatch):
	ctx, _api, _a = entorno
	llamadas = []
	monkeypatch.setattr(wx, "CallAfter", lambda funcion, *a: llamadas.append(funcion))
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "configuracion")
	assert ventana.actual == "resumen"
	assert ventana.configuracion in llamadas


def test_historial_de_un_archivo_va_a_commits_filtrados(entorno):
	ctx, api, _a = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "codigo")
	panel = ventana.paginas["codigo"]
	panel.lista.enfocar_fila(1, anunciar=False)  # README.md (las carpetas van primero)
	panel.ejecutar(_accion(panel, "historial"))
	assert ventana.actual == "commits"
	assert api.commits.call_args.kwargs["ruta"] == "README.md"
	assert "ruta README.md" in ventana.paginas["commits"].etiqueta.GetLabel()


def test_cambio_de_nombre_en_la_configuracion_reabre_la_ventana(entorno):
	ctx, _api, _a = entorno
	ventana = v.abrir_ventana_repositorio(ctx, NOMBRE, "ramas")
	ventana._al_guardar_configuracion(dict(REPO, full_name="ana/nuevo"))
	nuevas = v.ventanas_abiertas()
	assert [n.nombre for n in nuevas] == ["ana/nuevo"] and nuevas[0].actual == "ramas"


# ════════════════════════════════════════════════════════════════════════════
# Secciones
# ════════════════════════════════════════════════════════════════════════════


def test_letras_y_atajos_de_cada_seccion_sin_repetir(entorno, marco):
	ctx, _api, _a = entorno
	for seccion, fabrica in vistas.VISTAS.items():
		panel = PanelLista(marco, ctx, fabrica(NOMBRE), {"nombre": NOMBRE})
		acciones = panel.todas_las_acciones()
		letras = [letra_de_acceso(a.etiqueta) for a in acciones]
		assert None not in letras, f"{seccion}: acción sin letra de acceso"
		repetidas = {l for l in letras if letras.count(l) > 1}
		assert not repetidas, f"{seccion}: letras repetidas {repetidas}"
		por_atajo: dict[str, list] = {}
		for accion in acciones:
			if accion.atajo:
				por_atajo.setdefault(normalizar_atajo(accion.atajo), []).append(accion)
		for atajo, lista in por_atajo.items():
			# Solo se admite repetir un atajo entre acciones que se excluyen (Cerrar / Reabrir).
			assert len(lista) == 1 or all(a.disponible for a in lista), f"{seccion}: atajo {atajo} repetido"
		panel.Destroy()


def test_codigo_entra_en_carpetas_sube_y_abre_archivos(entorno, marco, monkeypatch):
	ctx, api, _a = entorno
	abiertos = []
	modulo = types.ModuleType("app.ui.detalle.archivos")
	modulo.abrir_archivo = lambda ctx, padre, nombre, ruta, ref="": abiertos.append((nombre, ruta, ref))
	monkeypatch.setitem(sys.modules, "app.ui.detalle.archivos", modulo)
	panel = _panel(marco, ctx, "codigo")
	assert [panel.lista.texto_celda(i, 0) for i in range(2)] == ["app", "README.md"]
	assert "carpeta /:" in panel.etiqueta.GetLabel() and "main" in panel.etiqueta.GetLabel()
	panel.definicion.activar(panel, panel.elementos[0])
	assert api.contenido.call_args.args == (NOMBRE, "app", "")
	assert panel.elementos[0]["type"] == "subir" and "carpeta /app" in panel.etiqueta.GetLabel()
	_tecla(panel.lista, wx.WXK_BACK)
	assert panel.datos["ruta"] == "" and api.contenido.call_args.args == (NOMBRE, "", "")
	panel.definicion.activar(panel, panel.elementos[1])
	assert abiertos == [(NOMBRE, "README.md", "")]


def test_borrar_archivo_pide_confirmacion_y_usa_el_sha(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	panel = _panel(marco, ctx, "codigo")
	panel.lista.enfocar_fila(1, anunciar=False)
	dialogo_modal.responder(wx.ID_YES, wx.ID_OK)  # confirmar y aceptar el mensaje del commit
	_tecla(panel.lista, wx.WXK_DELETE)
	api.borrar_archivo.assert_called_once_with(NOMBRE, "README.md", "s1", "Borrar README.md", rama="")
	assert panel.lista.numero_filas() == 1


def test_cerrar_issue_con_motivo(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	panel = _panel(marco, ctx, "issues")
	dialogo_modal.responder(wx.ID_OK)  # primer motivo: completada
	panel.ejecutar(_accion(panel, "Cerrar la issue"))
	api.cerrar_issue.assert_called_once_with(NOMBRE, 7, "completed")


def test_filtro_de_issues_por_estado(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	panel = _panel(marco, ctx, "issues")

	def elegir_cerradas(dialogo):
		dialogo.lista.SetSelection(1)
		return wx.ID_OK

	dialogo_modal.responder(wx.ID_OK, elegir_cerradas)  # «Estado» y después «Cerradas»
	_tecla(panel.lista, wx.WXK_F4)
	assert api.issues.call_args.kwargs["estado"] == "closed"
	assert "cerradas" in panel.etiqueta.GetLabel()


def test_etiquetas_de_una_issue(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.poner_etiquetas.return_value = [{"name": "error"}]
	panel = _panel(marco, ctx, "issues")
	dialogo_modal.responder(wx.ID_OK)  # deja marcada la que ya tenía
	panel.ejecutar(_accion(panel, "etiquetas"))
	api.poner_etiquetas.assert_called_once_with(NOMBRE, 7, ["error"])


def test_borrar_rama_confirmada(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	panel = _panel(marco, ctx, "ramas")
	assert panel.lista.texto_celda(0, 1) == "Sí", "la rama por defecto se marca"
	panel.lista.enfocar_fila(1, anunciar=False)
	dialogo_modal.responder(wx.ID_YES)
	_tecla(panel.lista, wx.WXK_DELETE)
	api.borrar_rama.assert_called_once_with(NOMBRE, "desarrollo")
	assert panel.lista.numero_filas() == 1


def test_proteger_rama(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.proteccion.return_value = None
	panel = _panel(marco, ctx, "ramas")

	def dos_revisiones(dialogo):
		dialogo.revisiones.SetValue(2)
		dialogo.lineal.SetValue(True)
		return wx.ID_OK

	dialogo_modal.responder(dos_revisiones)
	panel.ejecutar(_accion(panel, "Proteger la rama"))
	argumentos = api.proteger.call_args
	assert argumentos.args == (NOMBRE, "main") and argumentos.kwargs["revisiones"] == 2
	assert argumentos.kwargs["historial_lineal"] is True


def test_seguridad_junta_alertas_y_explica_lo_no_disponible(entorno, marco):
	ctx, _api, _a = entorno
	panel = _panel(marco, ctx, "seguridad")
	assert panel.lista.numero_filas() == 2
	assert panel.lista.texto_celda(0, 0) == "Dependabot" and panel.lista.texto_celda(0, 2) == "Alta"
	assert "no disponible" in panel.lista.texto_celda(1, 1)
	panel.lista.enfocar_fila(1, anunciar=False)
	assert not any("Descartar" in a.etiqueta for a in panel.acciones_disponibles())


def test_secreto_nuevo_se_guarda_cifrado(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	panel = _panel(marco, ctx, "secretos")
	assert [panel.lista.texto_celda(i, 2) for i in range(2)] == ["(oculto)", "pruebas"]

	def rellenar(dialogo):
		dialogo.nombre.SetValue("mi_token")
		dialogo.valor.SetValue("valor secreto")
		return wx.ID_OK

	dialogo_modal.responder(rellenar)
	panel.ejecutar(_accion(panel, "Nuevo secreto"))
	api.guardar_secreto.assert_called_once_with(NOMBRE, "MI_TOKEN", "valor secreto")


def test_formulario_que_falla_se_vuelve_a_abrir_con_lo_escrito(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.crear_etiqueta.side_effect = [ErrorGitHub("Ya existe una etiqueta con ese nombre.", 422), {"name": "nueva"}]
	panel = _panel(marco, ctx, "labels")
	vistos = []

	def rellenar(dialogo):
		dialogo.nombre.SetValue("nueva")
		dialogo.color.SetValue("0e8a16")
		return wx.ID_OK

	def comprobar(dialogo):
		vistos.append(dialogo.nombre.GetValue())
		return wx.ID_OK

	dialogo_modal.responder(rellenar, wx.ID_OK, comprobar)  # formulario, mensaje de error, formulario otra vez
	panel.ejecutar(_accion(panel, "Nueva label"))
	assert vistos == ["nueva"], "el segundo intento conserva lo escrito"
	assert api.crear_etiqueta.call_count == 2


def test_colaboradores_e_invitaciones_en_la_misma_lista(entorno, marco):
	ctx, _api, _a = entorno
	panel = _panel(marco, ctx, "colaboradores")
	assert [panel.lista.texto_celda(i, 0) for i in range(2)] == ["luis", "ana"]
	assert panel.lista.texto_celda(0, 2) == "Invitación pendiente"
	etiquetas = [a.etiqueta for a in panel.acciones_disponibles()]
	assert "&Cancelar la invitación…" in etiquetas and "Q&uitar el acceso…" not in etiquetas


def test_lanzar_flujo_sencillo_solo_ofrece_los_que_tienen_workflow_dispatch(entorno, marco, dialogo_modal, monkeypatch):
	ctx, api, _a = entorno
	monkeypatch.setitem(sys.modules, "app.ui.detalle.acciones", types.ModuleType("app.ui.detalle.acciones"))
	api.flujos.return_value = [{"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
		{"id": 2, "name": "Publicar", "path": ".github/workflows/pub.yml", "state": "active"}]
	api.leer_archivo.side_effect = lambda nombre, ruta, ref="": (b"on: push" if "ci" in ruta else b"on:\n  workflow_dispatch:", "")
	panel = _panel(marco, ctx, "acciones")
	opciones = []

	def mirar(dialogo):
		opciones.append(dialogo.lista.GetStrings())
		return wx.ID_OK

	dialogo_modal.responder(mirar, wx.ID_OK)
	panel.ejecutar(_accion(panel, "Lanzar un flujo"))
	assert opciones == [["Publicar"]]
	api.lanzar_flujo.assert_called_once_with(NOMBRE, 2, "main")


# ════════════════════════════════════════════════════════════════════════════
# Paneles de texto
# ════════════════════════════════════════════════════════════════════════════


def test_resumen_muestra_datos_lenguajes_y_readme(entorno, marco, monkeypatch):
	ctx, api, _a = entorno
	api.readme.return_value = "# Proyecto\n\nHola."
	documentos = []
	from app.ui import visor_ayuda

	monkeypatch.setattr(visor_ayuda, "mostrar_documento", lambda padre, titulo, texto, **k: documentos.append((titulo, texto)))
	panel = p.PanelResumen(marco, ctx, {"nombre": NOMBRE})
	panel.cargar()
	assert "Repositorio: ana/proyecto" in panel.texto.GetValue()
	assert "Última release: Primera" in panel.texto.GetValue()
	assert panel.lenguajes.GetStrings() == ["Python: 90,0 %", "C: 10,0 %"]
	assert panel.temas.GetStrings() == ["wx"]
	panel.leer_readme()
	assert documentos == [("README de ana/proyecto", "# Proyecto\n\nHola.")]


def test_estadisticas_reintentan_mientras_github_calcula(entorno, marco):
	ctx, api, _a = entorno
	api.participacion.side_effect = [None, {}, {"all": [1, 2, 3], "owner": [1, 1, 1]}]
	api.visitas.side_effect = ErrorGitHub("Necesita permiso de escritura.", 403)
	panel = p.PanelEstadisticas(marco, ctx, {"nombre": NOMBRE})
	panel.cargar()
	texto = panel.texto.GetValue()
	assert api.participacion.call_count == 3
	assert "6 commits en 52 semanas" in texto
	assert "no disponible (Necesita permiso de escritura.)" in texto
	assert "ana: 6 commits" in texto


def test_estadistica_que_nunca_llega_se_explica(monkeypatch):
	monkeypatch.setattr(p, "ESPERA_ESTADISTICAS", 0)
	assert p.pedir_estadistica(lambda: None) is None
	texto = p.componer_estadisticas({"participacion": None, "contribuyentes": None})
	assert "aún las está calculando" in texto


def test_pages_desactivado_y_activado(entorno, marco):
	ctx, api, _a = entorno
	panel = p.PanelPages(marco, ctx, {"nombre": NOMBRE})
	panel.cargar()
	assert "no está activado" in panel.texto.GetValue()
	assert panel.botones["activar"].IsEnabled() and not panel.botones["desactivar"].IsEnabled()
	api.pages.return_value = {"status": "built", "html_url": "https://ana.github.io/proyecto/", "source": {"branch": "main", "path": "/"}}
	api.compilaciones_pages.return_value = [{"status": "built", "created_at": "2025-01-01T00:00:00Z", "duration": 3000}]
	panel.cargar()
	assert "https://ana.github.io/proyecto/" in panel.texto.GetValue() and "rama main" in panel.texto.GetValue()
	assert not panel.botones["activar"].IsEnabled() and panel.botones["recompilar"].IsEnabled()


# ════════════════════════════════════════════════════════════════════════════
# Diálogos
# ════════════════════════════════════════════════════════════════════════════


def test_teclado_de_todos_los_dialogos(entorno):
	ctx, _api, _a = entorno
	dialogos = [
		d.DialogoCrearRepositorio(None, "ana", ["miorg"], ["Python"], [("mit", "MIT License (MIT)")]),
		d.DialogoVigilancia(None, NOMBRE, "todo"),
		d.DialogoConfiguracion(None, ctx, NOMBRE, REPO, ["main", "desarrollo"]),
		d.DialogoProteccion(None, "main"),
		d.DialogoWebhook(None, ctx.config),
		d.DialogoWebhook(None, ctx.config, {"id": 1, "config": {"url": "https://x"}, "events": ["push"]}),
		d.DialogoSecreto(None),
		d.DialogoClaveDespliegue(None),
		d.DialogoLabel(None),
		d.DialogoHito(None),
		d.DialogoEntorno(None),
	]
	for dialogo in dialogos:
		try:
			afirmar_teclado_correcto(dialogo)
		finally:
			dialogo.Destroy()


def test_crear_repositorio_en_una_organizacion(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.mis_organizaciones.return_value = [{"login": "miorg"}]
	api.plantillas_gitignore.return_value = ["Python"]
	api.licencias.return_value = [{"key": "mit", "name": "MIT License", "spdx_id": "MIT"}]
	api.crear_repositorio.return_value = {"full_name": "miorg/nuevo"}
	creados = []

	def rellenar(dialogo):
		dialogo.dueno.SetSelection(1)
		dialogo.nombre.SetValue("nuevo")
		dialogo.visibilidad.SetSelection(1)
		dialogo.gitignore.SetSelection(1)
		dialogo.licencia.SetSelection(1)
		return wx.ID_OK

	dialogo_modal.responder(rellenar)
	d.dialogo_crear_repositorio(marco, ctx, al_crear=creados.append)
	api.crear_repositorio.assert_called_once_with("nuevo", "", True, org="miorg", auto_init=True, gitignore="Python",
		licencia="mit")
	assert creados == [{"full_name": "miorg/nuevo"}]


def test_crear_repositorio_sin_nombre_explica_y_no_envia(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.mis_organizaciones.return_value = []
	api.plantillas_gitignore.side_effect = ErrorGitHub("Sin conexión", None)
	api.licencias.return_value = []
	dialogo_modal.responder(wx.ID_OK, wx.ID_OK, wx.ID_CANCEL)  # Aceptar vacío, mensaje de error, Cancelar
	d.dialogo_crear_repositorio(marco, ctx)
	api.crear_repositorio.assert_not_called()
	assert any("Escriba el nombre" in " ".join(m.textos) for m in dialogo_modal.mostrados)


def test_crear_desde_plantilla(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.mis_organizaciones.return_value = []
	api.plantillas_gitignore.return_value = []
	api.licencias.return_value = []

	def rellenar(dialogo):
		dialogo.nombre.SetValue("copia")
		dialogo.plantilla.SetValue("luis/plantilla")
		return wx.ID_OK

	dialogo_modal.responder(rellenar)
	d.dialogo_crear_repositorio(marco, ctx)
	api.crear_desde_plantilla.assert_called_once_with("luis/plantilla", "ana", "copia", "", False, False)


def test_vigilancia_marca_la_actual_y_aplica_ignorar(entorno, marco, dialogo_modal):
	ctx, api, anuncios = entorno
	api.suscripcion.return_value = {"subscribed": True, "ignored": False}
	marcada = []

	def ignorar(dialogo):
		marcada.extend(c for c, b in dialogo.botones if b.GetValue())
		dict(dialogo.botones)["ignorar"].SetValue(True)
		return wx.ID_OK

	dialogo_modal.responder(ignorar)
	d.dialogo_vigilancia(marco, ctx, NOMBRE)
	assert marcada == ["todo"]
	api.vigilar.assert_called_once_with(NOMBRE, suscrito=False, ignorado=True)
	assert any("Ignora ana/proyecto" in a for a in anuncios)


def test_configuracion_guarda_solo_lo_cambiado(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	api.editar_repositorio.return_value = dict(REPO, description="Nueva")
	guardados = []

	def cambiar(dialogo):
		dialogo.campo_descripcion.SetValue("Nueva")
		dialogo.campo_temas.SetValue("wx, Python")
		return wx.ID_OK

	dialogo_modal.responder(cambiar)
	d.dialogo_configuracion(marco, ctx, NOMBRE, al_guardar=guardados.append)
	api.editar_repositorio.assert_called_once_with(NOMBRE, description="Nueva")
	api.poner_temas.assert_called_once_with(NOMBRE, ["wx", "python"])
	assert guardados and guardados[0]["topics"] == ["wx", "python"]


def test_borrar_repositorio_exige_escribir_el_nombre(entorno, marco, dialogo_modal):
	ctx, api, _a = entorno
	desaparecidos = []
	dialogo = d.DialogoConfiguracion(marco, ctx, NOMBRE, REPO, ["main"], desaparecidos.append)

	def escribir_mal(caja):
		caja.campo.SetValue("ana/otro")
		return wx.ID_OK

	dialogo_modal.responder(wx.ID_YES, escribir_mal, wx.ID_OK)  # Sí, nombre equivocado, aviso
	dialogo.borrar()
	api.borrar_repositorio.assert_not_called()

	def escribir_bien(caja):
		caja.campo.SetValue(NOMBRE)
		return wx.ID_OK

	dialogo_modal.responder(wx.ID_YES, escribir_bien)
	dialogo.borrar()
	api.borrar_repositorio.assert_called_once_with(NOMBRE)
	assert desaparecidos == ["borrado"]
	dialogo.Destroy()


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras
# ════════════════════════════════════════════════════════════════════════════


def test_etiqueta_con_letra_evita_las_de_la_ventana():
	assert vistas.etiqueta_con_letra("Issues:") == "Iss&ues:"
	assert vistas.etiqueta_con_letra("Ramas:") == "R&amas:"
	assert vistas.etiqueta_con_letra("Pull & push:") == "&Pull && push:"


def test_json_legible():
	texto = vistas.json_legible({"nombre": "principal", "activa": True, "reglas": [{"tipo": "deletion"}], "ramas": ["main"], "x": {}})
	assert texto.splitlines() == ["nombre: principal", "activa: Sí", "reglas:", "\tElemento 1:", "\t\ttipo: deletion",
		"ramas: main", "x: (vacío)"]


def test_nombre_de_colores():
	assert d.nombre_color("d73a4a") == "rojo"
	assert d.nombre_color("#1d76db") == "azul"
	assert d.nombre_color("ffffff") == "blanco"
	assert d.nombre_color("zzz") == ""


def test_fechas_de_hito():
	assert d.fecha_a_iso("31/12/2025") == "2025-12-31T12:00:00Z"
	assert d.fecha_a_iso("2025-12-31") == "2025-12-31T12:00:00Z"
	assert d.fecha_a_iso("") == ""
	assert d.fecha_a_iso("mañana") is None


def test_proteccion_y_vigilancia_desde_la_api():
	valores = d.proteccion_a_valores({"required_pull_request_reviews": {"required_approving_review_count": 2},
		"enforce_admins": {"enabled": True}, "required_status_checks": {"contexts": ["ci"]}})
	assert valores["revisiones"] == 2 and valores["admins"] is True and valores["checks"] == ["ci"]
	assert d.estado_vigilancia(None) == "participando"
	assert d.estado_vigilancia({"subscribed": False, "ignored": True}) == "ignorar"
	assert d.estado_vigilancia({"subscribed": True}) == "todo"
