"""Cliente HTTP de la API de GitHub (REST y GraphQL), sin wx.

Qué resuelve este módulo, y por qué así:

- **Un único sitio** para cabeceras, autenticación, versión de la API,
  paginación, límites de uso y errores. El resto de la aplicación llama a
  ``get``/``post``/``paginar``/``graphql`` y recibe datos de Python o una
  ``ErrorGitHub`` con un mensaje en español listo para el usuario.
- **GitHub.com y GitHub Enterprise Server**: la base de la API se calcula a
  partir del host (``api.github.com`` o ``https://HOST/api/v3``).
- **Peticiones condicionales con ETag**: GitHub no descuenta del límite las
  respuestas 304, así que refrescar una lista que no cambió sale gratis y
  además es más rápido. La caché vive en memoria (por cliente).
- **Límites de uso** primario (``X-RateLimit-*``) y secundario
  (``Retry-After`` o 403/429 con mensaje de abuso): se convierten en
  ``LimiteAlcanzado`` con la hora de reinicio para poder decirla al usuario.
- **Seguro entre hilos**: cada hilo usa su propia ``requests.Session`` (la
  sesión de requests no es segura entre hilos) y la caché va con candado.
- **Nunca** se escribe el token en el registro: se registra con
  ``registrar_secreto`` para que el sistema de registro lo tape.
"""

from __future__ import annotations

import builtins
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger(__name__)

# Versión más reciente de la API REST en github.com. GitHub Enterprise Server
# puede no admitirla todavía: allí se usa la de compatibilidad (la de siempre).
VERSION_API = "2026-03-10"
VERSION_API_COMPATIBLE = "2022-11-28"
ACEPTAR_JSON = "application/vnd.github+json"
HOST_GITHUB = "github.com"
POR_PAGINA_MAXIMO = 100
# Tope de seguridad al recorrer páginas sin límite explícito (100 x 100 = 10 000 elementos).
PAGINAS_MAXIMAS_POR_DEFECTO = 100
TAMANO_CACHE_ETAG = 500


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ════════════════════════════════════════════════════════════════════════════
# Errores
# ════════════════════════════════════════════════════════════════════════════


class ErrorGitHub(Exception):
	"""Error de la API con mensaje para el usuario (español) y detalle técnico.

	:param mensaje_usuario: frase que se puede mostrar o anunciar tal cual.
	:param codigo_http: código de estado, o ``None`` si no llegó respuesta.
	:param detalle: texto técnico (mensaje de GitHub, URL) para el registro.
	:param errores: lista ``errors`` que devuelve GitHub en los 422.
	:param documentacion: enlace ``documentation_url`` de GitHub.
	"""

	def __init__(
		self,
		mensaje_usuario: str,
		codigo_http: int | None = None,
		detalle: str = "",
		errores: list | None = None,
		documentacion: str = "",
	) -> None:
		super().__init__(detalle or mensaje_usuario)
		self.mensaje_usuario = mensaje_usuario
		self.codigo_http = codigo_http
		self.detalle = detalle
		self.errores = errores or []
		self.documentacion = documentacion
		# El gestor de tareas lo lee para registrar en una sola línea (sin traza) los fallos
		# esperables: los de GitHub ya llevan un mensaje claro y la traza no aporta nada.
		self.transitorio = True

	def __str__(self) -> str:
		return self.mensaje_usuario


class NoAutorizado(ErrorGitHub):
	"""401: token caducado, revocado o inexistente."""


class SinPermiso(ErrorGitHub):
	"""403 que no es por límite de uso: faltan permisos o ámbitos (scopes)."""


class NoEncontrado(ErrorGitHub):
	"""404 (GitHub también lo usa para ocultar lo que no se puede ver)."""


class ErrorValidacion(ErrorGitHub):
	"""422: los datos enviados no son válidos."""


class Conflicto(ErrorGitHub):
	"""409: conflicto (por ejemplo, el archivo cambió o la rama no se puede fusionar)."""


