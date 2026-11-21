"""Git local: detectar git, ejecutarlo de forma robusta y analizar su salida (sin wx).

Por qué así:

- Se invoca el ``git`` instalado (Git for Windows) con ``subprocess``: es lo
  que la persona ya usa en consola, respeta su configuración (nombre, correo,
  firma GPG, ganchos, LFS) y no añade dependencias nativas.
- Salidas **porcelain v2 con -z** para analizar sin ambigüedad (nombres con
  espacios, acentos o saltos de línea).
- ``LC_ALL=C`` y ``LANGUAGE=C`` en lo que se analiza (los mensajes traducidos
  romperían el análisis); los mensajes para la persona se toman tal cual.
- ``GIT_TERMINAL_PROMPT=0``: git nunca se queda esperando una contraseña en
  una consola invisible. Para HTTPS se pasa el token por ``GIT_ASKPASS``
  (un script temporal que lo lee de una variable de entorno del proceso hijo),
  sin escribirlo jamás en ``.git/config`` ni en disco.
- ``CREATE_NO_WINDOW``: no aparecen consolas negras.
"""

from __future__ import annotations

import builtins
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

TIEMPO_POR_DEFECTO = 120
TIEMPO_RED = 1800


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorGit(Exception):
	"""Fallo de una orden git, con la salida de error para mostrar."""

	def __init__(self, mensaje: str, orden: list[str] | None = None, codigo: int | None = None, salida: str = "") -> None:
		super().__init__(mensaje)
		self.mensaje_usuario = mensaje
		self.orden = orden or []
		self.codigo = codigo
		self.salida = salida

	def __str__(self) -> str:
		return self.mensaje_usuario


class GitNoInstalado(ErrorGit):
	"""No se encuentra el ejecutable de git."""


# ════════════════════════════════════════════════════════════════════════════
# Detección
# ════════════════════════════════════════════════════════════════════════════

_RUTA_GIT: str | None = None
_candado_ruta = threading.Lock()


def buscar_git(configurada: str = "") -> str | None:
	"""Ruta de git: la configurada, la del PATH o las rutas típicas de Git for Windows."""
	global _RUTA_GIT
	if configurada and os.path.isfile(configurada):
		return configurada
	with _candado_ruta:
		if _RUTA_GIT and os.path.isfile(_RUTA_GIT):
			return _RUTA_GIT
		candidatos = [shutil.which("git")]
		for base in ("%ProgramFiles%", "%ProgramFiles(x86)%", "%LOCALAPPDATA%\\Programs", "%USERPROFILE%\\scoop\\shims"):
			candidatos.append(os.path.expandvars(base + r"\Git\cmd\git.exe"))
		candidatos.append(os.path.expandvars(r"%USERPROFILE%\scoop\shims\git.exe"))
		for candidato in candidatos:
			if candidato and os.path.isfile(candidato):
				_RUTA_GIT = candidato
				return candidato
	return None


def establecer_ruta_git(ruta: str) -> None:
	"""Fija la ruta de git elegida en Preferencias (vacía = detectar)."""
	global _RUTA_GIT
	with _candado_ruta:
		_RUTA_GIT = ruta if ruta and os.path.isfile(ruta) else None


def git_disponible() -> bool:
	return buscar_git() is not None


def version_git() -> str:
	try:
		return ejecutar(["--version"], tiempo=15).strip()
	except ErrorGit:
		return ""


# ════════════════════════════════════════════════════════════════════════════
# Ejecución
# ════════════════════════════════════════════════════════════════════════════


def _opciones_proceso() -> dict:
	if sys.platform == "win32":
		return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
	return {}


def entorno_git(token: str | None = None, usuario: str = "x-access-token", analizable: bool = True) -> tuple[dict, list[Path]]:
	"""Entorno para el proceso hijo y archivos temporales que hay que borrar luego.

	Con ``token``, se crea un ``askpass`` temporal (en ``data/temp``) que
	devuelve usuario y token leyéndolos de variables de entorno del propio
	proceso git: el token nunca se escribe en disco ni en la línea de órdenes.
	"""
	entorno = dict(os.environ)
	entorno["GIT_TERMINAL_PROMPT"] = "0"
	entorno["GCM_INTERACTIVE"] = "never" if token else entorno.get("GCM_INTERACTIVE", "auto")
	entorno["GIT_PAGER"] = "cat"
	entorno["PAGER"] = "cat"
	# git ejecuta el editor con su propio sh (también Git for Windows): «true» acepta el mensaje propuesto.
	entorno["GIT_EDITOR"] = "true"
	entorno["GIT_SEQUENCE_EDITOR"] = "true"
	if analizable:
		entorno["LC_ALL"] = "C"
		entorno["LANGUAGE"] = "C"
	temporales: list[Path] = []
	if token:
		carpeta = _carpeta_temporal()
		descriptor, nombre = tempfile.mkstemp(prefix="askpass_", suffix=".bat", dir=carpeta)
		os.close(descriptor)
		ruta = Path(nombre)
		# El script mira si git pide el usuario («Username») o la contraseña.
		ruta.write_text(
			"@echo off\r\n"
			"echo %~1 | findstr /i \"username\" >nul && (echo %GA_USUARIO%& exit /b 0)\r\n"
			"echo %GA_TOKEN%\r\n",
			encoding="utf-8",
		)
		temporales.append(ruta)
		entorno["GIT_ASKPASS"] = str(ruta)
		entorno["SSH_ASKPASS"] = str(ruta)
		entorno["GA_USUARIO"] = usuario
		entorno["GA_TOKEN"] = token
		# Que ningún ayudante de credenciales guarde ni sirva otra credencial.
		entorno["GIT_CONFIG_COUNT"] = "1"
		entorno["GIT_CONFIG_KEY_0"] = "credential.helper"
		entorno["GIT_CONFIG_VALUE_0"] = ""
	return entorno, temporales


