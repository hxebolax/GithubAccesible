"""Punto único para abrir cualquier cosa de GitHub en su ventana.

Las vistas y los diálogos no importan directamente las ventanas de detalle:
llaman a estas funciones. Así se evitan importaciones circulares y se puede
cambiar dónde se abre algo (ventana nueva, misma ventana, navegador) en un
solo sitio. Las importaciones son perezosas para que el arranque sea rápido.
"""

from __future__ import annotations

import builtins
import logging
import re
import webbrowser
from typing import Any

import wx

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def repositorio(ctx: Any, nombre: str, seccion: str = "") -> None:
	from app.ui.repositorio.ventana import abrir_ventana_repositorio

	abrir_ventana_repositorio(ctx, nombre, seccion)


def issue(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
	from app.ui.detalle.issue import abrir_issue

	abrir_issue(ctx, padre, nombre, int(numero))


def pull_request(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
	from app.ui.detalle.pull_request import abrir_pull_request

	abrir_pull_request(ctx, padre, nombre, int(numero))


def issue_o_pr(ctx: Any, padre: wx.Window | None, elemento: dict) -> None:
	"""Abre una issue o un PR a partir de un elemento de búsqueda o de lista de issues."""
	nombre = nombre_repo_de(elemento)
	numero = int(elemento.get("number") or 0)
	if not nombre or not numero:
		webbrowser.open(elemento.get("html_url", ""))
		return
	if elemento.get("pull_request") or "/pull/" in str(elemento.get("html_url", "")):
		pull_request(ctx, padre, nombre, numero)
	else:
		issue(ctx, padre, nombre, numero)


def usuario(ctx: Any, padre: wx.Window | None, login: str) -> None:
	from app.ui.detalle.usuario import abrir_usuario

	abrir_usuario(ctx, padre, login)


def gist(ctx: Any, padre: wx.Window | None, id_gist: str) -> None:
	from app.ui.detalle.gist import abrir_gist

	abrir_gist(ctx, padre, id_gist)


def ejecucion(ctx: Any, padre: wx.Window | None, nombre: str, id_ejecucion: int) -> None:
	from app.ui.detalle.acciones import abrir_ejecucion

	abrir_ejecucion(ctx, padre, nombre, int(id_ejecucion))


def commit(ctx: Any, padre: wx.Window | None, nombre: str, sha: str) -> None:
	from app.ui.detalle.diferencias import abrir_commit

	abrir_commit(ctx, padre, nombre, sha)


def release(ctx: Any, padre: wx.Window | None, nombre: str, elemento: dict) -> None:
	from app.ui.detalle.releases import abrir_release

	abrir_release(ctx, padre, nombre, elemento)


def discusion(ctx: Any, padre: wx.Window | None, nombre: str, numero: int) -> None:
	from app.ui.detalle.discusiones import abrir_discusion

	abrir_discusion(ctx, padre, nombre, int(numero))


def proyecto(ctx: Any, padre: wx.Window | None, proyecto: dict) -> None:
	from app.ui.detalle.proyectos import abrir_proyecto

	abrir_proyecto(ctx, padre, proyecto)


def repositorio_local(ctx: Any, carpeta: str) -> None:
	from app.ui.git.ventana_git import abrir_ventana_git

	abrir_ventana_git(ctx, carpeta)


_NUMERO = re.compile(r"/(issues|pulls|pull|discussions)/(\d+)")


def nombre_repo_de(elemento: dict) -> str:
	"""«dueño/repo» de una issue, PR, notificación o evento de cualquier forma que venga."""
	repo = elemento.get("repository")
	if isinstance(repo, dict) and repo.get("full_name"):
		return repo["full_name"]
	if isinstance(repo, dict) and repo.get("nameWithOwner"):
		return repo["nameWithOwner"]
	url = str(elemento.get("repository_url") or "")
	if "/repos/" in url:
		return url.split("/repos/", 1)[1]
	url = str(elemento.get("html_url") or "")
	coincidencia = re.match(r"https://[^/]+/([^/]+/[^/]+)", url)
	return coincidencia.group(1) if coincidencia else ""


def notificacion(ctx: Any, padre: wx.Window | None, notif: dict) -> None:
	"""Abre lo que motivó una notificación en su ventana (issue, PR, release, Actions...)."""
	nombre = (notif.get("repository") or {}).get("full_name", "")
	sujeto = notif.get("subject") or {}
	tipo = sujeto.get("type", "")
	url = sujeto.get("url") or ""
	coincidencia = _NUMERO.search(url)
	if tipo == "Issue" and coincidencia:
		issue(ctx, padre, nombre, int(coincidencia.group(2)))
	elif tipo == "PullRequest" and coincidencia:
		pull_request(ctx, padre, nombre, int(coincidencia.group(2)))
	elif tipo == "Discussion" and coincidencia:
		discusion(ctx, padre, nombre, int(coincidencia.group(2)))
	elif tipo == "CheckSuite":
		repositorio(ctx, nombre, "acciones")
	elif tipo == "Release":
		repositorio(ctx, nombre, "releases")
	elif tipo == "Commit" and url:
		commit(ctx, padre, nombre, url.rstrip("/").rsplit("/", 1)[-1])
	elif tipo in ("RepositoryVulnerabilityAlert", "RepositoryDependabotAlertsThread"):
		repositorio(ctx, nombre, "seguridad")
	elif nombre:
		repositorio(ctx, nombre)
	else:
		from app.services.formato import url_web_de_api

		webbrowser.open(url_web_de_api(url, ctx.host) or f"https://{ctx.host}/notifications")


def url_github(ctx: Any, padre: wx.Window | None, url: str) -> bool:
	"""Abre en la aplicación una URL de GitHub pegada por la persona. ``False`` si no la entiende."""
	url = url.strip()
	coincidencia = re.match(r"(?:https?://[^/]+/)?([\w.-]+)/([\w.-]+)(?:/(issues|pull|discussions|actions/runs|commit|releases)/?([\w.]+)?)?", url)
	if not coincidencia:
		return False
	dueno, repo, tipo, valor = coincidencia.groups()
	nombre = f"{dueno}/{repo.removesuffix('.git')}"
	if tipo == "issues" and valor and valor.isdigit():
		issue(ctx, padre, nombre, int(valor))
	elif tipo == "pull" and valor and valor.isdigit():
		pull_request(ctx, padre, nombre, int(valor))
	elif tipo == "discussions" and valor and valor.isdigit():
		discusion(ctx, padre, nombre, int(valor))
	elif tipo == "actions/runs" and valor and valor.isdigit():
		ejecucion(ctx, padre, nombre, int(valor))
	elif tipo == "commit" and valor:
		commit(ctx, padre, nombre, valor)
	else:
		repositorio(ctx, nombre, {"releases": "releases", "issues": "issues", "pull": "prs"}.get(tipo or "", ""))
	return True