class LimiteAlcanzado(ErrorGitHub):
	"""Límite de uso primario o secundario.

	:param reinicio: momento (epoch) en que se puede volver a intentar.
	"""

	def __init__(self, mensaje_usuario: str, reinicio: float, codigo_http: int | None = None, detalle: str = "") -> None:
		super().__init__(mensaje_usuario, codigo_http, detalle)
		self.reinicio = reinicio
		self.transitorio = True

	@property
	def segundos_restantes(self) -> int:
		return max(0, int(self.reinicio - time.time()))


class ErrorGraphQL(ErrorGitHub):
	"""La consulta GraphQL devolvió ``errors``."""


# ════════════════════════════════════════════════════════════════════════════
# Utilidades puras (probadas sin red)
# ════════════════════════════════════════════════════════════════════════════


def urls_api(host: str) -> tuple[str, str]:
	"""Devuelve ``(base_rest, url_graphql)`` para un host.

	- ``github.com`` → ``https://api.github.com`` y ``https://api.github.com/graphql``.
	- GitHub Enterprise Server → ``https://HOST/api/v3`` y ``https://HOST/api/graphql``.
	- Se acepta el host con o sin esquema y con barra final.
	"""
	host = normalizar_host(host)
	if host in (HOST_GITHUB, "api.github.com"):
		return "https://api.github.com", "https://api.github.com/graphql"
	if host.endswith(".ghe.com"):
		# GitHub Enterprise Cloud con residencia de datos: api.<subdominio>.ghe.com
		return f"https://api.{host}", f"https://api.{host}/graphql"
	return f"https://{host}/api/v3", f"https://{host}/api/graphql"


def normalizar_host(host: str) -> str:
	"""Quita esquema, ruta y barras: «https://github.example.com/» → «github.example.com»."""
	host = (host or HOST_GITHUB).strip()
	if "://" in host:
		host = urlparse(host).netloc or host
	return host.strip("/").lower() or HOST_GITHUB


def url_web(host: str) -> str:
	"""Raíz web del host (para abrir en el navegador)."""
	return f"https://{normalizar_host(host)}"


_ENLACE = re.compile(r'<([^>]+)>\s*;\s*rel="([^"]+)"')


def analizar_link(cabecera: str | None) -> dict[str, str]:
	"""Convierte la cabecera ``Link`` de paginación en ``{"next": url, "last": url, ...}``."""
	if not cabecera:
		return {}
	return {rel: url for url, rel in _ENLACE.findall(cabecera)}


def numero_ultima_pagina(cabecera: str | None) -> int | None:
	"""Número de la última página según ``Link`` (para decir «página 2 de 7»)."""
	ultima = analizar_link(cabecera).get("last")
	if not ultima:
		return None
	coincidencia = re.search(r"[?&]page=(\d+)", ultima)
	return int(coincidencia.group(1)) if coincidencia else None


def fecha_iso(texto: str | None) -> datetime | None:
	"""Convierte una fecha ISO 8601 de GitHub («2024-01-02T03:04:05Z») en ``datetime`` consciente."""
	if not texto:
		return None
	try:
		return datetime.fromisoformat(texto.replace("Z", "+00:00"))
	except ValueError:
		log.debug("Fecha no reconocida: %r", texto)
		return None


