"""Wiki de un repositorio de GitHub: leer, crear, editar, renombrar y borrar páginas (sin wx).

Por qué así:

- La API de GitHub (REST y GraphQL) NO da acceso a la wiki: solo dice si está
  activada (``has_wiki``). Cada wiki es, en realidad, un repositorio git aparte
  en ``https://<host>/<dueño>/<repo>.wiki.git`` con un archivo por página
  (``Home.md``, ``Primeros-pasos.md``...). Es lo que hacen también los clientes
  de escritorio: clonarla y trabajar con git.
- Se guarda una copia en ``data/cache/wikis/<host>/<dueño>__<repo>``. Antes de
  leer o cambiar se trae lo último de GitHub y se deja la copia IGUAL que el
  remoto (``reset --hard``): es una caché nuestra, nunca la carpeta de trabajo
  de la persona, así que no se pierde nada suyo.
- Cada cambio es un commit que se envía al momento. Si el envío falla (sin
  permiso, sin red), se deshace el commit local para que la caché no se quede
  con un cambio que GitHub no tiene.
- Una wiki activada pero sin ninguna página NO existe todavía como repositorio
  (git contesta «not found»): GitHub solo la crea al guardar la primera página
  desde la web. Se avisa con ``WikiSinPaginas`` para ofrecer el navegador.
- Los enlaces internos de Gollum (``[[Texto|Página]]``) se convierten a enlaces
  Markdown normales para que el visor los muestre como enlaces.
"""

from __future__ import annotations

import builtins
import logging
import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from app.services import git_local
from app.services.git_local import Commit, ErrorGit

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Formatos de página que admite la wiki de GitHub (extensión → nombre del formato).
FORMATOS: dict[str, str] = {
	".md": "Markdown", ".markdown": "Markdown", ".mdown": "Markdown", ".mkdn": "Markdown", ".mkd": "Markdown",
	".mediawiki": "MediaWiki", ".wiki": "MediaWiki", ".textile": "Textile", ".rdoc": "RDoc", ".org": "Org",
	".creole": "Creole", ".rst": "reStructuredText", ".rest": "reStructuredText", ".asciidoc": "AsciiDoc",
	".adoc": "AsciiDoc", ".asc": "AsciiDoc", ".pod": "Pod",
}
#: Páginas especiales: la portada y los bloques que GitHub pone a un lado y al pie de todas.
PORTADA = "Home"
ESPECIALES = {"_sidebar": N_("Barra lateral"), "_footer": N_("Pie de página")}
#: Caracteres que GitHub no admite en el nombre de una página (los cambia por guiones).
_PROHIBIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class ErrorWiki(Exception):
	"""Fallo al manejar la wiki, con mensaje para la persona."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje_usuario = mensaje

	def __str__(self) -> str:
		return self.mensaje_usuario


class WikiSinPaginas(ErrorWiki):
	"""La wiki está activada pero aún no tiene páginas (o no hay permiso para verla)."""


@dataclass(frozen=True)
class PaginaWiki:
	"""Una página: su archivo dentro del repositorio de la wiki y lo que se muestra."""

	archivo: str
	titulo: str
	formato: str
	tamano: int
	especial: str = ""

	@property
	def es_markdown(self) -> bool:
		return self.formato == "Markdown"

	@property
	def nombre(self) -> str:
		"""Nombre de la página en las direcciones de GitHub (el archivo sin extensión ni carpeta)."""
		return Path(self.archivo).stem


# ════════════════════════════════════════════════════════════════════════════
# Funciones puras (se prueban sin red ni git)
# ════════════════════════════════════════════════════════════════════════════


def url_clonado(host: str, repositorio: str) -> str:
	"""Dirección git de la wiki: ``https://github.com/ana/proyecto.wiki.git``."""
	return f"https://{host or 'github.com'}/{repositorio.strip('/')}.wiki.git"


def url_web(host: str, repositorio: str, nombre: str = "") -> str:
	"""Página de la wiki en la web (sin nombre o con «Home», la portada)."""
	base = f"https://{host or 'github.com'}/{repositorio.strip('/')}/wiki"
	if not nombre or nombre == PORTADA:
		return base
	return f"{base}/{quote(nombre, safe='-_.()')}"