def _carpeta_temporal() -> Path:
	try:
		from app.core import paths

		return paths.ruta_temporales()
	except Exception:  # noqa: BLE001 - en pruebas sin la app
		carpeta = Path(tempfile.gettempdir()) / "githubaccesible"
		carpeta.mkdir(parents=True, exist_ok=True)
		return carpeta


def _mensaje_error(salida: str, orden: list[str]) -> str:
	texto = (salida or "").strip()
	lineas = [linea for linea in texto.splitlines() if linea.strip() and not linea.startswith("hint:")]
	resumen = "\n".join(lineas[-8:])
	pistas = [
		(r"Authentication failed|could not read Username|terminal prompts disabled",
			_("Git no pudo autenticarse. Inicie sesión en la aplicación o configure sus credenciales de Git.")),
		(r"not a git repository", _("La carpeta no es un repositorio de Git.")),
		(r"CONFLICT|Automatic merge failed|fix conflicts", _("Hay conflictos que resolver antes de continuar.")),
		(r"non-fast-forward|\[rejected\]|fetch first", _("El remoto tiene cambios que usted no tiene. Traiga los cambios (pull) antes de enviar.")),
		(r"Please tell me who you are|empty ident", _("Git no sabe su nombre ni su correo. Configúrelos en Git, Configuración.")),
		(r"nothing to commit", _("No hay cambios preparados para confirmar.")),
		(r"Your local changes .* would be overwritten", _("Tiene cambios sin confirmar que se perderían. Confírmelos o guárdelos en un stash antes.")),
		(r"Could not resolve host|unable to access", _("No se pudo conectar con el servidor remoto.")),
		(r"Permission denied \(publickey\)", _("El servidor ha rechazado la clave SSH.")),
		(r"already exists and is not an empty directory", _("La carpeta de destino ya existe y no está vacía.")),
	]
	for patron, explicacion in pistas:
		if re.search(patron, texto, re.I):
			return f"{explicacion}\n\n{resumen}" if resumen else explicacion
	return resumen or _("Git terminó con un error (orden: git {orden}).").format(orden=" ".join(orden[:3]))


def ejecutar(
	argumentos: list[str],
	carpeta: str | Path | None = None,
	*,
	token: str | None = None,
	usuario_token: str = "x-access-token",
	entrada: str | None = None,
	tiempo: float = TIEMPO_POR_DEFECTO,
	analizable: bool = True,
	aceptar_codigos: Iterable[int] = (0,),
	binario: bool = False,
	al_linea: Callable[[str], None] | None = None,
	cancelado: Callable[[], bool] | None = None,
) -> str:
	"""Ejecuta ``git <argumentos>`` y devuelve la salida estándar.

	:param al_linea: si se indica, se lee la salida de error línea a línea (progreso
		de clone, fetch, push) y se entrega a esta función; útil con ``--progress``.
	:raises GitNoInstalado: si no hay git.
	:raises ErrorGit: si el código de salida no está en ``aceptar_codigos``.
	"""
	git = buscar_git()
	if not git:
		raise GitNoInstalado(_("Git no está instalado. Instale Git for Windows desde https://git-scm.com o indique su ruta en Preferencias."))
	orden = [git, *argumentos]
	entorno, temporales = entorno_git(token, usuario_token, analizable)
	cwd = str(carpeta) if carpeta else None
	log.debug("git %s (en %s)", " ".join(argumentos[:6]), cwd or ".")
	try:
		if al_linea is None:
			try:
				resultado = subprocess.run(
					orden, cwd=cwd, input=entrada.encode("utf-8") if entrada is not None else None,
					capture_output=True, timeout=tiempo, env=entorno, **_opciones_proceso(),
				)
			except subprocess.TimeoutExpired as error:
				raise ErrorGit(_("Git tardó demasiado (más de {s} segundos).").format(s=int(tiempo)), argumentos) from error
			except OSError as error:
				raise ErrorGit(_("No se pudo ejecutar git: {e}").format(e=error), argumentos) from error
			salida = resultado.stdout if binario else resultado.stdout.decode("utf-8", errors="replace")
			errores = resultado.stderr.decode("utf-8", errors="replace")
			codigo = resultado.returncode
		else:
			salida, errores, codigo = _ejecutar_con_progreso(orden, cwd, entorno, tiempo, al_linea, cancelado, argumentos)
	finally:
		for temporal in temporales:
			try:
				temporal.unlink()
			except OSError:
				log.debug("No se pudo borrar %s", temporal, exc_info=True)
	if codigo not in tuple(aceptar_codigos):
		texto = (errores or "") + ("\n" + salida if isinstance(salida, str) and salida.strip() else "")
		log.info("git %s terminó con código %s: %s", " ".join(argumentos[:3]), codigo, errores.strip()[-500:])
		raise ErrorGit(_mensaje_error(texto, argumentos), argumentos, codigo, texto)
	return salida