def mensaje_de_error(codigo: int, cuerpo: Any, cabeceras: dict[str, str] | None = None) -> str:
	"""Frase en español para un código HTTP de GitHub, con el detalle útil del cuerpo."""
	cabeceras = cabeceras or {}
	mensaje_github = ""
	if isinstance(cuerpo, dict):
		mensaje_github = str(cuerpo.get("message") or "")
	base = {
		400: _("GitHub no ha entendido la petición."),
		401: _("La sesión no es válida o ha caducado. Vuelva a iniciar sesión."),
		403: _("GitHub ha denegado el acceso. Puede que la cuenta no tenga permiso o que al token le falten ámbitos."),
		404: _("No se ha encontrado. Puede que no exista o que la cuenta no tenga acceso."),
		405: _("Esa operación no está permitida aquí."),
		409: _("Hay un conflicto: el contenido cambió entretanto o la operación no es posible en este estado."),
		410: _("Ya no existe o la función está desactivada en este repositorio."),
		413: _("El envío es demasiado grande para GitHub."),
		422: _("GitHub ha rechazado los datos enviados."),
		451: _("No disponible por motivos legales."),
		500: _("GitHub ha tenido un error interno. Inténtelo de nuevo en unos momentos."),
		502: _("GitHub no está disponible en este momento."),
		503: _("GitHub está saturado o en mantenimiento."),
		504: _("GitHub tardó demasiado en responder."),
	}.get(codigo, _("GitHub ha respondido con el error {codigo}.").format(codigo=codigo))
	ambitos = cabeceras.get("X-Accepted-OAuth-Scopes", "")
	if codigo == 403 and ambitos:
		base += " " + _("Ámbitos necesarios: {ambitos}.").format(ambitos=ambitos)
	permisos = cabeceras.get("X-Accepted-GitHub-Permissions", "")
	if codigo == 403 and permisos:
		base += " " + _("Permisos necesarios del token: {p}.").format(p=permisos)
	sso = cabeceras.get("X-GitHub-SSO", "")
	if codigo == 403 and sso:
		url_sso = sso.split("url=", 1)[1] if "url=" in sso else ""
		base = _("La organización exige autorizar el token con su inicio de sesión único (SSO).")
		if url_sso:
			base += " " + _("Autorícelo en: {url}").format(url=url_sso)
	errores = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
	if isinstance(errores, list) and errores:
		partes = []
		for error in errores[:5]:
			if isinstance(error, dict):
				partes.append(str(error.get("message") or " ".join(f"{k}: {v}" for k, v in error.items() if k != "resource")))
			else:
				partes.append(str(error))
		base += " " + "; ".join(p for p in partes if p)
	elif mensaje_github and mensaje_github.lower() not in ("not found", "bad credentials"):
		base += f" ({mensaje_github})"
	return base


# ════════════════════════════════════════════════════════════════════════════
# Límites de uso
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class EstadoLimite:
	"""Último estado conocido del límite de uso primario."""

	limite: int | None = None
	restantes: int | None = None
	reinicio: float | None = None
	usados: int | None = None
	recurso: str = "core"

	def actualizar(self, cabeceras: Any) -> None:
		def entero(nombre: str) -> int | None:
			valor = cabeceras.get(nombre)
			try:
				return int(valor) if valor is not None else None
			except (TypeError, ValueError):
				return None

		if cabeceras.get("X-RateLimit-Limit") is None:
			return
		self.limite = entero("X-RateLimit-Limit")
		self.restantes = entero("X-RateLimit-Remaining")
		reinicio = entero("X-RateLimit-Reset")
		self.reinicio = float(reinicio) if reinicio is not None else None
		self.usados = entero("X-RateLimit-Used")
		self.recurso = str(cabeceras.get("X-RateLimit-Resource") or "core")

	def describir(self) -> str:
		if self.limite is None:
			return _("Sin datos del límite de uso todavía.")
		hora = datetime.fromtimestamp(self.reinicio).strftime("%H:%M") if self.reinicio else "?"
		return _("Quedan {r} de {l} peticiones ({recurso}); se renuevan a las {hora}.").format(
			r=self.restantes, l=self.limite, recurso=self.recurso, hora=hora
		)


# ════════════════════════════════════════════════════════════════════════════
# Respuesta
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Pagina:
	"""Una página de resultados.

	:param elementos: lista de elementos de esta página.
	:param siguiente: URL de la página siguiente (o ``""``).
	:param ultima: número de la última página si GitHub lo dice.
	:param total: ``total_count`` en búsquedas y algunos listados.
	:param incompleto: ``incomplete_results`` de las búsquedas (``True`` si GitHub
		cortó la búsqueda por tiempo; ``None`` si la respuesta no lo dice).
	"""

	elementos: list
	siguiente: str = ""
	ultima: int | None = None
	total: int | None = None
	numero: int = 1
	incompleto: bool | None = None

	@property
	def hay_mas(self) -> bool:
		return bool(self.siguiente)


