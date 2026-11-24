"""Actividad de un perfil más allá de los 30 días de eventos (incidencia #12).

No usan la red: la API y GraphQL se simulan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from app.services import formato as f
from app.services.github.api_graphql import ApiGraphQL
from app.services.github.cliente import ErrorGitHub, Pagina
from app.ui.detalle import usuario


def _coleccion(commits=(), issues=(), siguiente=False, creado="2019-03-25T22:24:53Z"):
	return {"rateLimit": {"cost": 1, "remaining": 4999}, "user": {"createdAt": creado, "contributionsCollection": {
		"commitContributionsByRepository": [{"repository": {"nameWithOwner": "ana/repo"}, "contributions": {
			"pageInfo": {"hasNextPage": siguiente}, "nodes": [{"occurredAt": m, "commitCount": 3} for m in commits]}}],
		"issueContributions": {"pageInfo": {"hasNextPage": False}, "nodes": [
			{"occurredAt": m, "issue": {"number": 7, "title": "Fallo", "url": "u", "repository": {"nameWithOwner": "otro/repo"}}}
			for m in issues]},
		"pullRequestContributions": {"pageInfo": {"hasNextPage": False}, "nodes": []},
		"pullRequestReviewContributions": {"pageInfo": {"hasNextPage": False}, "nodes": []},
		"repositoryContributions": {"pageInfo": {"hasNextPage": False}, "nodes": []},
	}}}


def _api_graphql(respuestas):
	api = ApiGraphQL.__new__(ApiGraphQL)
	api.c = mock.MagicMock()
	api.c.graphql.side_effect = respuestas
	return api


DESDE = datetime(2025, 1, 1, tzinfo=UTC)
HASTA = datetime(2026, 1, 1, tzinfo=UTC)


def test_contribuciones_como_eventos_del_feed():
	api = _api_graphql([_coleccion(commits=["2025-05-01T00:00:00Z"], issues=["2025-06-01T10:00:00Z", "2027-01-01T00:00:00Z"])])
	eventos, creado = api.historial_contribuciones("ana", DESDE, HASTA)
	assert creado == "2019-03-25T22:24:53Z"
	assert [e["type"] for e in eventos] == ["IssuesEvent", "_CommitContribution"], "ordenados del más reciente al más antiguo"
	assert f.describir_evento(eventos[1]) == "ana hizo 3 commits en ana/repo"
	assert f.describir_evento(eventos[0]) == "ana abrió la issue #7 en otro/repo: Fallo"
	assert api.c.graphql.call_count == 1, "un año cabe en una consulta (1 punto)"


def test_si_github_corta_una_lista_el_tramo_se_parte():
	api = _api_graphql([
		_coleccion(commits=["2025-11-01T00:00:00Z"], siguiente=True),
		_coleccion(commits=["2025-11-01T00:00:00Z", "2025-09-01T00:00:00Z"]),
		_coleccion(commits=["2025-03-01T00:00:00Z"]),
	])
	eventos, _creado = api.historial_contribuciones("ana", DESDE, HASTA)
	assert api.c.graphql.call_count == 3
	assert [e["created_at"][:7] for e in eventos] == ["2025-11", "2025-09", "2025-03"], "sin duplicados en el borde"


def _panel(historial=True):
	panel = mock.MagicMock()
	panel.datos = {"login": "ana"}
	panel.elementos = []
	panel.ctx.config.obtener.side_effect = lambda clave, defecto=None: historial if clave == "listas.historial_actividad" else defecto
	return panel


def test_tras_los_eventos_sigue_el_historial_hasta_el_alta():
	api = mock.MagicMock()
	evento = {"type": "WatchEvent", "created_at": "2026-11-01T10:00:00Z", "actor": {"login": "ana"}, "repo": {"name": "x/y"}}
	api.eventos_de.return_value = Pagina([evento])
	creado = "2024-06-01T00:00:00Z"
	tramos = []

	def historial(login, desde, hasta):
		tramos.append((desde, hasta))
		return ([{"type": "_CommitContribution", "created_at": (hasta - timedelta(days=1)).isoformat()}], creado)

	api.historial_contribuciones.side_effect = historial
	panel = _panel()
	primera = usuario.cargar_actividad(api, 1, panel)
	assert primera.elementos == [evento] and primera.hay_mas, "los eventos se acaban, pero hay historial"
	panel.elementos = list(primera.elementos)
	paginas = [usuario.cargar_actividad(api, n, panel) for n in (2, 3, 4)]
	assert tramos[0][1] == datetime(2026, 11, 1, 10, tzinfo=UTC), "empieza donde acaba el evento más antiguo"
	assert all(t[1] - t[0] == usuario.TRAMO_HISTORIAL for t in tramos)
	assert [p.hay_mas for p in paginas] == [True, True, False], "termina al pasar la fecha de alta"


def test_sin_la_opcion_solo_los_30_dias_y_un_fallo_no_rompe_la_lista():
	api = mock.MagicMock()
	api.eventos_de.return_value = Pagina([])
	assert not usuario.cargar_actividad(api, 1, _panel(historial=False)).hay_mas
	assert not api.historial_contribuciones.called
	panel = _panel()
	usuario.cargar_actividad(api, 1, panel)
	api.historial_contribuciones.side_effect = ErrorGitHub("sin GraphQL")
	resultado = usuario.cargar_actividad(api, 2, panel)
	assert resultado.elementos == [] and not resultado.hay_mas