def _ejecutar_con_progreso(orden, cwd, entorno, tiempo, al_linea, cancelado, argumentos):
	import time

	try:
		proceso = subprocess.Popen(
			orden, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno, **_opciones_proceso()
		)
	except OSError as error:
		raise ErrorGit(_("No se pudo ejecutar git: {e}").format(e=error), argumentos) from error
	trozos_salida: list[bytes] = []

	def leer_salida() -> None:
		for bloque in iter(lambda: proceso.stdout.read(4096), b""):
			trozos_salida.append(bloque)

	hilo = threading.Thread(target=leer_salida, daemon=True, name="git-salida")
	hilo.start()
	errores: list[str] = []
	inicio = time.monotonic()
	pendiente = b""
	while True:
		if cancelado and cancelado():
			proceso.kill()
			raise ErrorGit(_("Operación cancelada."), argumentos)
		if time.monotonic() - inicio > tiempo:
			proceso.kill()
			raise ErrorGit(_("Git tardó demasiado (más de {s} segundos).").format(s=int(tiempo)), argumentos)
		bloque = proceso.stderr.read1(1024) if hasattr(proceso.stderr, "read1") else proceso.stderr.read(1024)
		if not bloque:
			break
		pendiente += bloque
		# git separa el progreso con \r (misma línea) o \n.
		partes = re.split(rb"[\r\n]", pendiente)
		pendiente = partes.pop()
		for parte in partes:
			linea = parte.decode("utf-8", errors="replace").strip()
			if linea:
				errores.append(linea)
				al_linea(linea)
	if pendiente.strip():
		linea = pendiente.decode("utf-8", errors="replace").strip()
		errores.append(linea)
		al_linea(linea)
	proceso.wait()
	hilo.join(5)
	return b"".join(trozos_salida).decode("utf-8", errors="replace"), "\n".join(errores[-200:]), proceso.returncode


# ════════════════════════════════════════════════════════════════════════════
# Estado (git status --porcelain=v2 -z --branch)
# ════════════════════════════════════════════════════════════════════════════

ESTADOS = {
	".": "",
	"M": "modificado",
	"T": "cambio de tipo",
	"A": "añadido",
	"D": "eliminado",
	"R": "renombrado",
	"C": "copiado",
	"U": "en conflicto",
	"?": "sin seguimiento",
	"!": "ignorado",
}


@dataclass
class ArchivoEstado:
	"""Un archivo con cambios.

	:param indice: estado en el área de preparación (staged): letra de ``ESTADOS``.
	:param arbol: estado en el directorio de trabajo.
	"""

	ruta: str
	indice: str = "."
	arbol: str = "."
	ruta_original: str = ""
	conflicto: bool = False
	submodulo: bool = False

	@property
	def preparado(self) -> bool:
		return self.indice not in (".", "?", "!") and not self.conflicto

	@property
	def sin_preparar(self) -> bool:
		return self.arbol != "." or self.indice == "?"

	@property
	def sin_seguimiento(self) -> bool:
		return self.indice == "?"

	def describir_indice(self) -> str:
		if self.conflicto:
			return _("en conflicto")
		return _(ESTADOS.get(self.indice, self.indice)) if self.indice not in (".", "?") else ""

	def describir_arbol(self) -> str:
		if self.conflicto:
			return _("en conflicto")
		if self.indice == "?":
			return _("sin seguimiento")
		return _(ESTADOS.get(self.arbol, self.arbol)) if self.arbol != "." else ""

	def describir(self) -> str:
		partes = []
		if self.conflicto:
			return _("En conflicto")
		if self.indice == "?":
			return _("Nuevo, sin seguimiento")
		if self.indice not in ("."):
			partes.append(_("preparado: {e}").format(e=_(ESTADOS.get(self.indice, self.indice))))
		if self.arbol != ".":
			partes.append(_("sin preparar: {e}").format(e=_(ESTADOS.get(self.arbol, self.arbol))))
		texto = ", ".join(partes)
		if self.ruta_original:
			texto += " " + _("(antes {r})").format(r=self.ruta_original)
		return texto[:1].upper() + texto[1:] if texto else ""