@dataclass
class _EntradaCache:
	etag: str
	datos: Any
	enlace: str
	momento: float = field(default_factory=time.monotonic)


# ════════════════════════════════════════════════════════════════════════════
# Cliente
# ════════════════════════════════════════════════════════════════════════════


class ClienteGitHub:
	"""Cliente de la API REST y GraphQL de GitHub.

	:param token: token OAuth o PAT (``None`` = anónimo, 60 peticiones por hora).
	:param host: ``github.com`` o el host de GitHub Enterprise Server.
	:param agente: User-Agent (GitHub lo exige).
	:param crear_sesion: fábrica de ``requests.Session`` (por defecto, la del
		módulo de red con reintentos y proxy). Se llama una vez por hilo.
	:param usar_etag: activar las peticiones condicionales.
	"""

	def __init__(
		self,
		token: str | None = None,
		host: str = HOST_GITHUB,
		agente: str = "GithubAccesible",
		crear_sesion: Callable[[], requests.Session] | None = None,
		usar_etag: bool = True,
		tiempo: tuple[float, float] = (10.0, 60.0),
		renovar: Callable[[str | None], str | None] | None = None,
	) -> None:
		# ``renovar(token_rechazado) -> token_nuevo | None``: si GitHub rechaza el token (401)
		# y se puede renovar (tokens que caducan a las 8 horas), se pide uno nuevo y la
		# petición se repite una sola vez.
		self.host = normalizar_host(host)
		self._renovar = renovar
		self.base_rest, self.url_graphql = urls_api(self.host)
		self._token = (token or "").strip() or None
		self.agente = agente
		self._crear_sesion = crear_sesion or self._sesion_por_defecto
		self._local = threading.local()
		self.usar_etag = usar_etag
		self.tiempo = tiempo
		self._cache: dict[str, _EntradaCache] = {}
		self._candado = threading.Lock()
		self.limite = EstadoLimite()
		self.ambitos: list[str] = []
		self.intervalo_sondeo_notificaciones = 60
		self.peticiones = 0
		if self._token:
			_registrar_secreto(self._token)

	# ── Sesión ────────────────────────────────────────────────────────────────

	@staticmethod
	def _sesion_por_defecto() -> requests.Session:
		try:
			from app.core import red

			return red.crear_sesion(red.ConfiguracionRed(nombre_app="GithubAccesible", version_app=_version(), reintentos=2))
		except Exception:  # noqa: BLE001 - en pruebas o sin el módulo de red, una sesión simple
			log.debug("Sin módulo de red; se usa una sesión de requests simple.", exc_info=True)
			return requests.Session()

	def _sesion(self) -> requests.Session:
		sesion = getattr(self._local, "sesion", None)
		if sesion is None:
			sesion = self._crear_sesion()
			self._local.sesion = sesion
		return sesion

	@property
	def token(self) -> str | None:
		return self._token

	@property
	def autenticado(self) -> bool:
		return bool(self._token)

	def cambiar_token(self, token: str | None) -> None:
		"""Usa otro token a partir de ahora (por ejemplo, tras renovarlo)."""
		self._token = (token or "").strip() or None
		if self._token:
			_registrar_secreto(self._token)
		self.vaciar_cache()

	def cabeceras_base(self, aceptar: str | None = None) -> dict[str, str]:
		cabeceras = {
			"Accept": aceptar or ACEPTAR_JSON,
			"X-GitHub-Api-Version": VERSION_API if self.host == HOST_GITHUB else VERSION_API_COMPATIBLE,
			"User-Agent": self.agente,
		}
		if self._token:
			cabeceras["Authorization"] = f"Bearer {self._token}"
		return cabeceras

	def url(self, ruta: str) -> str:
		"""URL absoluta: admite rutas («/user»), URL completas de la API o plantillas «{?since}»."""
		ruta = re.sub(r"\{[^}]*\}", "", ruta or "")
		if ruta.startswith("http://") or ruta.startswith("https://"):
			return ruta
		return self.base_rest + "/" + ruta.lstrip("/")

	# ── Petición base ─────────────────────────────────────────────────────────

	def peticion(
		self,
		metodo: str,
		ruta: str,
		*,
		params: dict | None = None,
		json_datos: Any = None,
		datos: bytes | None = None,
		cabeceras: dict[str, str] | None = None,
		aceptar: str | None = None,
		condicional: bool = True,
		flujo: bool = False,
		tiempo: tuple[float, float] | None = None,
		permitir: tuple[int, ...] = (),
		_renovado: bool = False,
	) -> requests.Response:
		"""Hace la petición y devuelve la respuesta, o lanza ``ErrorGitHub``.

		:param condicional: en GET, usar ETag (si la respuesta es 304 se
			devuelve una respuesta sintética con los datos guardados).
		:param permitir: códigos de error que no deben lanzar (p. ej. 404 en
			«¿le he dado estrella?»).
		"""
		metodo = metodo.upper()
		url = self.url(ruta)
		cab = self.cabeceras_base(aceptar)
		if cabeceras:
			cab.update(cabeceras)
		clave_cache = self._clave_cache(url, params, cab.get("Accept", ""))
		entrada = None
		if metodo == "GET" and condicional and self.usar_etag and not flujo:
			with self._candado:
				entrada = self._cache.get(clave_cache)
			if entrada:
				cab["If-None-Match"] = entrada.etag
		try:
			respuesta = self._sesion().request(
				metodo, url, params=params, json=json_datos, data=datos, headers=cab,
				timeout=tiempo or self.tiempo, stream=flujo,
			)
		except requests.RequestException as error:
			raise ErrorGitHub(
				_("No se pudo conectar con GitHub. Compruebe la conexión a Internet."),
				None, f"{metodo} {url}: {type(error).__name__}: {error}",
			) from error
		self.peticiones += 1
		self.limite.actualizar(respuesta.headers)
		if "X-OAuth-Scopes" in respuesta.headers:
			self.ambitos = [a.strip() for a in respuesta.headers["X-OAuth-Scopes"].split(",") if a.strip()]
		if "X-Poll-Interval" in respuesta.headers:
			try:
				self.intervalo_sondeo_notificaciones = int(respuesta.headers["X-Poll-Interval"])
			except ValueError:
				log.debug("X-Poll-Interval no numérico: %r", respuesta.headers["X-Poll-Interval"])

		if respuesta.status_code == 304 and entrada is not None:
			respuesta._datos_cache = entrada.datos  # type: ignore[attr-defined]
			respuesta._enlace_cache = entrada.enlace  # type: ignore[attr-defined]
			return respuesta
		if respuesta.status_code == 401 and not _renovado and self._renovar is not None and self._token:
			rechazado = self._token
			nuevo = self._renovar(rechazado)
			if nuevo and nuevo != rechazado:
				log.info("Token renovado; se repite %s %s", metodo, url)
				self.cambiar_token(nuevo)
				return self.peticion(metodo, ruta, params=params, json_datos=json_datos, datos=datos, cabeceras=cabeceras,
					aceptar=aceptar, condicional=condicional, flujo=flujo, tiempo=tiempo, permitir=permitir, _renovado=True)
		if respuesta.status_code >= 400 and respuesta.status_code not in permitir:
			self._lanzar(respuesta, metodo, url)
		if metodo not in ("GET", "HEAD") and respuesta.status_code < 400:
			# Tras cambiar algo (marcar una notificación como leída, dar estrella, cerrar una
			# issue…), GitHub puede seguir contestando 304 a la lista anterior un rato y la
			# caché devolvería datos viejos. Las escrituras son pocas: se vacía entera.
			self.vaciar_cache()
		if metodo == "GET" and condicional and self.usar_etag and not flujo and respuesta.status_code == 200:
			etag = respuesta.headers.get("ETag")
			if etag:
				try:
					datos_json = respuesta.json()
				except ValueError:
					datos_json = None
				if datos_json is not None:
					with self._candado:
						if len(self._cache) >= TAMANO_CACHE_ETAG:
							# Se descarta la entrada más antigua: la caché es solo una ayuda.
							antigua = min(self._cache, key=lambda k: self._cache[k].momento)
							self._cache.pop(antigua, None)
						self._cache[clave_cache] = _EntradaCache(etag, datos_json, respuesta.headers.get("Link", ""))
		return respuesta

	@staticmethod
	def _clave_cache(url: str, params: dict | None, aceptar: str) -> str:
		parametros = json.dumps(params or {}, sort_keys=True, default=str)
		return f"{url}|{parametros}|{aceptar}"

	def vaciar_cache(self) -> None:
		with self._candado:
			self._cache.clear()

	def _lanzar(self, respuesta: requests.Response, metodo: str, url: str) -> None:
		codigo = respuesta.status_code
		try:
			cuerpo = respuesta.json()
		except ValueError:
			cuerpo = respuesta.text[:500]
		detalle = f"{metodo} {url} → HTTP {codigo}: {cuerpo.get('message') if isinstance(cuerpo, dict) else cuerpo}"
		documentacion = cuerpo.get("documentation_url", "") if isinstance(cuerpo, dict) else ""
		errores = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
		mensaje_github = (cuerpo.get("message") if isinstance(cuerpo, dict) else str(cuerpo)) or ""
		cabeceras = dict(respuesta.headers)

		# Límite secundario: Retry-After, o 403/429 que habla de «secondary rate limit» o «abuse».
		retry_after = respuesta.headers.get("Retry-After")
		if codigo in (403, 429) and (retry_after or re.search(r"secondary rate|abuse", mensaje_github, re.I)):
			espera = int(retry_after) if (retry_after or "").isdigit() else 60
			raise LimiteAlcanzado(
				_("GitHub pide esperar {s} segundos por exceso de peticiones seguidas.").format(s=espera),
				time.time() + espera, codigo, detalle,
			)
		# Límite primario agotado.
		if codigo in (403, 429) and respuesta.headers.get("X-RateLimit-Remaining") == "0":
			reinicio = float(respuesta.headers.get("X-RateLimit-Reset") or time.time() + 3600)
			hora = datetime.fromtimestamp(reinicio).strftime("%H:%M")
			raise LimiteAlcanzado(
				_("Se ha agotado el límite de peticiones a GitHub. Se renueva a las {hora}.").format(hora=hora),
				reinicio, codigo, detalle,
			)
		mensaje = mensaje_de_error(codigo, cuerpo, cabeceras)
		clase: type[ErrorGitHub] = {
			401: NoAutorizado, 403: SinPermiso, 404: NoEncontrado, 409: Conflicto, 422: ErrorValidacion,
		}.get(codigo, ErrorGitHub)
		raise clase(mensaje, codigo, detalle, errores if isinstance(errores, list) else None, documentacion)

	# ── Atajos REST ───────────────────────────────────────────────────────────

	@staticmethod
	def _json(respuesta: requests.Response) -> Any:
		datos = getattr(respuesta, "_datos_cache", None)
		if datos is not None:
			return datos
		if respuesta.status_code == 204 or not respuesta.content:
			return None
		try:
			return respuesta.json()
		except ValueError:
			return respuesta.text

	def get(self, ruta: str, params: dict | None = None, **opciones: Any) -> Any:
		return self._json(self.peticion("GET", ruta, params=params, **opciones))

	def post(self, ruta: str, datos: Any = None, **opciones: Any) -> Any:
		return self._json(self.peticion("POST", ruta, json_datos=datos, **opciones))

	def patch(self, ruta: str, datos: Any = None, **opciones: Any) -> Any:
		return self._json(self.peticion("PATCH", ruta, json_datos=datos, **opciones))

	def put(self, ruta: str, datos: Any = None, **opciones: Any) -> Any:
		return self._json(self.peticion("PUT", ruta, json_datos=datos, **opciones))

	def delete(self, ruta: str, datos: Any = None, **opciones: Any) -> Any:
		return self._json(self.peticion("DELETE", ruta, json_datos=datos, **opciones))

	def existe(self, ruta: str) -> bool:
		"""``True`` si GET devuelve 2xx, ``False`` si 404 (p. ej. «¿sigo a este usuario?»)."""
		respuesta = self.peticion("GET", ruta, permitir=(404,), condicional=False)
		return respuesta.status_code < 300

	def texto(self, ruta: str, aceptar: str, params: dict | None = None) -> str:
		"""GET que devuelve texto (diffs, contenido en bruto, HTML de Markdown)."""
		respuesta = self.peticion("GET", ruta, params=params, aceptar=aceptar, condicional=False)
		respuesta.encoding = respuesta.encoding or "utf-8"
		return respuesta.text

	def binario(self, ruta: str, aceptar: str = "application/octet-stream", params: dict | None = None) -> bytes:
		respuesta = self.peticion("GET", ruta, params=params, aceptar=aceptar, condicional=False)
		return respuesta.content

	# ── Paginación ────────────────────────────────────────────────────────────

	def pagina(self, ruta: str, params: dict | None = None, numero: int = 1, por_pagina: int = 30,
		clave: str | None = None, **opciones: Any) -> Pagina:
		"""Pide UNA página. ``clave`` extrae la lista de una respuesta envoltorio
		(``items`` en búsquedas, ``workflow_runs`` en Actions...)."""
		parametros = dict(params or {})
		parametros["per_page"] = max(1, min(POR_PAGINA_MAXIMO, int(por_pagina)))
		parametros["page"] = max(1, int(numero))
		respuesta = self.peticion("GET", ruta, params=parametros, **opciones)
		datos = self._json(respuesta)
		enlace = getattr(respuesta, "_enlace_cache", None) or respuesta.headers.get("Link", "")
		total = None
		incompleto = None
		if isinstance(datos, dict):
			total = datos.get("total_count")
			if isinstance(datos.get("incomplete_results"), bool):
				incompleto = datos["incomplete_results"]
			if clave is None:
				clave = next((k for k, v in datos.items() if isinstance(v, list)), None)
			elementos = list(datos.get(clave) or []) if clave else []
		else:
			elementos = list(datos or [])
		return Pagina(
			elementos, analizar_link(enlace).get("next", ""), numero_ultima_pagina(enlace),
			int(total) if isinstance(total, int) else None, parametros["page"], incompleto,
		)

	def paginar(
		self,
		ruta: str,
		params: dict | None = None,
		maximo: int | None = None,
		clave: str | None = None,
		por_pagina: int = POR_PAGINA_MAXIMO,
		cancelado: Callable[[], bool] | None = None,
		**opciones: Any,
	) -> Iterator[Any]:
		"""Recorre todas las páginas (siguiendo ``Link: rel="next"``) y produce los elementos.

		:param maximo: número máximo de elementos (``None`` = tope de seguridad).
		:param cancelado: función que, si devuelve ``True``, detiene el recorrido.
		"""
		numero = 1
		entregados = 0
		paginas = 0
		while True:
			if cancelado and cancelado():
				return
			pagina = self.pagina(ruta, params, numero, por_pagina, clave, **opciones)
			for elemento in pagina.elementos:
				yield elemento
				entregados += 1
				if maximo is not None and entregados >= maximo:
					return
			paginas += 1
			if not pagina.hay_mas or not pagina.elementos or paginas >= PAGINAS_MAXIMAS_POR_DEFECTO:
				return
			numero += 1

	def todos(self, ruta: str, params: dict | None = None, maximo: int | None = None, **opciones: Any) -> list:
		return list(self.paginar(ruta, params, maximo, **opciones))

	# ── GraphQL ───────────────────────────────────────────────────────────────

	def graphql(self, consulta: str, variables: dict | None = None) -> dict:
		"""Ejecuta una consulta o mutación GraphQL y devuelve ``data``.

		Lanza ``ErrorGraphQL`` si la respuesta trae ``errors`` sin ``data`` útil.
		"""
		respuesta = self.peticion(
			"POST", self.url_graphql, json_datos={"query": consulta, "variables": variables or {}}, condicional=False
		)
		cuerpo = self._json(respuesta) or {}
		errores = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
		datos = cuerpo.get("data") if isinstance(cuerpo, dict) else None
		if errores:
			mensajes = "; ".join(str(e.get("message", e)) for e in errores[:5] if isinstance(e, dict))
			tipos = {str(e.get("type", "")) for e in errores if isinstance(e, dict)}
			if "RATE_LIMITED" in tipos:
				raise LimiteAlcanzado(_("Se ha agotado el límite de consultas GraphQL de GitHub."), time.time() + 3600, 200, mensajes)
			if not datos or all(v is None for v in (datos or {}).values()):
				raise ErrorGraphQL(_("GitHub no pudo completar la consulta: {m}").format(m=mensajes), 200, mensajes, errores)
			log.warning("GraphQL devolvió avisos parciales: %s", mensajes)
		return datos or {}

	# ── Archivos ──────────────────────────────────────────────────────────────

	def descargar(
		self,
		url: str,
		destino: Path,
		aceptar: str = "application/octet-stream",
		progreso: Callable[[int, int | None], None] | None = None,
		cancelado: Callable[[], bool] | None = None,
	) -> Path:
		"""Descarga a disco en trozos (assets de releases, artefactos, archivos zip).

		Escribe primero en ``<destino>.parcial`` y lo renombra al terminar: un
		corte no deja un archivo a medias con el nombre bueno.
		"""
		destino = Path(destino)
		destino.parent.mkdir(parents=True, exist_ok=True)
		temporal = destino.with_name(destino.name + ".parcial")
		respuesta = self.peticion("GET", url, aceptar=aceptar, condicional=False, flujo=True, tiempo=(15.0, 120.0))
		total = int(respuesta.headers.get("Content-Length") or 0) or None
		hecho = 0
		try:
			with open(temporal, "wb") as archivo:
				for trozo in respuesta.iter_content(64 * 1024):
					if cancelado and cancelado():
						raise ErrorGitHub(_("Descarga cancelada."), None, "cancelada por el usuario")
					archivo.write(trozo)
					hecho += len(trozo)
					if progreso:
						progreso(hecho, total)
			temporal.replace(destino)
		finally:
			respuesta.close()
			if temporal.exists():
				try:
					temporal.unlink()
				except OSError:
					log.debug("No se pudo borrar %s", temporal, exc_info=True)
		return destino

	def subir(self, url_subida: str, archivo: Path, nombre: str | None = None, etiqueta: str = "",
		tipo: str = "application/octet-stream") -> Any:
		"""Sube un asset a una release (``upload_url`` de la release)."""
		archivo = Path(archivo)
		url = re.sub(r"\{[^}]*\}", "", url_subida)
		params = {"name": nombre or archivo.name}
		if etiqueta:
			params["label"] = etiqueta
		datos = archivo.read_bytes()
		respuesta = self.peticion(
			"POST", url, params=params, datos=datos, cabeceras={"Content-Type": tipo}, condicional=False,
			tiempo=(15.0, 600.0),
		)
		return self._json(respuesta)


def _registrar_secreto(valor: str) -> None:
	"""Pide al registro que tape este valor si alguna vez aparece en un mensaje."""
	try:
		from app.core import registro

		registro.registrar_secreto(valor)
	except Exception:  # noqa: BLE001 - sin el registro profesional no hay nada que tapar
		log.debug("No se pudo registrar el secreto en el sistema de registro.", exc_info=True)


def _version() -> str:
	try:
		from app.core.version import APP_VERSION

		return APP_VERSION
	except Exception:  # noqa: BLE001
		return "0"


def unir_url(base: str, relativa: str) -> str:
	return urljoin(base.rstrip("/") + "/", relativa.lstrip("/"))
