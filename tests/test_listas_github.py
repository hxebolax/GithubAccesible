"""«Mis issues» por búsqueda (#9), columnas de personas (#10) y de repositorios (#11)."""

from __future__ import annotations

from unittest import mock

import pytest

from app.services.github.cliente import ErrorGitHub, Pagina
from app.ui.vistas import principales as p
from app.ui.vistas.base import PanelLista
from tests.apoyo_app import crear_contexto


class _Panel:
	def __init__(self, datos=None):
		self.ctx = mock.MagicMock()
		self.ctx.usuario = "michal"
		self.ctx.config.obtener.side_effect = lambda clave, defecto=None: defecto
		self.datos = dict(datos or {})


# ── #9: Mis issues ──────────────────────────────────────────────────────────


def test_mis_issues_busca_las_creadas_en_cualquier_repositorio():
	api = mock.MagicMock()
	vista = p.vista_mis_issues()
	vista.cargar(api, 1, _Panel())
	consulta = api.buscar.call_args.args[1]
	assert api.buscar.call_args.args[0] == "issues"
	assert consulta == "is:issue author:@me archived:false is:open", "de fábrica, las creadas por mí y abiertas"
	vista.cargar(api, 2, _Panel({"filtro": "assignee:@me", "estado": "all"}))
	assert api.buscar.call_args.args[1] == "is:issue assignee:@me archived:false"
	assert not api.mis_issues.called, "/issues solo daba repositorios propios o de miembro"


def test_filtro_guardado_antiguo_no_rompe_el_dialogo(app_wx, marco, dialogo_modal):
	ctx, _api, _a = crear_contexto()
	panel = PanelLista(marco, ctx, p.vista_mis_issues(), {"filtro": "assigned"})
	dialogo_modal.responder(lambda dialogo: 0)
	assert p._elegir_filtro_y_estado(panel, p.FILTROS_ISSUES, "filtro") is False


# ── #10: personas ───────────────────────────────────────────────────────────

PERSONA = {"login": "ana", "name": "Ana", "html_url": "https://github.com/ana", "type": "User",
	"created_at": "2015-03-01T10:00:00Z", "followers": 1234, "public_repos": 42, "contribuciones": 987}


def test_personas_por_graphql_con_cursores():
	api = mock.MagicMock()
	api.personas.side_effect = [Pagina([PERSONA], siguiente="CURSOR2"), Pagina([dict(PERSONA, login="bea")])]
	datos: dict = {}
	primera = p.cargar_personas(api, 1, datos, seguidores=False)
	assert primera.elementos[0]["login"] == "ana" and primera.hay_mas
	p.cargar_personas(api, 2, datos, seguidores=False)
	assert api.personas.call_args_list[0].args == (False, 30, None)
	assert api.personas.call_args_list[1].args == (False, 30, "CURSOR2"), "la página 2 sigue el cursor de la 1"


def test_personas_sin_contribuciones_y_por_rest_si_graphql_falla():
	api = mock.MagicMock()

	def personas(seguidores, n, despues, contribuciones=True):
		if contribuciones:
			raise ErrorGitHub("demasiado costoso")
		return Pagina([dict(PERSONA, contribuciones=None)])

	api.personas.side_effect = personas
	datos: dict = {}
	resultado = p.cargar_personas(api, 1, datos, seguidores=True)
	assert resultado.elementos[0]["contribuciones"] is None and datos["_sin_contribuciones"]
	api.personas.side_effect = ErrorGitHub("sin GraphQL")
	api.seguidores.return_value = Pagina([{"login": "rest"}])
	assert p.cargar_personas(api, 1, {}, seguidores=True).elementos[0]["login"] == "rest"


def test_columnas_de_personas():
	ctx = mock.MagicMock()
	columnas = {c.id: c for c in p.columnas_persona()}
	assert {"repos_publicos", "seguidores", "desde", "contribuciones", "enlace"} <= {i for i, c in columnas.items() if c.visible}
	assert columnas["repos_publicos"].valor(PERSONA, ctx) == "42"
	assert columnas["seguidores"].valor(PERSONA, ctx) == "1.234"
	assert "2015" in columnas["desde"].valor(PERSONA, ctx)
	assert columnas["contribuciones"].valor(PERSONA, ctx) == "987"
	assert columnas["enlace"].valor(PERSONA, ctx) == "https://github.com/ana"


# ── #11: repositorios ───────────────────────────────────────────────────────

REPO = {
	"full_name": "ana/repo", "node_id": "R_1", "created_at": "2020-01-02T03:04:05Z", "size": 2048,
	"license": {"spdx_id": "GPL-3.0", "name": "GNU General Public License v3.0"}, "topics": ["nvda", "github"],
	"homepage": "https://ana.dev", "html_url": "https://github.com/ana/repo", "clone_url": "https://github.com/ana/repo.git",
	"ssh_url": "git@github.com:ana/repo.git", "permissions": {"admin": False, "maintain": False, "push": True, "pull": True},
}


@pytest.fixture
def ctx_falso():
	ctx = mock.MagicMock()
	ctx.relativas.return_value = False
	return ctx


def test_columnas_nuevas_de_repositorios(ctx_falso):
	columnas = {c.id: c for c in p.columnas_repositorio()}
	valores = {i: c.valor(REPO, ctx_falso) for i, c in columnas.items()}
	assert "2020" in valores["creado"] and valores["tamano"] == "2,0 MB" and valores["licencia"] == "GPL-3.0"
	assert valores["temas"] == "nvda, github" and valores["web"] == "https://ana.dev"
	assert valores["clonar_https"].endswith(".git") and valores["clonar_ssh"].startswith("git@")
	assert valores["permiso"] == "Escritura"
	assert not columnas["creado"].visible and {c.id: c for c in p.columnas_repositorio(True)}["creado"].visible
	assert {c.id: c for c in p.vista_mis_repositorios().columnas}["creado"].visible, "«Creado» visible en Mis repositorios"


def test_observadores_y_ultima_release_solo_si_se_ven(ctx_falso):
	api = mock.MagicMock()
	repo = dict(REPO)
	p.completar_repositorios(api, [repo], {"nombre", "estrellas"})
	assert not api.datos_extra_repos.called, "sin esas columnas no se gasta una consulta"
	api.datos_extra_repos.return_value = {"R_1": {"observadores": 7, "ultima_release": {
		"tag": "v1.0.10", "nombre": "", "fecha": "2026-11-23T10:00:00Z"}}}
	p.completar_repositorios(api, [repo], {"nombre", "observadores"})
	columnas = {c.id: c for c in p.columnas_repositorio()}
	assert columnas["observadores"].valor(repo, ctx_falso) == "7"
	assert columnas["ultima_release"].valor(repo, ctx_falso).startswith("v1.0.10, ")
	assert "Su permiso: Escritura" in p.detalle_repositorio(repo, ctx_falso)


def test_el_panel_completa_con_las_columnas_visibles(app_wx, marco):
	ctx, api, _a = crear_contexto()
	vistas = []
	definicion = p.vista_estrellas()
	definicion.cargar = lambda api_, pagina, panel: [dict(REPO)]
	definicion.completar = lambda api_, elementos, columnas: vistas.append((len(elementos), columnas))
	panel = PanelLista(marco, ctx, definicion)
	panel.cargar()
	assert vistas and vistas[0][0] == 1 and "nombre" in vistas[0][1] and "observadores" not in vistas[0][1]