@dataclass
class EstadoRepositorio:
	rama: str = ""
	commit: str = ""
	rama_remota: str = ""
	adelante: int = 0
	atras: int = 0
	archivos: list[ArchivoEstado] = field(default_factory=list)
	stashes: int = 0

	@property
	def preparados(self) -> list[ArchivoEstado]:
		return [a for a in self.archivos if a.preparado]

	@property
	def sin_preparar(self) -> list[ArchivoEstado]:
		return [a for a in self.archivos if a.sin_preparar]

	@property
	def conflictos(self) -> list[ArchivoEstado]:
		return [a for a in self.archivos if a.conflicto]

	@property
	def limpio(self) -> bool:
		return not self.archivos

	def resumen(self) -> str:
		partes = [_("Rama {r}").format(r=self.rama or _("(sin rama, HEAD separado)"))]
		if self.rama_remota:
			if self.adelante or self.atras:
				partes.append(_("{a} por delante y {b} por detrás de {r}").format(a=self.adelante, b=self.atras, r=self.rama_remota))
			else:
				partes.append(_("al día con {r}").format(r=self.rama_remota))
		else:
			partes.append(_("sin rama remota"))
		if self.limpio:
			partes.append(_("sin cambios"))
		else:
			partes.append(_("{p} preparados, {s} sin preparar").format(p=len(self.preparados), s=len(self.sin_preparar)))
			if self.conflictos:
				partes.append(_("{c} en conflicto").format(c=len(self.conflictos)))
		return ", ".join(partes) + "."


def analizar_estado(salida: str) -> EstadoRepositorio:
	"""Analiza ``git status --porcelain=v2 -z --branch --show-stash``."""
	estado = EstadoRepositorio()
	entradas = salida.split("\0")
	i = 0
	while i < len(entradas):
		linea = entradas[i]
		i += 1
		if not linea:
			continue
		if linea.startswith("# "):
			partes = linea[2:].split(" ")
			clave = partes[0]
			if clave == "branch.oid":
				estado.commit = partes[1] if len(partes) > 1 else ""
			elif clave == "branch.head":
				estado.rama = "" if partes[1] == "(detached)" else partes[1]
			elif clave == "branch.upstream":
				estado.rama_remota = partes[1]
			elif clave == "branch.ab" and len(partes) >= 3:
				estado.adelante = abs(int(partes[1]))
				estado.atras = abs(int(partes[2]))
			elif clave == "stash" and len(partes) > 1:
				estado.stashes = int(partes[1])
			continue
		tipo = linea[0]
		if tipo == "1":
			campos = linea.split(" ", 8)
			xy = campos[1]
			estado.archivos.append(ArchivoEstado(campos[8], xy[0], xy[1], submodulo=campos[2] != "N..."))
		elif tipo == "2":
			campos = linea.split(" ", 9)
			xy = campos[1]
			original = entradas[i] if i < len(entradas) else ""
			i += 1
			estado.archivos.append(ArchivoEstado(campos[9], xy[0], xy[1], ruta_original=original))
		elif tipo == "u":
			campos = linea.split(" ", 10)
			xy = campos[1]
			estado.archivos.append(ArchivoEstado(campos[10], xy[0], xy[1], conflicto=True))
		elif tipo == "?":
			estado.archivos.append(ArchivoEstado(linea[2:], "?", "?"))
		elif tipo == "!":
			estado.archivos.append(ArchivoEstado(linea[2:], "!", "!"))
	return estado


# ════════════════════════════════════════════════════════════════════════════
# Historial, ramas, etiquetas, stash, remotos
# ════════════════════════════════════════════════════════════════════════════

SEPARADOR = "\x1f"
FIN_REGISTRO = "\x1e"


@dataclass
class Commit:
	sha: str
	sha_corto: str
	autor: str
	correo: str
	fecha: str
	asunto: str
	cuerpo: str = ""
	padres: list[str] = field(default_factory=list)
	referencias: str = ""

	@property
	def es_fusion(self) -> bool:
		return len(self.padres) > 1


FORMATO_LOG = SEPARADOR.join(["%H", "%h", "%an", "%ae", "%aI", "%s", "%b", "%P", "%D"]) + FIN_REGISTRO


def analizar_log(salida: str) -> list[Commit]:
	commits = []
	for registro in salida.split(FIN_REGISTRO):
		registro = registro.strip("\n")
		if not registro:
			continue
		campos = registro.split(SEPARADOR)
		if len(campos) < 9:
			continue
		commits.append(Commit(
			campos[0], campos[1], campos[2], campos[3], campos[4], campos[5], campos[6].strip(),
			campos[7].split(), campos[8],
		))
	return commits


@dataclass
class Rama:
	nombre: str
	actual: bool
	remota: bool
	sha: str
	seguimiento: str = ""
	estado_seguimiento: str = ""
	asunto: str = ""
	fecha: str = ""


def analizar_ramas(salida: str) -> list[Rama]:
	ramas = []
	for linea in salida.splitlines():
		campos = linea.split(SEPARADOR)
		if len(campos) < 7:
			continue
		nombre_completo = campos[0]
		if nombre_completo.endswith("/HEAD"):
			continue
		remota = nombre_completo.startswith("refs/remotes/")
		nombre = nombre_completo.removeprefix("refs/heads/").removeprefix("refs/remotes/")
		ramas.append(Rama(nombre, campos[1] == "*", remota, campos[2], campos[3], campos[4], campos[5], campos[6]))
	return ramas


