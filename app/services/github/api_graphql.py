"""Partes de GitHub que solo existen en GraphQL (sin wx).

- Projects (v2): listar proyectos, sus elementos y campos, añadir elementos,
  cambiar el valor de un campo (estado, iteración...), archivar y borrar.
- Discussions: listar, leer con respuestas, crear, comentar, marcar respuesta.
- Hilos de revisión de PR: listar, resolver y reabrir conversaciones.
- Elementos fijados del perfil y calendario de contribuciones.
- Blame de un archivo (autoría línea a línea) sin clonar el repositorio.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.github.api import _Base
from app.services.github.cliente import Pagina, fecha_iso

log = logging.getLogger(__name__)

#: Consulta de las contribuciones de una persona en un intervalo (como máximo un año, lo impone GitHub).
#: Medido: cuesta 1 punto de los 5.000 por hora de GraphQL; un año de una cuenta activa (300 commits,
#: 24 repositorios, pull requests y revisiones) cabe en una sola consulta.
_CONSULTA_CONTRIBUCIONES = """
query($login: String!, $desde: DateTime!, $hasta: DateTime!) {
  rateLimit { cost remaining }
  user(login: $login) {
    createdAt
    contributionsCollection(from: $desde, to: $hasta) {
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner }
        contributions(first: 100) { pageInfo { hasNextPage } nodes { occurredAt commitCount } }
      }
      issueContributions(first: 100) { pageInfo { hasNextPage } nodes { occurredAt issue { number title url repository { nameWithOwner } } } }
      pullRequestContributions(first: 100) { pageInfo { hasNextPage } nodes { occurredAt pullRequest { number title url repository { nameWithOwner } } } }
      pullRequestReviewContributions(first: 100) { pageInfo { hasNextPage } nodes { occurredAt pullRequest { number title url repository { nameWithOwner } } } }
      repositoryContributions(first: 100) { pageInfo { hasNextPage } nodes { occurredAt repository { nameWithOwner } } }
    }
  }
}"""


def _iso(momento: datetime) -> str:
	return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nodos(datos: Any, *ruta: str) -> list:
	for clave in ruta:
		if not isinstance(datos, dict):
			return []
		datos = datos.get(clave)
	if isinstance(datos, dict):
		return [n for n in datos.get("nodes") or [] if n]
	return []


class ApiGraphQL(_Base):
	# ── Projects v2 ───────────────────────────────────────────────────────────

	def proyectos(self, dueno: str, es_org: bool = False, primeros: int = 50) -> list[dict]:
		tipo = "organization" if es_org else "user"
		consulta = f"""
		query($login: String!, $n: Int!) {{
		  {tipo}(login: $login) {{
		    projectsV2(first: $n, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
		      nodes {{ id number title shortDescription closed public url updatedAt items {{ totalCount }} }}
		    }}
		  }}
		}}"""
		return _nodos(self.c.graphql(consulta, {"login": dueno, "n": primeros}), tipo, "projectsV2")

	def proyectos_repo(self, nombre: str) -> list[dict]:
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!) {
		  repository(owner: $o, name: $r) {
		    projectsV2(first: 50) { nodes { id number title shortDescription closed public url updatedAt items { totalCount } } }
		  }
		}"""
		return _nodos(self.c.graphql(consulta, {"o": dueno, "r": repo}), "repository", "projectsV2")

	def campos_proyecto(self, id_proyecto: str) -> list[dict]:
		consulta = """
		query($id: ID!) {
		  node(id: $id) {
		    ... on ProjectV2 {
		      fields(first: 50) {
		        nodes {
		          ... on ProjectV2FieldCommon { id name dataType }
		          ... on ProjectV2SingleSelectField { id name dataType options { id name } }
		          ... on ProjectV2IterationField { id name dataType configuration { iterations { id title startDate } } }
		        }
		      }
		    }
		  }
		}"""
		return _nodos(self.c.graphql(consulta, {"id": id_proyecto}), "node", "fields")

	def elementos_proyecto(self, id_proyecto: str, primeros: int = 100, despues: str | None = None) -> tuple[list[dict], str | None]:
		consulta = """
		query($id: ID!, $n: Int!, $despues: String) {
		  node(id: $id) {
		    ... on ProjectV2 {
		      items(first: $n, after: $despues) {
		        pageInfo { hasNextPage endCursor }
		        nodes {
		          id type isArchived
		          content {
		            ... on Issue { title number url state repository { nameWithOwner } }
		            ... on PullRequest { title number url state repository { nameWithOwner } }
		            ... on DraftIssue { title body }
		          }
		          fieldValues(first: 20) {
		            nodes {
		              ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
		              ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
		              ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
		              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
		              ... on ProjectV2ItemFieldIterationValue { title field { ... on ProjectV2FieldCommon { name } } }
		            }
		          }
		        }
		      }
		    }
		  }
		}"""
		datos = self.c.graphql(consulta, {"id": id_proyecto, "n": primeros, "despues": despues})
		items = (datos.get("node") or {}).get("items") or {}
		info = items.get("pageInfo") or {}
		return [n for n in items.get("nodes") or [] if n], (info.get("endCursor") if info.get("hasNextPage") else None)

	def id_de_nodo(self, nombre: str, numero: int) -> str:
		"""ID global (node_id) de una issue o PR a partir de «dueño/repo» y número."""
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!, $n: Int!) {
		  repository(owner: $o, name: $r) { issueOrPullRequest(number: $n) { ... on Issue { id } ... on PullRequest { id } } }
		}"""
		datos = self.c.graphql(consulta, {"o": dueno, "r": repo, "n": int(numero)})
		return ((datos.get("repository") or {}).get("issueOrPullRequest") or {}).get("id", "")

	def anadir_a_proyecto(self, id_proyecto: str, id_contenido: str) -> str:
		consulta = """
		mutation($p: ID!, $c: ID!) { addProjectV2ItemById(input: {projectId: $p, contentId: $c}) { item { id } } }"""
		datos = self.c.graphql(consulta, {"p": id_proyecto, "c": id_contenido})
		return datos["addProjectV2ItemById"]["item"]["id"]

	def anadir_borrador(self, id_proyecto: str, titulo: str, cuerpo: str = "") -> str:
		consulta = """
		mutation($p: ID!, $t: String!, $b: String) {
		  addProjectV2DraftIssue(input: {projectId: $p, title: $t, body: $b}) { projectItem { id } }
		}"""
		datos = self.c.graphql(consulta, {"p": id_proyecto, "t": titulo, "b": cuerpo})
		return datos["addProjectV2DraftIssue"]["projectItem"]["id"]

	def cambiar_campo(self, id_proyecto: str, id_elemento: str, id_campo: str, valor: dict) -> None:
		"""``valor``: ``{"text": ...}``, ``{"number": ...}``, ``{"date": ...}``,
		``{"singleSelectOptionId": ...}`` o ``{"iterationId": ...}``."""
		consulta = """
		mutation($p: ID!, $i: ID!, $f: ID!, $v: ProjectV2FieldValue!) {
		  updateProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f, value: $v}) { projectV2Item { id } }
		}"""
		self.c.graphql(consulta, {"p": id_proyecto, "i": id_elemento, "f": id_campo, "v": valor})

	def archivar_elemento(self, id_proyecto: str, id_elemento: str, archivar: bool = True) -> None:
		mutacion = "archiveProjectV2Item" if archivar else "unarchiveProjectV2Item"
		self.c.graphql(f"mutation($p: ID!, $i: ID!) {{ {mutacion}(input: {{projectId: $p, itemId: $i}}) {{ item {{ id }} }} }}",
			{"p": id_proyecto, "i": id_elemento})

	def borrar_elemento(self, id_proyecto: str, id_elemento: str) -> None:
		self.c.graphql("mutation($p: ID!, $i: ID!) { deleteProjectV2Item(input: {projectId: $p, itemId: $i}) { deletedItemId } }",
			{"p": id_proyecto, "i": id_elemento})

	def crear_proyecto(self, id_dueno: str, titulo: str) -> dict:
		datos = self.c.graphql("""
		mutation($o: ID!, $t: String!) { createProjectV2(input: {ownerId: $o, title: $t}) { projectV2 { id number url } } }""",
			{"o": id_dueno, "t": titulo})
		return datos["createProjectV2"]["projectV2"]

	def id_usuario_actual(self) -> str:
		return (self.c.graphql("query { viewer { id login } }").get("viewer") or {}).get("id", "")

	# ── Discussions ───────────────────────────────────────────────────────────

	def discusiones(self, nombre: str, primeros: int = 50, despues: str | None = None) -> tuple[list[dict], str | None]:
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!, $n: Int!, $despues: String) {
		  repository(owner: $o, name: $r) {
		    discussions(first: $n, after: $despues, orderBy: {field: UPDATED_AT, direction: DESC}) {
		      pageInfo { hasNextPage endCursor }
		      nodes {
		        id number title url createdAt updatedAt closed isAnswered locked upvoteCount
		        author { login } category { name emoji } comments { totalCount }
		      }
		    }
		  }
		}"""
		datos = self.c.graphql(consulta, {"o": dueno, "r": repo, "n": primeros, "despues": despues})
		disc = (datos.get("repository") or {}).get("discussions") or {}
		info = disc.get("pageInfo") or {}
		return [n for n in disc.get("nodes") or [] if n], (info.get("endCursor") if info.get("hasNextPage") else None)

	def buscar_discusiones(self, consulta: str, primeros: int = 50, despues: str | None = None) -> Pagina:
		"""Busca discusiones (solo existe en GraphQL: ``search(type: DISCUSSION)``).

		Devuelve una ``Pagina`` cuyo ``siguiente`` es el CURSOR de la página
		siguiente (no una URL) y cuyo ``total`` es ``discussionCount``. Cada
		elemento lleva ``html_url``, ``repository.nameWithOwner``, ``_tipo`` =
		«discusion» y los fragmentos resaltados en ``text_matches``.
		"""
		datos = self.c.graphql("""
		query($q: String!, $n: Int!, $despues: String) {
		  search(query: $q, type: DISCUSSION, first: $n, after: $despues) {
		    discussionCount
		    pageInfo { hasNextPage endCursor }
		    edges {
		      textMatches { fragment property highlights { text } }
		      node {
		        ... on Discussion {
		          id number title url createdAt updatedAt closed isAnswered locked upvoteCount
		          author { login } category { name } comments { totalCount } repository { nameWithOwner }
		          labels(first: 10) { nodes { name } }
		        }
		      }
		    }
		  }
		}""", {"q": consulta, "n": max(1, min(100, int(primeros))), "despues": despues})
		busqueda = datos.get("search") or {}
		elementos = []
		for arista in busqueda.get("edges") or []:
			nodo = (arista or {}).get("node") or {}
			if not nodo.get("url"):
				continue
			nodo = dict(nodo, _tipo="discusion", html_url=nodo["url"])
			nodo["text_matches"] = [
				{"fragment": m.get("fragment", ""), "property": m.get("property", ""),
					"matches": [{"text": h.get("text", "")} for h in m.get("highlights") or [] if isinstance(h, dict)]}
				for m in (arista.get("textMatches") or []) if isinstance(m, dict)
			]
			elementos.append(nodo)
		info = busqueda.get("pageInfo") or {}
		total = busqueda.get("discussionCount")
		return Pagina(elementos, (info.get("endCursor") or "") if info.get("hasNextPage") else "", None,
			int(total) if isinstance(total, int) else None)

	def personas(self, seguidores: bool, primeros: int = 30, despues: str | None = None,
		contribuciones: bool = True) -> Pagina:
		"""Seguidores o personas que sigue la cuenta, con sus datos de perfil (incidencia #10).

		La lista REST solo trae el usuario; aquí, en UNA consulta por página, llegan también
		el nombre, los repositorios públicos, los seguidores, la fecha de alta, el enlace y,
		si ``contribuciones``, las del último año (lo más costoso para GitHub: por eso las
		páginas son de 30). Los elementos tienen forma REST (``login``, ``html_url``...) con
		``public_repos``, ``followers``, ``created_at`` y ``contribuciones``.
		"""
		campo = "followers" if seguidores else "following"
		extra = "contributionsCollection { contributionCalendar { totalContributions } }" if contribuciones else ""
		datos = self.c.graphql(f"""
		query($n: Int!, $despues: String) {{
		  viewer {{
		    {campo}(first: $n, after: $despues) {{
		      totalCount
		      pageInfo {{ hasNextPage endCursor }}
		      nodes {{
		        login name url createdAt
		        followers {{ totalCount }}
		        repositories(privacy: PUBLIC, ownerAffiliations: OWNER) {{ totalCount }}
		        {extra}
		      }}
		    }}
		  }}
		}}""", {"n": max(1, min(100, int(primeros))), "despues": despues})
		conexion = ((datos.get("viewer") or {}).get(campo)) or {}
		elementos = []
		for nodo in conexion.get("nodes") or []:
			if not isinstance(nodo, dict) or not nodo.get("login"):
				continue
			calendario = ((nodo.get("contributionsCollection") or {}).get("contributionCalendar") or {})
			elementos.append({
				"login": nodo["login"], "name": nodo.get("name") or "", "html_url": nodo.get("url") or "",
				"type": "User", "created_at": nodo.get("createdAt") or "",
				"followers": (nodo.get("followers") or {}).get("totalCount"),
				"public_repos": (nodo.get("repositories") or {}).get("totalCount"),
				"contribuciones": calendario.get("totalContributions") if contribuciones else None,
			})
		info = conexion.get("pageInfo") or {}
		total = conexion.get("totalCount")
		return Pagina(elementos, (info.get("endCursor") or "") if info.get("hasNextPage") else "", None,
			int(total) if isinstance(total, int) else None)

	def datos_extra_repos(self, ids: list[str]) -> dict[str, dict]:
		"""Observadores reales y última release de varios repositorios en UNA consulta (incidencia #11).

		Las listas REST no los traen (su ``watchers_count`` son en realidad las estrellas).
		:param ids: ``node_id`` de los repositorios (hasta 100).
		:return: ``node_id`` → ``{"observadores": int, "ultima_release": {"tag", "nombre", "fecha"} | None}``.
		"""
		ids = [i for i in ids if i][:100]
		if not ids:
			return {}
		datos = self.c.graphql("""
		query($ids: [ID!]!) {
		  nodes(ids: $ids) {
		    ... on Repository {
		      id
		      watchers { totalCount }
		      latestRelease { tagName name publishedAt }
		    }
		  }
		}""", {"ids": ids})
		resultado: dict[str, dict] = {}
		for nodo in datos.get("nodes") or []:
			if not isinstance(nodo, dict) or not nodo.get("id"):
				continue
			release = nodo.get("latestRelease")
			resultado[nodo["id"]] = {
				"observadores": (nodo.get("watchers") or {}).get("totalCount"),
				"ultima_release": {"tag": release.get("tagName") or "", "nombre": release.get("name") or "",
					"fecha": release.get("publishedAt") or ""} if isinstance(release, dict) else None,
			}
		return resultado

	def historial_contribuciones(self, login: str, desde: datetime, hasta: datetime) -> tuple[list[dict], str]:
		"""Contribuciones de ``login`` en ``[desde, hasta)`` con forma de evento del feed (incidencia #12).

		La API de eventos solo da los últimos 30 días (y 300 eventos como mucho); lo anterior
		solo está en las contribuciones: commits por día y repositorio, issues y pull requests
		abiertos, revisiones y repositorios creados. Si GitHub corta alguna lista (más de 100
		elementos: ``hasNextPage``), el intervalo se parte en dos y se vuelve a pedir: no se pierde nada.

		:return: (eventos, fecha de alta de la persona en GitHub en ISO).
		"""
		datos = self.c.graphql(_CONSULTA_CONTRIBUCIONES, {"login": login, "desde": _iso(desde), "hasta": _iso(hasta)})
		coste = datos.get("rateLimit") or {}
		log.debug("Contribuciones de %s %s-%s: %s puntos, quedan %s", login, _iso(desde), _iso(hasta),
			coste.get("cost"), coste.get("remaining"))
		usuario = datos.get("user") or {}
		coleccion = usuario.get("contributionsCollection") or {}
		creado = usuario.get("createdAt") or ""
		eventos: list[dict] = []
		cortado = False
		actor = {"login": login}

		def anadir(tipo: str, momento: str, repo: str, carga: dict) -> None:
			fecha = fecha_iso(momento)
			# [desde, hasta): un momento justo en el borde no sale en dos tramos.
			if fecha is not None and desde <= fecha < hasta:
				eventos.append({"type": tipo, "actor": actor, "repo": {"name": repo}, "created_at": momento,
					"payload": carga, "_historial": True})

		for grupo in coleccion.get("commitContributionsByRepository") or []:
			repo = ((grupo or {}).get("repository") or {}).get("nameWithOwner", "")
			conexion = (grupo or {}).get("contributions") or {}
			nodos = conexion.get("nodes") or []
			cortado |= bool((conexion.get("pageInfo") or {}).get("hasNextPage"))
			for nodo in nodos:
				anadir("_CommitContribution", nodo.get("occurredAt", ""), repo, {"size": nodo.get("commitCount") or 1})
		for clave, tipo, campo, accion in (
			("issueContributions", "IssuesEvent", "issue", "opened"),
			("pullRequestContributions", "PullRequestEvent", "pullRequest", "opened"),
			("pullRequestReviewContributions", "PullRequestReviewEvent", "pullRequest", "created"),
		):
			conexion = coleccion.get(clave) or {}
			nodos = conexion.get("nodes") or []
			cortado |= bool((conexion.get("pageInfo") or {}).get("hasNextPage"))
			for nodo in nodos:
				objeto = (nodo or {}).get(campo) or {}
				repo = (objeto.get("repository") or {}).get("nameWithOwner", "")
				clave_carga = "issue" if campo == "issue" else "pull_request"
				anadir(tipo, nodo.get("occurredAt", ""), repo, {"action": accion, clave_carga: {
					"number": objeto.get("number"), "title": objeto.get("title") or "", "html_url": objeto.get("url") or ""}})
		conexion = coleccion.get("repositoryContributions") or {}
		nodos = conexion.get("nodes") or []
		cortado |= bool((conexion.get("pageInfo") or {}).get("hasNextPage"))
		for nodo in nodos:
			repo = ((nodo or {}).get("repository") or {}).get("nameWithOwner", "")
			anadir("CreateEvent", nodo.get("occurredAt", ""), repo, {"ref_type": "repository"})

		if cortado and hasta - desde > timedelta(days=2):
			medio = desde + (hasta - desde) / 2
			recientes, _creado = self.historial_contribuciones(login, medio, hasta)
			antiguos, _creado = self.historial_contribuciones(login, desde, medio)
			return recientes + antiguos, creado
		eventos.sort(key=lambda e: e["created_at"], reverse=True)
		return eventos, creado

	def discusion(self, nombre: str, numero: int) -> dict:
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!, $n: Int!) {
		  repository(owner: $o, name: $r) {
		    discussion(number: $n) {
		      id number title body url createdAt closed isAnswered locked upvoteCount
		      author { login } category { name }
		      answer { id }
		      comments(first: 100) {
		        nodes {
		          id body createdAt isAnswer upvoteCount author { login }
		          replies(first: 50) { nodes { id body createdAt author { login } } }
		        }
		      }
		    }
		  }
		}"""
		return ((self.c.graphql(consulta, {"o": dueno, "r": repo, "n": int(numero)}).get("repository") or {}).get("discussion")) or {}

	def categorias_discusion(self, nombre: str) -> tuple[str, list[dict]]:
		"""Devuelve (id del repositorio, categorías)."""
		dueno, repo = nombre.split("/", 1)
		datos = self.c.graphql("""
		query($o: String!, $r: String!) {
		  repository(owner: $o, name: $r) { id discussionCategories(first: 50) { nodes { id name emoji description isAnswerable } } }
		}""", {"o": dueno, "r": repo})
		repositorio = datos.get("repository") or {}
		return repositorio.get("id", ""), _nodos(repositorio, "discussionCategories")

	def crear_discusion(self, id_repo: str, id_categoria: str, titulo: str, cuerpo: str) -> dict:
		datos = self.c.graphql("""
		mutation($r: ID!, $c: ID!, $t: String!, $b: String!) {
		  createDiscussion(input: {repositoryId: $r, categoryId: $c, title: $t, body: $b}) { discussion { id number url } }
		}""", {"r": id_repo, "c": id_categoria, "t": titulo, "b": cuerpo})
		return datos["createDiscussion"]["discussion"]

	def comentar_discusion(self, id_discusion: str, cuerpo: str, responde_a: str | None = None) -> dict:
		datos = self.c.graphql("""
		mutation($d: ID!, $b: String!, $r: ID) {
		  addDiscussionComment(input: {discussionId: $d, body: $b, replyToId: $r}) { comment { id url } }
		}""", {"d": id_discusion, "b": cuerpo, "r": responde_a})
		return datos["addDiscussionComment"]["comment"]

	def marcar_respuesta(self, id_comentario: str, marcar: bool = True) -> None:
		mutacion = "markDiscussionCommentAsAnswer" if marcar else "unmarkDiscussionCommentAsAnswer"
		self.c.graphql(f"mutation($id: ID!) {{ {mutacion}(input: {{id: $id}}) {{ discussion {{ id }} }} }}", {"id": id_comentario})

	def cerrar_discusion(self, id_discusion: str, motivo: str = "RESOLVED") -> None:
		self.c.graphql("mutation($d: ID!, $m: DiscussionCloseReason) { closeDiscussion(input: {discussionId: $d, reason: $m}) { discussion { id } } }",
			{"d": id_discusion, "m": motivo})

	def reabrir_discusion(self, id_discusion: str) -> None:
		self.c.graphql("mutation($d: ID!) { reopenDiscussion(input: {discussionId: $d}) { discussion { id } } }", {"d": id_discusion})

	def votar(self, id_sujeto: str, quitar: bool = False) -> None:
		mutacion = "removeUpvote" if quitar else "addUpvote"
		self.c.graphql(f"mutation($s: ID!) {{ {mutacion}(input: {{subjectId: $s}}) {{ subject {{ id }} }} }}", {"s": id_sujeto})

	# ── Hilos de revisión de pull requests ────────────────────────────────────

	def hilos_revision(self, nombre: str, numero: int) -> list[dict]:
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!, $n: Int!) {
		  repository(owner: $o, name: $r) {
		    pullRequest(number: $n) {
		      reviewThreads(first: 100) {
		        nodes {
		          id isResolved isOutdated path line originalLine diffSide
		          comments(first: 50) { nodes { id databaseId body createdAt author { login } } }
		        }
		      }
		    }
		  }
		}"""
		datos = self.c.graphql(consulta, {"o": dueno, "r": repo, "n": int(numero)})
		return _nodos((datos.get("repository") or {}).get("pullRequest") or {}, "reviewThreads")

	def resolver_hilo(self, id_hilo: str, resolver: bool = True) -> None:
		mutacion = "resolveReviewThread" if resolver else "unresolveReviewThread"
		self.c.graphql(f"mutation($id: ID!) {{ {mutacion}(input: {{threadId: $id}}) {{ thread {{ id isResolved }} }} }}", {"id": id_hilo})

	def activar_fusion_automatica(self, id_pr: str, metodo: str = "MERGE") -> None:
		self.c.graphql("mutation($id: ID!, $m: PullRequestMergeMethod) { enablePullRequestAutoMerge(input: {pullRequestId: $id, mergeMethod: $m}) { pullRequest { id } } }",
			{"id": id_pr, "m": metodo})

	def desactivar_fusion_automatica(self, id_pr: str) -> None:
		self.c.graphql("mutation($id: ID!) { disablePullRequestAutoMerge(input: {pullRequestId: $id}) { pullRequest { id } } }", {"id": id_pr})

	def marcar_listo(self, id_pr: str, listo: bool = True) -> None:
		mutacion = "markPullRequestReadyForReview" if listo else "convertPullRequestToDraft"
		self.c.graphql(f"mutation($id: ID!) {{ {mutacion}(input: {{pullRequestId: $id}}) {{ pullRequest {{ id isDraft }} }} }}", {"id": id_pr})

	# ── Perfil ────────────────────────────────────────────────────────────────

	def fijados(self, login: str) -> list[dict]:
		consulta = """
		query($l: String!) {
		  user(login: $l) {
		    pinnedItems(first: 6, types: [REPOSITORY, GIST]) {
		      nodes {
		        ... on Repository { nameWithOwner description stargazerCount url }
		        ... on Gist { name description url }
		      }
		    }
		  }
		}"""
		return _nodos(self.c.graphql(consulta, {"l": login}), "user", "pinnedItems")

	def contribuciones(self, login: str) -> dict:
		consulta = """
		query($l: String!) {
		  user(login: $l) {
		    contributionsCollection {
		      totalCommitContributions totalIssueContributions totalPullRequestContributions
		      totalPullRequestReviewContributions totalRepositoryContributions
		      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
		    }
		  }
		}"""
		return ((self.c.graphql(consulta, {"l": login}).get("user") or {}).get("contributionsCollection")) or {}

	# ── Blame ─────────────────────────────────────────────────────────────────

	def blame(self, nombre: str, ref: str, ruta: str) -> list[dict]:
		"""Rangos de líneas con su commit (autor, fecha, mensaje)."""
		dueno, repo = nombre.split("/", 1)
		consulta = """
		query($o: String!, $r: String!, $ref: String!, $p: String!) {
		  repository(owner: $o, name: $r) {
		    object(expression: $ref) {
		      ... on Commit {
		        blame(path: $p) {
		          ranges { startingLine endingLine age commit { abbreviatedOid messageHeadline committedDate author { name user { login } } } }
		        }
		      }
		    }
		  }
		}"""
		datos = self.c.graphql(consulta, {"o": dueno, "r": repo, "ref": ref, "p": ruta})
		objeto = (datos.get("repository") or {}).get("object") or {}
		return ((objeto.get("blame") or {}).get("ranges")) or []

	# ── Varios ────────────────────────────────────────────────────────────────

	def fijar_issue(self, id_issue: str, fijar: bool = True) -> None:
		mutacion = "pinIssue" if fijar else "unpinIssue"
		self.c.graphql(f"mutation($id: ID!) {{ {mutacion}(input: {{issueId: $id}}) {{ issue {{ id }} }} }}", {"id": id_issue})

	def transferir_issue(self, id_issue: str, id_repo_destino: str) -> dict:
		datos = self.c.graphql("mutation($i: ID!, $r: ID!) { transferIssue(input: {issueId: $i, repositoryId: $r}) { issue { url number } } }",
			{"i": id_issue, "r": id_repo_destino})
		return datos["transferIssue"]["issue"]

	def id_repo(self, nombre: str) -> str:
		dueno, repo = nombre.split("/", 1)
		return ((self.c.graphql("query($o: String!, $r: String!) { repository(owner: $o, name: $r) { id } }",
			{"o": dueno, "r": repo}).get("repository")) or {}).get("id", "")