def url_nueva_pagina(host: str, repositorio: str) -> str:
	return f"https://{host or 'github.com'}/{repositorio.strip('/')}/wiki/_new"


def titulo_de_archivo(archivo: str) -> str:
	"""«Primeros-pasos.md» → «Primeros pasos» (GitHub muestra los guiones como espacios)."""
	nombre = Path(archivo).stem
	if nombre.casefold() in ESPECIALES:
		return _(ESPECIALES[nombre.casefold()])
	return nombre.replace("-", " ").strip() or nombre


def archivo_para_titulo(titulo: str, extension: str = ".md") -> str:
	"""Nombre de archivo que GitHub daría a una página con ese título («Mi página» → «Mi-página.md»)."""
	nombre = _PROHIBIDOS.sub("-", (titulo or "").strip())
	nombre = re.sub(r"\s+", "-", nombre).strip("-.")
	if not nombre:
		raise ErrorWiki(_("Escriba el título de la página."))
	return nombre + (extension if extension.startswith(".") else f".{extension}")


def es_pagina(ruta: Path) -> bool:
	return ruta.suffix.lower() in FORMATOS


def ordenar_paginas(paginas: list[PaginaWiki]) -> list[PaginaWiki]:
	"""La portada primero, luego las páginas por orden alfabético y al final las especiales."""
	def clave(p: PaginaWiki) -> tuple[int, str]:
		if p.nombre == PORTADA and "/" not in p.archivo:
			return (0, "")
		return (2 if p.especial else 1, p.titulo.casefold())

	return sorted(paginas, key=clave)


def listar_paginas(carpeta: Path) -> list[PaginaWiki]:
	"""Páginas de una copia de la wiki (se ignoran ``.git`` y los archivos que no son páginas)."""
	carpeta = Path(carpeta)
	paginas = []
	for ruta in carpeta.rglob("*"):
		relativa = ruta.relative_to(carpeta)
		if ".git" in relativa.parts or not ruta.is_file() or not es_pagina(ruta):
			continue
		archivo = relativa.as_posix()
		especial = ruta.stem.casefold() if ruta.stem.casefold() in ESPECIALES else ""
		paginas.append(PaginaWiki(archivo, titulo_de_archivo(archivo), FORMATOS[ruta.suffix.lower()], ruta.stat().st_size, especial))
	return ordenar_paginas(paginas)


_ENLACE_GOLLUM = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_IMAGEN = re.compile(r"\.(png|jpe?g|gif|svg|webp|bmp)$", re.I)


def convertir_enlaces(texto: str, host: str, repositorio: str) -> str:
	"""``[[Página]]`` y ``[[Texto|Página]]`` → enlaces Markdown a la página de la wiki.

	Las imágenes (``[[imagen.png]]``) se dejan como texto alternativo con su
	dirección: el lector las anuncia y se pueden abrir.
	"""
	def sustituir(coincidencia: re.Match) -> str:
		contenido = coincidencia.group(1).strip()
		texto_enlace, _barra, destino = contenido.partition("|")
		if not destino:
			texto_enlace, destino = contenido, contenido
		texto_enlace, destino = texto_enlace.strip(), destino.strip()
		if destino.startswith(("http://", "https://")):
			return f"[{texto_enlace}]({destino})"
		if _IMAGEN.search(destino.split("|", 1)[0]):
			ruta = f"https://{host or 'github.com'}/{repositorio}/wiki/{quote(destino, safe='/-_.()')}"
			return f"[{_('Imagen')}: {texto_enlace}]({ruta})"
		nombre, _ancla, seccion = destino.partition("#")
		direccion = url_web(host, repositorio, re.sub(r"\s+", "-", nombre.strip()))
		if seccion:
			direccion += "#" + quote(seccion.strip().lower().replace(" ", "-"), safe="-_")
		return f"[{texto_enlace}]({direccion})"

	return _ENLACE_GOLLUM.sub(sustituir, texto or "")