class RepositorioLocal:
	"""Operaciones git sobre una carpeta.

	:param carpeta: carpeta de trabajo del repositorio.
	:param token: función que devuelve el token para operaciones de red por HTTPS
		(o ``None`` para usar las credenciales propias de git).
	"""

	def __init__(self, carpeta: str | Path, token: Callable[[], str | None] | None = None) -> None:
		self.carpeta = Path(carpeta)
		self._token = token or (lambda: None)

	# ── Básico ────────────────────────────────────────────────────────────────

	def git(self, *argumentos: str, **opciones) -> str:
		return ejecutar(list(argumentos), self.carpeta, **opciones)

	def git_red(self, *argumentos: str, al_linea: Callable[[str], None] | None = None,
		cancelado: Callable[[], bool] | None = None) -> str:
		"""Orden de red (fetch, pull, push, clone de submódulos) con el token si lo hay."""
		token = self._usar_token()
		return ejecutar(list(argumentos), self.carpeta, token=token, tiempo=TIEMPO_RED, analizable=False,
			al_linea=al_linea, cancelado=cancelado)

	def _usar_token(self) -> str | None:
		"""El token solo se usa si el remoto es HTTPS de GitHub; con SSH, git usa sus claves."""
		try:
			url = self.git("remote", "get-url", "origin").strip()
		except ErrorGit:
			return None
		return self._token() if url.startswith("https://") else None

	@staticmethod
	def es_repositorio(carpeta: str | Path) -> bool:
		try:
			salida = ejecutar(["rev-parse", "--is-inside-work-tree"], carpeta, tiempo=20)
			return salida.strip() == "true"
		except ErrorGit:
			return False

	def raiz(self) -> Path:
		return Path(self.git("rev-parse", "--show-toplevel").strip())

	def estado(self, ignorados: bool = False) -> EstadoRepositorio:
		argumentos = ["status", "--porcelain=v2", "-z", "--branch", "--show-stash", "--untracked-files=all"]
		if ignorados:
			argumentos.append("--ignored")
		return analizar_estado(self.git(*argumentos))

	# ── Área de preparación y confirmaciones ──────────────────────────────────

	def preparar(self, rutas: list[str]) -> None:
		if rutas:
			self.git("add", "--", *rutas)

	def preparar_todo(self) -> None:
		self.git("add", "--all")

	def quitar_de_preparados(self, rutas: list[str]) -> None:
		if rutas:
			self.git("restore", "--staged", "--", *rutas)

	def descartar_cambios(self, rutas: list[str]) -> None:
		"""Descarta cambios del directorio de trabajo (irreversible: la interfaz debe confirmar)."""
		if rutas:
			self.git("restore", "--worktree", "--", *rutas)

	def borrar_sin_seguimiento(self, rutas: list[str]) -> None:
		if rutas:
			self.git("clean", "-f", "--", *rutas)

	def confirmar(self, mensaje: str, *, enmendar: bool = False, todo: bool = False, firmar: bool = False,
		sin_verificar: bool = False, autor: str = "") -> str:
		argumentos = ["commit", "-F", "-"]
		if enmendar:
			argumentos.append("--amend")
		if todo:
			argumentos.append("--all")
		if firmar:
			argumentos.append("-S")
		if sin_verificar:
			argumentos.append("--no-verify")
		if autor:
			argumentos.append(f"--author={autor}")
		return self.git(*argumentos, entrada=mensaje, analizable=False)

	def ultimo_mensaje(self) -> str:
		return self.git("log", "-1", "--format=%B").strip()

	# ── Diferencias ───────────────────────────────────────────────────────────

	def diferencias(self, ruta: str | None = None, preparados: bool = False, contexto: int = 3) -> str:
		argumentos = ["diff", "--no-color", "--no-ext-diff", f"-U{contexto}"]
		if preparados:
			argumentos.append("--cached")
		if ruta:
			argumentos += ["--", ruta]
		return self.git(*argumentos)

	def diferencias_sin_seguimiento(self, ruta: str) -> str:
		"""Un archivo nuevo sin seguimiento como diff (todo añadido)."""
		return self.git("diff", "--no-color", "--no-index", "--", os.devnull, ruta, aceptar_codigos=(0, 1))

	def diferencias_commit(self, sha: str, ruta: str | None = None) -> str:
		argumentos = ["show", "--no-color", "--format=", "--no-ext-diff", sha]
		if ruta:
			argumentos += ["--", ruta]
		return self.git(*argumentos)

	def comparar(self, desde: str, hasta: str) -> str:
		return self.git("diff", "--no-color", f"{desde}...{hasta}")

	# ── Historial ─────────────────────────────────────────────────────────────

	def historial(self, cantidad: int = 200, ref: str = "HEAD", ruta: str | None = None, todas: bool = False,
		buscar: str = "", autor: str = "", saltar: int = 0) -> list[Commit]:
		argumentos = ["log", f"--format={FORMATO_LOG}", f"-n{int(cantidad)}", f"--skip={int(saltar)}"]
		if todas:
			argumentos.append("--all")
		else:
			argumentos.append(ref)
		if buscar:
			argumentos += [f"--grep={buscar}", "-i"]
		if autor:
			argumentos.append(f"--author={autor}")
		if ruta:
			argumentos += ["--follow", "--", ruta]
		try:
			return analizar_log(self.git(*argumentos))
		except ErrorGit as error:
			if "does not have any commits" in error.salida or "unknown revision" in error.salida:
				return []
			raise

	def reflog(self, cantidad: int = 100) -> list[str]:
		return self.git("reflog", f"-n{cantidad}", "--format=%h %gd %gs").splitlines()

	def culpables(self, ruta: str) -> list[tuple[str, str, str, int, str]]:
		"""``git blame --porcelain``: lista de (sha corto, autor, fecha, línea, texto)."""
		salida = self.git("blame", "--porcelain", "--", ruta)
		autores: dict[str, tuple[str, str]] = {}
		filas = []
		sha = ""
		linea_final = 0
		for linea in salida.splitlines():
			if re.match(r"^[0-9a-f]{40} ", linea):
				partes = linea.split()
				sha = partes[0]
				linea_final = int(partes[2])
			elif linea.startswith("author "):
				autores.setdefault(sha, (linea[7:], ""))
			elif linea.startswith("author-time "):
				from datetime import datetime

				autor = autores.get(sha, ("", ""))[0]
				autores[sha] = (autor, datetime.fromtimestamp(int(linea[12:])).strftime("%Y-%m-%d"))
			elif linea.startswith("\t"):
				autor, fecha = autores.get(sha, ("", ""))
				filas.append((sha[:8], autor, fecha, linea_final, linea[1:]))
		return filas

	# ── Ramas ─────────────────────────────────────────────────────────────────

	def ramas(self, remotas: bool = True) -> list[Rama]:
		formato = SEPARADOR.join([
			"%(refname)", "%(HEAD)", "%(objectname:short)", "%(upstream:short)", "%(upstream:track)",
			"%(contents:subject)", "%(committerdate:iso-strict)",
		])
		referencias = ["refs/heads"] + (["refs/remotes"] if remotas else [])
		return analizar_ramas(self.git("for-each-ref", f"--format={formato}", "--sort=-committerdate", *referencias))

	def rama_actual(self) -> str:
		return self.git("branch", "--show-current").strip()

	def crear_rama(self, nombre: str, desde: str = "", cambiar: bool = True) -> None:
		if cambiar:
			self.git("switch", "-c", nombre, *([desde] if desde else []))
		else:
			self.git("branch", nombre, *([desde] if desde else []))

	def cambiar_rama(self, nombre: str, crear_seguimiento: bool = False) -> None:
		if crear_seguimiento:
			local = nombre.split("/", 1)[1] if "/" in nombre else nombre
			self.git("switch", "-c", local, "--track", nombre)
		else:
			self.git("switch", nombre)

	def renombrar_rama(self, antigua: str, nueva: str) -> None:
		self.git("branch", "-m", antigua, nueva)

	def borrar_rama(self, nombre: str, forzar: bool = False) -> None:
		self.git("branch", "-D" if forzar else "-d", nombre)

	def borrar_rama_remota(self, remoto: str, nombre: str) -> None:
		self.git_red("push", remoto, "--delete", nombre)

	def fusionar(self, rama: str, sin_avance_rapido: bool = False, aplastar: bool = False, mensaje: str = "") -> str:
		argumentos = ["merge", rama]
		if sin_avance_rapido:
			argumentos.append("--no-ff")
		if aplastar:
			argumentos.append("--squash")
		if mensaje:
			argumentos += ["-m", mensaje]
		return self.git(*argumentos, analizable=False)

	def abortar_fusion(self) -> None:
		self.git("merge", "--abort")

	def reorganizar(self, sobre: str) -> str:
		return self.git("rebase", sobre, analizable=False)

	def continuar_reorganizacion(self) -> str:
		return self.git("rebase", "--continue", analizable=False)

	def abortar_reorganizacion(self) -> None:
		self.git("rebase", "--abort")

	def saltar_reorganizacion(self) -> str:
		return self.git("rebase", "--skip", analizable=False)

	def operacion_en_curso(self) -> str:
		"""«fusión», «reorganización», «cherry-pick», «revert», «bisect» o «»."""
		carpeta_git = Path(self.git("rev-parse", "--absolute-git-dir").strip())
		if (carpeta_git / "MERGE_HEAD").exists():
			return _("fusión")
		if (carpeta_git / "rebase-merge").exists() or (carpeta_git / "rebase-apply").exists():
			return _("reorganización")
		if (carpeta_git / "CHERRY_PICK_HEAD").exists():
			return _("cherry-pick")
		if (carpeta_git / "REVERT_HEAD").exists():
			return _("reversión")
		if (carpeta_git / "BISECT_LOG").exists():
			return _("bisección")
		return ""

	def elegir_cherry(self, sha: str) -> str:
		return self.git("cherry-pick", sha, analizable=False)

	def revertir(self, sha: str) -> str:
		return self.git("revert", "--no-edit", sha, analizable=False)

	def restablecer(self, ref: str, modo: str = "mixed") -> None:
		if modo not in ("soft", "mixed", "hard", "keep", "merge"):
			raise ValueError(modo)
		self.git("reset", f"--{modo}", ref)

	def resolver_con(self, ruta: str, version: str) -> None:
		"""Resuelve un conflicto quedándose con «nuestra» (ours) o «su» (theirs) versión."""
		if version not in ("ours", "theirs"):
			raise ValueError(version)
		self.git("checkout", f"--{version}", "--", ruta)
		self.git("add", "--", ruta)

	def marcar_resuelto(self, ruta: str) -> None:
		self.git("add", "--", ruta)

	# ── Remotos y red ─────────────────────────────────────────────────────────

	def remotos(self) -> list[tuple[str, str, str]]:
		"""Lista de (nombre, url, tipo «fetch»/«push»)."""
		filas = []
		for linea in self.git("remote", "-v").splitlines():
			partes = linea.split()
			if len(partes) >= 3:
				filas.append((partes[0], partes[1], partes[2].strip("()")))
		return filas

	def anadir_remoto(self, nombre: str, url: str) -> None:
		self.git("remote", "add", nombre, url)

	def borrar_remoto(self, nombre: str) -> None:
		self.git("remote", "remove", nombre)

	def cambiar_url_remoto(self, nombre: str, url: str) -> None:
		self.git("remote", "set-url", nombre, url)

	def traer(self, remoto: str = "", podar: bool = True, todo: bool = True, al_linea=None, cancelado=None) -> str:
		argumentos = ["fetch", "--progress"]
		if podar:
			argumentos.append("--prune")
		if todo and not remoto:
			argumentos.append("--all")
		elif remoto:
			argumentos.append(remoto)
		return self.git_red(*argumentos, al_linea=al_linea, cancelado=cancelado)

	def tirar(self, reorganizar: bool = False, solo_avance: bool = False, al_linea=None, cancelado=None) -> str:
		argumentos = ["pull", "--progress"]
		if reorganizar:
			argumentos.append("--rebase")
		elif solo_avance:
			argumentos.append("--ff-only")
		else:
			argumentos.append("--no-rebase")
		return self.git_red(*argumentos, al_linea=al_linea, cancelado=cancelado)

	def empujar(self, remoto: str = "origin", rama: str = "", forzar: bool = False, etiquetas: bool = False,
		establecer_seguimiento: bool = False, al_linea=None, cancelado=None) -> str:
		argumentos = ["push", "--progress"]
		if forzar:
			argumentos.append("--force-with-lease")
		if etiquetas:
			argumentos.append("--tags")
		if establecer_seguimiento:
			argumentos.append("--set-upstream")
		argumentos.append(remoto)
		if rama:
			argumentos.append(rama)
		return self.git_red(*argumentos, al_linea=al_linea, cancelado=cancelado)

	# ── Etiquetas ─────────────────────────────────────────────────────────────

	def etiquetas(self) -> list[tuple[str, str, str, str]]:
		"""(nombre, sha corto, fecha, asunto), de la más reciente a la más antigua."""
		formato = SEPARADOR.join(["%(refname:short)", "%(objectname:short)", "%(creatordate:iso-strict)", "%(contents:subject)"])
		filas = []
		for linea in self.git("for-each-ref", f"--format={formato}", "--sort=-creatordate", "refs/tags").splitlines():
			campos = linea.split(SEPARADOR)
			if len(campos) >= 4:
				filas.append((campos[0], campos[1], campos[2], campos[3]))
		return filas

	def crear_etiqueta(self, nombre: str, mensaje: str = "", ref: str = "HEAD", firmar: bool = False) -> None:
		if mensaje or firmar:
			self.git("tag", "-s" if firmar else "-a", nombre, "-m", mensaje or nombre, ref)
		else:
			self.git("tag", nombre, ref)

	def borrar_etiqueta(self, nombre: str) -> None:
		self.git("tag", "-d", nombre)

	def empujar_etiqueta(self, nombre: str, remoto: str = "origin") -> str:
		return self.git_red("push", remoto, f"refs/tags/{nombre}")

	# ── Stash ─────────────────────────────────────────────────────────────────

	def stashes(self) -> list[tuple[str, str, str]]:
		"""(referencia, fecha, mensaje)."""
		filas = []
		for linea in self.git("stash", "list", f"--format=%gd{SEPARADOR}%cI{SEPARADOR}%gs").splitlines():
			campos = linea.split(SEPARADOR)
			if len(campos) >= 3:
				filas.append((campos[0], campos[1], campos[2]))
		return filas

	def guardar_stash(self, mensaje: str = "", incluir_sin_seguimiento: bool = True) -> None:
		argumentos = ["stash", "push"]
		if incluir_sin_seguimiento:
			argumentos.append("--include-untracked")
		if mensaje:
			argumentos += ["-m", mensaje]
		self.git(*argumentos)

	def aplicar_stash(self, referencia: str, borrar: bool = False) -> str:
		return self.git("stash", "pop" if borrar else "apply", referencia, analizable=False)

	def borrar_stash(self, referencia: str) -> None:
		self.git("stash", "drop", referencia)

	def ver_stash(self, referencia: str) -> str:
		return self.git("stash", "show", "-p", "--no-color", referencia)

	# ── Configuración y otros ─────────────────────────────────────────────────

	def config(self, clave: str, global_: bool = False) -> str:
		argumentos = ["config"]
		if global_:
			argumentos.append("--global")
		argumentos += ["--get", clave]
		try:
			return self.git(*argumentos).strip()
		except ErrorGit:
			return ""

	def establecer_config(self, clave: str, valor: str, global_: bool = False) -> None:
		self.git("config", *(["--global"] if global_ else []), clave, valor)

	def submodulos(self) -> list[str]:
		return [linea.strip() for linea in self.git("submodule", "status", "--recursive").splitlines() if linea.strip()]

	def actualizar_submodulos(self, al_linea=None) -> str:
		return self.git_red("submodule", "update", "--init", "--recursive", "--progress", al_linea=al_linea)

	def archivos_seguidos(self) -> list[str]:
		return [r for r in self.git("ls-files", "-z").split("\0") if r]

	def mostrar_archivo(self, ref: str, ruta: str) -> bytes:
		return self.git("show", f"{ref}:{ruta}", binario=True)

	def lfs_disponible(self) -> bool:
		try:
			self.git("lfs", "version", tiempo=20)
			return True
		except ErrorGit:
			return False

	def limpiar(self, simular: bool = True, directorios: bool = True, ignorados: bool = False) -> str:
		argumentos = ["clean"]
		argumentos.append("-n" if simular else "-f")
		if directorios:
			argumentos.append("-d")
		if ignorados:
			argumentos.append("-x")
		return self.git(*argumentos)

	def mantenimiento(self) -> str:
		return self.git("gc", "--prune=now", analizable=False, tiempo=TIEMPO_RED)

	def bisecar(self, orden: str, ref: str = "") -> str:
		"""``git bisect start|good|bad|reset|skip``."""
		if orden not in ("start", "good", "bad", "reset", "skip"):
			raise ValueError(orden)
		return self.git("bisect", orden, *([ref] if ref else []), analizable=False)

	def worktrees(self) -> list[str]:
		return [linea for linea in self.git("worktree", "list").splitlines() if linea.strip()]

	def anadir_worktree(self, carpeta: str, rama: str) -> None:
		self.git("worktree", "add", carpeta, rama)


