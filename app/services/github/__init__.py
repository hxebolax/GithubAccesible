"""Acceso a GitHub: cliente HTTP, autenticación y fachada de la API por áreas."""

from __future__ import annotations

from app.services.github.api import (
	ApiCommits,
	ApiContenidos,
	ApiIssues,
	ApiPulls,
	ApiRamas,
	ApiReleases,
	ApiRepositorios,
	ApiUsuarios,
)
from app.services.github.api_extra import (
	ApiAcciones,
	ApiBusqueda,
	ApiCodespaces,
	ApiGists,
	ApiNotificaciones,
	ApiOrganizaciones,
	ApiPaquetes,
	ApiSeguridad,
	ApiVarios,
)
from app.services.github.api_graphql import ApiGraphQL
from app.services.github.cliente import ClienteGitHub


class ApiGitHub(
	ApiUsuarios,
	ApiRepositorios,
	ApiContenidos,
	ApiRamas,
	ApiCommits,
	ApiIssues,
	ApiPulls,
	ApiReleases,
	ApiAcciones,
	ApiGists,
	ApiNotificaciones,
	ApiOrganizaciones,
	ApiBusqueda,
	ApiSeguridad,
	ApiPaquetes,
	ApiCodespaces,
	ApiVarios,
	ApiGraphQL,
):
	"""Todas las operaciones de GitHub en un solo objeto: ``ApiGitHub(cliente).issues(...)``."""

	def __init__(self, cliente: ClienteGitHub) -> None:
		super().__init__(cliente)

	@property
	def cliente(self) -> ClienteGitHub:
		return self.c


__all__ = ["ApiGitHub", "ClienteGitHub"]