def pagina_de_enlace(direccion: str, host: str, repositorio: str) -> str | None:
	"""Si ``direccion`` es una página de ESTA wiki, su nombre («Home» para la portada); si no, ``None``."""
	partes = urlsplit(direccion or "")
	if partes.scheme not in ("http", "https") or partes.netloc.casefold() != (host or "github.com").casefold():
		return None
	prefijo = f"/{repositorio.strip('/')}/wiki".casefold()
	ruta = unquote(partes.path).rstrip("/")
	if ruta.casefold() == prefijo:
		return PORTADA
	if not ruta.casefold().startswith(prefijo + "/"):
		return None
	nombre = ruta[len(prefijo) + 1:]
	if not nombre or "/" in nombre or nombre.startswith("_") or _IMAGEN.search(nombre):
		return None
	return nombre


def buscar_pagina(paginas: list[PaginaWiki], nombre: str) -> PaginaWiki | None:
	"""Página por su nombre de enlace, sin distinguir mayúsculas ni guiones de espacios (como GitHub)."""
	buscado = re.sub(r"[\s-]+", "-", (nombre or "").strip()).casefold()
	return next((p for p in paginas if re.sub(r"[\s-]+", "-", p.nombre).casefold() == buscado), None)


def documento_para_visor(pagina: PaginaWiki, texto: str, host: str, repositorio: str) -> str:
	"""Texto que se enseña en el visor: Markdown con enlaces convertidos, u otro formato tal cual.

	Los formatos que no son Markdown (MediaWiki, AsciiDoc...) se muestran en un
	bloque de código para que el visor no los interprete mal.
	"""
	if pagina.es_markdown:
		cuerpo = convertir_enlaces(texto, host, repositorio)
		if not re.match(r"\s*#\s", cuerpo):
			cuerpo = f"# {pagina.titulo}\n\n{cuerpo}"
		return cuerpo
	valla = "~~~~" if "```" in texto else "```"
	aviso = _("Página en formato {f}: se muestra el texto original.").format(f=pagina.formato)
	return f"# {pagina.titulo}\n\n{aviso}\n\n{valla}\n{texto}\n{valla}\n"


def es_error_no_encontrada(error: ErrorGit) -> bool:
	"""Git dice que el repositorio de la wiki no existe (wiki vacía) o que no tenemos acceso."""
	texto = f"{error.salida}\n{error.mensaje_usuario}"
	return bool(re.search(r"not found|does not exist|does not appear to be a git repository", texto, re.I))


# ════════════════════════════════════════════════════════════════════════════
# Copia local de la wiki
# ════════════════════════════════════════════════════════════════════════════

#: Un candado por carpeta: dos secciones (o dos ventanas) no tocan la misma copia a la vez.
_CANDADOS: dict[str, threading.Lock] = {}
_CANDADO_GENERAL = threading.Lock()


def _candado(carpeta: Path) -> threading.Lock:
	clave = str(carpeta).casefold()
	with _CANDADO_GENERAL:
		return _CANDADOS.setdefault(clave, threading.Lock())


def carpeta_cache(base: Path, host: str, repositorio: str) -> Path:
	"""``<base>/<host>/<dueño>__<repo>`` con nombres válidos en Windows."""
	from app.core.descargas import nombre_seguro

	dueno, _barra, nombre = repositorio.strip("/").partition("/")
	return Path(base) / nombre_seguro(host or "github.com") / nombre_seguro(f"{dueno}__{nombre}")