# ════════════════════════════════════════════════════════════════════════════
# Órdenes que no dependen de un repositorio
# ════════════════════════════════════════════════════════════════════════════


def clonar(url: str, destino: str | Path, *, token: str | None = None, rama: str = "", profundidad: int = 0,
	submodulos: bool = True, al_linea: Callable[[str], None] | None = None, cancelado: Callable[[], bool] | None = None) -> Path:
	"""Clona ``url`` en ``destino`` (la carpeta no debe existir o estar vacía)."""
	argumentos = ["clone", "--progress"]
	if rama:
		argumentos += ["--branch", rama]
	if profundidad:
		argumentos += ["--depth", str(int(profundidad))]
	if submodulos:
		argumentos.append("--recurse-submodules")
	argumentos += [url, str(destino)]
	ejecutar(argumentos, None, token=token if url.startswith("https://") else None, tiempo=TIEMPO_RED,
		analizable=False, al_linea=al_linea, cancelado=cancelado)
	return Path(destino)


def iniciar(carpeta: str | Path, rama: str = "main") -> None:
	Path(carpeta).mkdir(parents=True, exist_ok=True)
	ejecutar(["init", "-b", rama], carpeta)


def config_global(clave: str) -> str:
	try:
		return ejecutar(["config", "--global", "--get", clave], tiempo=15).strip()
	except ErrorGit:
		return ""


