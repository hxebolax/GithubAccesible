"""Vigilar ejecuciones de GitHub Actions en segundo plano y avisar al terminar (sin wx).

Por qué: después de un push, o tras relanzar un flujo, la persona quiere saber
si ha ido bien sin tener abierta la ventana de la ejecución ni volver a mirar
cada minuto. La ventana principal llama a ``comprobar`` cada cierto tiempo (en
un hilo) y dice los avisos con voz, sonido y, si se quiere, una notificación
de Windows.

Qué se puede vigilar (cada elemento es un diccionario que se guarda en
``acciones.vigiladas`` para que sobreviva a un reinicio):

- ``ejecucion``: una ejecución concreta; se avisa al terminar y se deja de vigilar.
- ``commit``: las ejecuciones que lance un commit (por ejemplo, el que se acaba
  de enviar con push). Se espera a que aparezcan (hasta ``ESPERA_COMMIT_MIN``),
  se avisa de cada una al terminar y se deja de vigilar cuando acaban todas.
- ``repositorio``: todas las ejecuciones de un repositorio; se avisa de cada una
  que termine a partir de ese momento, hasta que la persona lo quite.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

#: Minutos que se espera a que un commit lance sus ejecuciones antes de dejarlo.
ESPERA_COMMIT_MIN = 10
#: Ejecuciones ya avisadas que se recuerdan por elemento (para no repetir avisos).
MAXIMO_AVISADAS = 200


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


RESULTADOS = {
	"success": "correcta",
	"failure": "fallida",
	"cancelled": "cancelada",
	"skipped": "omitida",
	"timed_out": "se agotó el tiempo",
	"action_required": "necesita aprobación",
	"neutral": "neutra",
	"stale": "caducada",
	"startup_failure": "no pudo arrancar",
}


@dataclass(frozen=True)
class Aviso:
	"""Una ejecución terminada de la que hay que avisar."""

	repo: str
	id: int
	nombre: str
	conclusion: str
	rama: str = ""
	url: str = ""

	@property
	def correcta(self) -> bool:
		return self.conclusion in ("success", "skipped", "neutral")

	@property
	def texto(self) -> str:
		resultado = _(RESULTADOS.get(self.conclusion, self.conclusion or "terminada"))
		rama = _(" en {r}").format(r=self.rama) if self.rama else ""
		return _("Actions de {repo}: «{n}»{rama} ha terminado: {res}.").format(repo=self.repo, n=self.nombre, rama=rama,
			res=resultado)


def _ahora() -> datetime:
	return datetime.now(UTC)


def _fecha(texto: str | None) -> datetime | None:
	if not texto:
		return None
	try:
		return datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
	except ValueError:
		return None


def _aviso(repo: str, run: dict) -> Aviso:
	return Aviso(repo, int(run.get("id") or 0), str(run.get("name") or run.get("display_title") or _("flujo")),
		str(run.get("conclusion") or ""), str(run.get("head_branch") or ""), str(run.get("html_url") or ""))


def _elementos(resultado: Any) -> list[dict]:
	elementos = getattr(resultado, "elementos", resultado)
	return [e for e in (elementos or []) if isinstance(e, dict)]


# ── Crear elementos vigilados ────────────────────────────────────────────────


def nueva_ejecucion(repo: str, run: dict) -> dict:
	return {"tipo": "ejecucion", "repo": repo, "id": int(run.get("id") or 0),
		"nombre": str(run.get("name") or run.get("display_title") or "")}


def nuevo_commit(repo: str, sha: str, ahora: datetime | None = None) -> dict:
	return {"tipo": "commit", "repo": repo, "sha": sha, "desde": (ahora or _ahora()).isoformat(), "avisadas": [], "vistas": 0}


def nuevo_repositorio(repo: str, ahora: datetime | None = None) -> dict:
	return {"tipo": "repositorio", "repo": repo, "desde": (ahora or _ahora()).isoformat(), "avisadas": []}


def describir(elemento: dict) -> str:
	"""Texto para la lista de «Ejecuciones vigiladas»."""
	tipo, repo = elemento.get("tipo"), elemento.get("repo", "")
	if tipo == "ejecucion":
		return _("Ejecución «{n}» de {r}").format(n=elemento.get("nombre") or elemento.get("id"), r=repo)
	if tipo == "commit":
		return _("Ejecuciones del commit {s} de {r}").format(s=str(elemento.get("sha", ""))[:7], r=repo)
	return _("Todas las ejecuciones de {r}").format(r=repo)


def misma(a: dict, b: dict) -> bool:
	"""Dos elementos vigilan lo mismo (para no duplicarlos)."""
	if a.get("tipo") != b.get("tipo") or str(a.get("repo", "")).casefold() != str(b.get("repo", "")).casefold():
		return False
	return a.get("id") == b.get("id") and a.get("sha") == b.get("sha")


# ── Comprobar ────────────────────────────────────────────────────────────────


def comprobar(api: Any, vigiladas: list[dict], ahora: datetime | None = None) -> tuple[list[Aviso], list[dict]]:
	"""Pregunta a GitHub por cada elemento vigilado.

	Devuelve ``(avisos, vigiladas_que_siguen)``. Un fallo de red en un elemento no
	lo quita (se vuelve a intentar la próxima vez) ni impide comprobar los demás;
	un 404 (repositorio o ejecución borrados) sí lo quita.
	"""
	ahora = ahora or _ahora()
	avisos: list[Aviso] = []
	siguen: list[dict] = []
	for elemento in vigiladas:
		try:
			nuevos, sigue = _comprobar_uno(api, dict(elemento), ahora)
		except Exception as error:  # noqa: BLE001 - un elemento que falla no detiene la vigilancia de los demás
			if getattr(error, "codigo_http", None) == 404:
				log.info("Se deja de vigilar %s: ya no existe", describir(elemento))
				continue
			log.info("No se pudo comprobar %s: %s", describir(elemento), error)
			siguen.append(elemento)
			continue
		avisos.extend(nuevos)
		if sigue is not None:
			siguen.append(sigue)
	return avisos, siguen


def _comprobar_uno(api: Any, elemento: dict, ahora: datetime) -> tuple[list[Aviso], dict | None]:
	repo = elemento.get("repo", "")
	tipo = elemento.get("tipo")
	if tipo == "ejecucion":
		run = api.ejecucion(repo, int(elemento.get("id") or 0)) or {}
		if run.get("status") == "completed":
			return [_aviso(repo, run)], None
		return [], elemento
	avisadas = [int(x) for x in elemento.get("avisadas") or []]
	if tipo == "commit":
		runs = _elementos(api.ejecuciones(repo, 1, sha=str(elemento.get("sha", ""))))
		nuevos = [_aviso(repo, r) for r in runs if r.get("status") == "completed" and int(r.get("id") or 0) not in avisadas]
		avisadas += [a.id for a in nuevos]
		elemento["avisadas"] = avisadas[-MAXIMO_AVISADAS:]
		elemento["vistas"] = max(int(elemento.get("vistas") or 0), len(runs))
		if runs and all(r.get("status") == "completed" for r in runs):
			return nuevos, None
		desde = _fecha(elemento.get("desde")) or ahora
		if not runs and ahora - desde > timedelta(minutes=ESPERA_COMMIT_MIN):
			log.info("El commit %s de %s no ha lanzado ejecuciones; se deja de vigilar", elemento.get("sha"), repo)
			return nuevos, None
		return nuevos, elemento
	# repositorio
	desde = _fecha(elemento.get("desde")) or ahora
	runs = _elementos(api.ejecuciones(repo, 1))
	nuevos = []
	for run in runs:
		identificador = int(run.get("id") or 0)
		terminada = _fecha(run.get("updated_at")) or ahora
		if run.get("status") == "completed" and identificador not in avisadas and terminada >= desde:
			nuevos.append(_aviso(repo, run))
			avisadas.append(identificador)
	elemento["avisadas"] = avisadas[-MAXIMO_AVISADAS:]
	return nuevos, elemento