class WikiLocal:
	"""Copia de trabajo (caché) de la wiki de un repositorio.

	:param carpeta: dónde se guarda la copia (``carpeta_cache``).
	:param host: «github.com» o el de GitHub Enterprise.
	:param repositorio: «dueño/repo».
	:param token: función que devuelve el token para HTTPS (o ``None``).
	:param identidad: ``(nombre, correo)`` para los commits si git no tiene
		los suyos configurados (se pone solo en esta copia, nunca global).
	:param url_remoto: otra dirección git (las pruebas usan un repositorio local).
	"""

	def __init__(self, carpeta: Path, host: str, repositorio: str, token: Callable[[], str | None] | None = None,
		identidad: tuple[str, str] | None = None, url_remoto: str = "") -> None:
		self.carpeta = Path(carpeta)
		self.host = host or "github.com"
		self.repositorio = repositorio.strip("/")
		self._token = token or (lambda: None)
		self.identidad = identidad
		self._url_remoto = url_remoto
		self.repo = git_local.RepositorioLocal(self.carpeta, self._token)

	@property
	def url(self) -> str:
		return self._url_remoto or url_clonado(self.host, self.repositorio)

	def existe_copia(self) -> bool:
		return (self.carpeta / ".git").is_dir()

	# ── Sincronizar ──────────────────────────────────────────────────────────

	def sincronizar(self) -> list[PaginaWiki]:
		"""Trae lo último de GitHub (clona la primera vez) y devuelve las páginas."""
		with _candado(self.carpeta):
			self._sincronizar()
			return listar_paginas(self.carpeta)

	def _sincronizar(self) -> None:
		if not self.existe_copia():
			self._clonar()
			return
		try:
			self.repo.git_red("fetch", "--prune", "origin")
		except ErrorGit as error:
			if es_error_no_encontrada(error):
				raise WikiSinPaginas(self._texto_sin_paginas()) from error
			raise ErrorWiki(_("No se pudo traer la wiki de GitHub: {m}").format(m=error.mensaje_usuario)) from error
		self.repo.git("reset", "--hard", self._rama_remota())
		self.repo.git("clean", "-fdq")

	def _clonar(self) -> None:
		if self.carpeta.exists():
			shutil.rmtree(self.carpeta, ignore_errors=True)  # copia a medias de un intento anterior
		self.carpeta.parent.mkdir(parents=True, exist_ok=True)
		try:
			git_local.clonar(self.url, self.carpeta, token=self._token(), submodulos=False)
		except ErrorGit as error:
			shutil.rmtree(self.carpeta, ignore_errors=True)
			if es_error_no_encontrada(error):
				raise WikiSinPaginas(self._texto_sin_paginas()) from error
			raise ErrorWiki(_("No se pudo descargar la wiki: {m}").format(m=error.mensaje_usuario)) from error
		self._poner_identidad()

	def _texto_sin_paginas(self) -> str:
		return _(
			"La wiki de {r} todavía no tiene páginas (o no tiene permiso para verla). GitHub solo crea la wiki "
			"al guardar la primera página desde la web: use «Crear la primera página en el navegador» y, después, "
			"actualice con F5 para trabajar con ella desde aquí."
		).format(r=self.repositorio)

	def _poner_identidad(self) -> None:
		"""Nombre y correo solo para esta copia si git no los tiene (si no, el commit fallaría)."""
		if not self.identidad:
			return
		try:
			tiene_nombre = bool(self.repo.git("config", "--get", "user.name", aceptar_codigos=(0, 1)).strip())
			tiene_correo = bool(self.repo.git("config", "--get", "user.email", aceptar_codigos=(0, 1)).strip())
			if not tiene_nombre:
				self.repo.git("config", "user.name", self.identidad[0])
			if not tiene_correo:
				self.repo.git("config", "user.email", self.identidad[1])
		except ErrorGit:
			log.info("No se pudo configurar la identidad de la copia de la wiki", exc_info=True)

	def _rama_remota(self) -> str:
		try:
			referencia = self.repo.git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
			if referencia:
				return referencia
		except ErrorGit:
			pass
		rama = self.repo.rama_actual().strip() or "master"
		return f"origin/{rama}"

	# ── Leer ─────────────────────────────────────────────────────────────────

	def paginas(self) -> list[PaginaWiki]:
		return listar_paginas(self.carpeta) if self.existe_copia() else []

	def _ruta(self, archivo: str) -> Path:
		ruta = (self.carpeta / archivo).resolve()
		if self.carpeta.resolve() not in ruta.parents:
			raise ErrorWiki(_("Ruta de página no válida: {a}").format(a=archivo))
		return ruta

	def leer(self, archivo: str) -> str:
		return self._ruta(archivo).read_text(encoding="utf-8", errors="replace")

	def historial(self, archivo: str, cantidad: int = 100) -> list[Commit]:
		with _candado(self.carpeta):
			return self.repo.historial(cantidad, ruta=archivo)

	def version(self, archivo: str, sha: str) -> str:
		"""Texto de la página tal como quedó en ese commit."""
		return self.repo.git("show", f"{sha}:{archivo}")

	def diferencias(self, archivo: str, sha: str) -> str:
		return self.repo.diferencias_commit(sha, archivo)

	# ── Cambiar (cada cambio es un commit que se envía al momento) ───────────

	def guardar(self, archivo: str, texto: str, mensaje: str, nueva: bool = False) -> PaginaWiki:
		"""Crea o sustituye una página y la envía a GitHub."""
		with _candado(self.carpeta):
			self._sincronizar()
			ruta = self._ruta(archivo)
			if nueva and ruta.exists():
				raise ErrorWiki(_("Ya existe una página llamada «{t}».").format(t=titulo_de_archivo(archivo)))
			ruta.parent.mkdir(parents=True, exist_ok=True)
			# Se respetan los saltos de línea del archivo que había (GitHub los guarda tal cual).
			salto = "\r\n" if ruta.exists() and b"\r\n" in ruta.read_bytes() else "\n"
			contenido = (texto or "").replace("\r\n", "\n")
			ruta.write_bytes(contenido.replace("\n", salto).encode("utf-8"))
			self.repo.git("add", "--", archivo)
			if not self.repo.git("status", "--porcelain", "--", archivo).strip():
				raise ErrorWiki(_("La página no ha cambiado: no hay nada que guardar."))
			self._confirmar_y_enviar(mensaje or (_("Crear {t}") if nueva else _("Actualizar {t}")).format(
				t=titulo_de_archivo(archivo)))
			return next(p for p in listar_paginas(self.carpeta) if p.archivo == archivo)

	def borrar(self, archivo: str, mensaje: str = "") -> None:
		with _candado(self.carpeta):
			self._sincronizar()
			self._ruta(archivo)
			self.repo.git("rm", "-q", "--", archivo)
			self._confirmar_y_enviar(mensaje or _("Borrar {t}").format(t=titulo_de_archivo(archivo)))

	def renombrar(self, archivo: str, titulo_nuevo: str, mensaje: str = "") -> str:
		"""Cambia el título (y el archivo) de una página. Devuelve el archivo nuevo."""
		with _candado(self.carpeta):
			self._sincronizar()
			carpeta = str(Path(archivo).parent.as_posix())
			nuevo = archivo_para_titulo(titulo_nuevo, Path(archivo).suffix or ".md")
			if carpeta not in ("", "."):
				nuevo = f"{carpeta}/{nuevo}"
			if nuevo == archivo:
				raise ErrorWiki(_("El título nuevo es igual al actual."))
			if self._ruta(nuevo).exists() and nuevo.casefold() != archivo.casefold():
				raise ErrorWiki(_("Ya existe una página llamada «{t}».").format(t=titulo_nuevo.strip()))
			self.repo.git("mv", "--", archivo, nuevo)
			self._confirmar_y_enviar(mensaje or _("Renombrar {a} a {n}").format(a=titulo_de_archivo(archivo),
				n=titulo_de_archivo(nuevo)))
			return nuevo

	def _confirmar_y_enviar(self, mensaje: str) -> None:
		self._poner_identidad()
		self.repo.confirmar(mensaje)
		try:
			self.repo.git_red("push", "origin", "HEAD")
		except ErrorGit as error:
			# GitHub no lo tiene: se deshace el commit para que la caché no mienta.
			try:
				self.repo.git("reset", "--hard", self._rama_remota())
			except ErrorGit:
				log.warning("No se pudo deshacer el commit local de la wiki", exc_info=True)
			raise ErrorWiki(_("No se pudo enviar el cambio a la wiki: {m}").format(m=error.mensaje_usuario)) from error

	def olvidar(self) -> None:
		"""Borra la copia local (la próxima vez se vuelve a descargar entera)."""
		with _candado(self.carpeta):
			shutil.rmtree(self.carpeta, ignore_errors=True)