def establecer_config_global(clave: str, valor: str) -> None:
	ejecutar(["config", "--global", clave, valor], tiempo=15)


def generar_clave_ssh(ruta: Path, correo: str, frase: str = "") -> Path:
	"""Genera una clave ed25519 con ``ssh-keygen`` (incluido en Windows y en Git for Windows)."""
	ssh_keygen = shutil.which("ssh-keygen")
	if not ssh_keygen:
		git = buscar_git()
		if git:
			candidato = Path(git).resolve().parent.parent / "usr" / "bin" / "ssh-keygen.exe"
			if candidato.is_file():
				ssh_keygen = str(candidato)
	if not ssh_keygen:
		raise ErrorGit(_("No se encuentra ssh-keygen en este equipo."))
	ruta = Path(ruta)
	if ruta.exists():
		raise ErrorGit(_("Ya existe una clave en {r}.").format(r=ruta))
	ruta.parent.mkdir(parents=True, exist_ok=True)
	resultado = subprocess.run(
		[ssh_keygen, "-t", "ed25519", "-C", correo, "-f", str(ruta), "-N", frase],
		capture_output=True, text=True, timeout=60, **_opciones_proceso(),
	)
	if resultado.returncode != 0:
		raise ErrorGit(_("ssh-keygen falló: {e}").format(e=resultado.stderr.strip()))
	return ruta.with_suffix(ruta.suffix + ".pub") if ruta.suffix else Path(str(ruta) + ".pub")
