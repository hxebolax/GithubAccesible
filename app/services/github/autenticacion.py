"""Inicio de sesión en GitHub de todas las formas posibles y gestión de cuentas (sin wx).

Formas de iniciar sesión:

1. **Código de dispositivo (OAuth Device Flow)**: la recomendada. La
   aplicación pide un código, la persona lo escribe en
   ``https://github.com/login/device`` desde su navegador (donde ya tiene
   sesión, 2FA, llave de seguridad o passkey) y la aplicación recibe el token.
   No se teclea ninguna contraseña en la aplicación.
2. **Token de acceso personal** (clásico ``ghp_`` o de grano fino
   ``github_pat_``), pegado por la persona.
3. **Importar la sesión de GitHub CLI** (``gh auth token``) si gh está instalado.
4. **Credenciales de Git** (Git Credential Manager), con ``git credential fill``.
5. **GitHub Enterprise Server**: cualquiera de las anteriores contra otro host.

Las cuentas se guardan en la configuración (sin el token) y el token en el
almacén de secretos cifrado con DPAPI (``data/config/secretos.dat``).
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from app.services.github.cliente import HOST_GITHUB, ClienteGitHub, ErrorGitHub, NoAutorizado, normalizar_host

log = logging.getLogger(__name__)

# ID de cliente de la aplicación OAuth «GitHub Accesible» (con Device Flow activado).
# Es un dato PÚBLICO: el flujo de dispositivo no usa secreto de cliente. Se puede
# cambiar en Preferencias, Cuentas (por ejemplo, para GitHub Enterprise, donde hay
# que registrar una aplicación OAuth propia en el servidor).
ID_CLIENTE_OAUTH = "Ov23liFN65507ngE2CFC"

# Ámbitos que pide la aplicación para poder hacerlo todo. La persona puede pedir
# menos en el diálogo de inicio de sesión.
AMBITOS_COMPLETOS = (
	"repo", "workflow", "write:packages", "delete:packages", "admin:org", "admin:public_key",
	"admin:repo_hook", "admin:org_hook", "gist", "notifications", "user", "delete_repo",
	"write:discussion", "project", "admin:gpg_key", "admin:ssh_signing_key", "codespace", "read:audit_log",
)
# Los que pide GitHub CLI más lo necesario para notificaciones, Actions, proyectos y perfil.
# Los delicados (borrar repositorios, administrar organizaciones, claves, webhooks)
# solo están en el conjunto completo: se pueden pedir después repitiendo el inicio de sesión.
AMBITOS_BASICOS = (
	"repo", "read:org", "gist", "workflow", "notifications", "read:user", "user:email", "user:follow",
	"project", "read:packages",
)

DESCRIPCION_AMBITOS = {
	"repo": N_("Repositorios públicos y privados: código, issues, pull requests, ajustes."),
	"workflow": N_("Modificar los flujos de trabajo de GitHub Actions."),
	"write:packages": N_("Publicar paquetes."),
	"delete:packages": N_("Borrar paquetes."),
	"admin:org": N_("Administrar organizaciones, equipos y miembros."),
	"read:org": N_("Ver organizaciones y equipos."),
	"admin:public_key": N_("Administrar las claves SSH de la cuenta."),
	"admin:repo_hook": N_("Administrar los webhooks de los repositorios."),
	"admin:org_hook": N_("Administrar los webhooks de las organizaciones."),
	"gist": N_("Crear y editar gists."),
	"notifications": N_("Leer y marcar notificaciones."),
	"user": N_("Perfil, correos y seguidores."),
	"delete_repo": N_("Borrar repositorios."),
	"write:discussion": N_("Discusiones de equipo."),
	"project": N_("Proyectos (Projects)."),
	"admin:gpg_key": N_("Administrar las claves GPG."),
	"admin:ssh_signing_key": N_("Administrar las claves SSH de firma."),
	"codespace": N_("Codespaces."),
	"read:audit_log": N_("Registro de auditoría de la empresa u organización."),
}

URL_CREAR_TOKEN_CLASICO = "https://github.com/settings/tokens/new?description=GitHub%20Accesible&scopes="
URL_CREAR_TOKEN_FINO = "https://github.com/settings/personal-access-tokens/new"

METODO_DISPOSITIVO = "dispositivo"
METODO_TOKEN = "token"
METODO_GH = "gh"
METODO_GIT = "git"
METODO_APP = "app"

NOMBRES_METODO = {
	METODO_DISPOSITIVO: N_("Navegador con código de dispositivo"),
	METODO_TOKEN: N_("Token de acceso personal"),
	METODO_GH: N_("Sesión de GitHub CLI"),
	METODO_GIT: N_("Credenciales de Git"),
	METODO_APP: N_("Token de aplicación de GitHub"),
}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorAutenticacion(Exception):
	"""Fallo al iniciar sesión, con mensaje en español para la persona."""


# ════════════════════════════════════════════════════════════════════════════
# Cuentas
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Cuenta:
	"""Una cuenta guardada. El token NO forma parte de este objeto al guardarse."""

	usuario: str
	host: str = HOST_GITHUB
	nombre: str = ""
	metodo: str = METODO_TOKEN
	ambitos: list[str] = field(default_factory=list)
	id_usuario: int = 0
	correo: str = ""
	tipo_token: str = ""
	alta: float = field(default_factory=time.time)

	@property
	def clave(self) -> str:
		return f"{normalizar_host(self.host)}:{self.usuario.lower()}"

	@property
	def nombre_secreto(self) -> str:
		return f"token:{self.clave}"

	def descripcion(self) -> str:
		texto = self.usuario
		if self.nombre and self.nombre != self.usuario:
			texto += f" ({self.nombre})"
		if normalizar_host(self.host) != HOST_GITHUB:
			texto += " " + _("en {host}").format(host=self.host)
		return texto

	def a_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def desde_dict(cls, datos: dict[str, Any]) -> Cuenta:
		conocidos = {k: v for k, v in datos.items() if k in cls.__dataclass_fields__}
		return cls(**conocidos)


def tipo_de_token(token: str) -> str:
	"""Tipo de token según su prefijo (documentado por GitHub)."""
	prefijos = {
		"ghp_": _("token clásico"),
		"github_pat_": _("token de grano fino"),
		"gho_": _("token OAuth"),
		"ghu_": _("token de usuario de aplicación"),
		"ghs_": _("token de instalación de aplicación"),
		"ghr_": _("token de renovación"),
	}
	for prefijo, nombre in prefijos.items():
		if token.startswith(prefijo):
			return nombre
	return _("token")


def validar_token(token: str, host: str = HOST_GITHUB, metodo: str = METODO_TOKEN,
	crear_cliente: Callable[..., ClienteGitHub] = ClienteGitHub) -> Cuenta:
	"""Comprueba el token con ``GET /user`` y devuelve la ``Cuenta``.

	:raises ErrorAutenticacion: si el token no vale o no hay conexión.
	"""
	token = (token or "").strip()
	if not token:
		raise ErrorAutenticacion(_("No se ha indicado ningún token."))
	cliente = crear_cliente(token=token, host=host, usar_etag=False)
	try:
		usuario = cliente.get("/user")
	except NoAutorizado as error:
		raise ErrorAutenticacion(_("GitHub no acepta ese token: puede estar mal copiado, caducado o revocado.")) from error
	except ErrorGitHub as error:
		raise ErrorAutenticacion(error.mensaje_usuario) from error
	if not isinstance(usuario, dict) or not usuario.get("login"):
		raise ErrorAutenticacion(_("GitHub no ha devuelto los datos de la cuenta."))
	return Cuenta(
		usuario=usuario["login"],
		host=normalizar_host(host),
		nombre=usuario.get("name") or "",
		metodo=metodo,
		ambitos=list(cliente.ambitos),
		id_usuario=int(usuario.get("id") or 0),
		correo=usuario.get("email") or "",
		tipo_token=tipo_de_token(token),
	)


# ════════════════════════════════════════════════════════════════════════════
# Flujo de dispositivo (OAuth Device Flow)
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class CodigoDispositivo:
	"""Lo que devuelve GitHub al pedir un código de dispositivo."""

	codigo_dispositivo: str
	codigo_usuario: str
	url_verificacion: str
	caduca_en: int
	intervalo: int
	pedido: float = field(default_factory=time.monotonic)

	@property
	def caducado(self) -> bool:
		return time.monotonic() - self.pedido > self.caduca_en

	@property
	def codigo_deletreado(self) -> str:
		"""El código separado por espacios para que el lector lo lea letra a letra."""
		return " ".join(c for c in self.codigo_usuario if c != "-") if self.codigo_usuario else ""


_MENSAJES_DISPOSITIVO = {
	"expired_token": N_("El código ha caducado. Vuelva a empezar el inicio de sesión."),
	"access_denied": N_("Se ha cancelado la autorización en el navegador."),
	"unsupported_grant_type": N_("GitHub no admite este tipo de autorización."),
	"incorrect_client_credentials": N_("El identificador de la aplicación OAuth no es válido. Revíselo en Preferencias, Cuentas."),
	"incorrect_device_code": N_("El código de dispositivo no es válido."),
	"device_flow_disabled": N_("La aplicación OAuth no tiene activado el flujo de dispositivo (Enable Device Flow)."),
}


def _mensaje_dispositivo(error: str, descripcion: Any = None) -> str:
	"""Mensaje traducido para un código de error del flujo de dispositivo.

	Se mira antes si el código es conocido porque ``_("")`` devuelve la cabecera
	del catálogo, no una cadena vacía: sin esa comprobación nunca se usaría el respaldo.
	"""
	mensaje = _MENSAJES_DISPOSITIVO.get(error)
	return _(mensaje) if mensaje else str(descripcion or error)


class FlujoDispositivo:
	"""Implementa el flujo de dispositivo de GitHub paso a paso.

	Uso (en un hilo de trabajo)::

		flujo = FlujoDispositivo(id_cliente, ambitos)
		codigo = flujo.pedir_codigo()        # mostrar codigo.codigo_usuario y abrir la URL
		token = flujo.esperar_token(codigo, cancelado=token_cancelacion.cancelado)
	"""

	def __init__(self, id_cliente: str = ID_CLIENTE_OAUTH, ambitos: tuple[str, ...] | list[str] = AMBITOS_BASICOS,
		host: str = HOST_GITHUB, sesion: requests.Session | None = None) -> None:
		self.id_cliente = (id_cliente or "").strip()
		self.ambitos = list(ambitos)
		self.host = normalizar_host(host)
		self._sesion = sesion or requests.Session()
		self._dormir: Callable[[float], None] = time.sleep
		# Si la aplicación OAuth tiene «Expire user access tokens», GitHub da también un token
		# de renovación (válido 6 meses): aquí queda lo necesario para renovar sin molestar.
		self.renovacion: dict[str, Any] | None = None

	def _datos_renovacion(self, cuerpo: dict[str, Any]) -> dict[str, Any] | None:
		if not cuerpo.get("refresh_token"):
			return None
		ahora = time.time()
		return {
			"refresh_token": cuerpo["refresh_token"],
			"caduca": ahora + int(cuerpo.get("expires_in") or 28800),
			"caduca_renovacion": ahora + int(cuerpo.get("refresh_token_expires_in") or 15897600),
			"id_cliente": self.id_cliente,
		}

	def renovar(self, token_renovacion: str) -> tuple[str, dict[str, Any] | None]:
		"""Pide un token nuevo con el de renovación. Devuelve ``(token, datos_renovacion)``.

		Los tokens del flujo de dispositivo se renuevan sin secreto de cliente. GitHub
		invalida el token y el de renovación anteriores en cuanto se usa este.
		"""
		cuerpo = self._post(self.url_token, {
			"client_id": self.id_cliente,
			"grant_type": "refresh_token",
			"refresh_token": token_renovacion,
		})
		if not cuerpo.get("access_token"):
			raise ErrorAutenticacion(str(cuerpo.get("error_description") or cuerpo.get("error") or _("sin token")))
		return cuerpo["access_token"], self._datos_renovacion(cuerpo)

	@property
	def url_codigo(self) -> str:
		return f"https://{self.host}/login/device/code"

	@property
	def url_token(self) -> str:
		return f"https://{self.host}/login/oauth/access_token"

	def _post(self, url: str, datos: dict[str, str]) -> dict[str, Any]:
		try:
			respuesta = self._sesion.post(url, data=datos, headers={"Accept": "application/json"}, timeout=(10, 30))
		except requests.RequestException as error:
			raise ErrorAutenticacion(_("No se pudo conectar con GitHub. Compruebe la conexión a Internet.")) from error
		if respuesta.status_code == 404:
			# GitHub responde 404 cuando el Client ID no existe (mal copiado o de otro servidor).
			raise ErrorAutenticacion(_(_MENSAJES_DISPOSITIVO["incorrect_client_credentials"]))
		try:
			cuerpo = respuesta.json()
		except ValueError as error:
			raise ErrorAutenticacion(
				_("GitHub ha respondido algo inesperado (código {c}).").format(c=respuesta.status_code)
			) from error
		if respuesta.status_code >= 400 and "error" not in cuerpo:
			raise ErrorAutenticacion(_("GitHub ha rechazado la petición (código {c}).").format(c=respuesta.status_code))
		return cuerpo

	def pedir_codigo(self) -> CodigoDispositivo:
		if not self.id_cliente:
			raise ErrorAutenticacion(_(
				"Falta el identificador de la aplicación OAuth. Escríbalo en Preferencias, Cuentas, "
				"o inicie sesión con un token."
			))
		cuerpo = self._post(self.url_codigo, {"client_id": self.id_cliente, "scope": " ".join(self.ambitos)})
		if "error" in cuerpo:
			raise ErrorAutenticacion(_mensaje_dispositivo(cuerpo["error"], cuerpo.get("error_description")))
		try:
			return CodigoDispositivo(
				codigo_dispositivo=cuerpo["device_code"],
				codigo_usuario=cuerpo["user_code"],
				url_verificacion=cuerpo.get("verification_uri") or f"https://{self.host}/login/device",
				caduca_en=int(cuerpo.get("expires_in") or 900),
				intervalo=int(cuerpo.get("interval") or 5),
			)
		except (KeyError, ValueError) as error:
			raise ErrorAutenticacion(_("GitHub no ha devuelto un código de dispositivo válido.")) from error

	def comprobar_una_vez(self, codigo: CodigoDispositivo) -> tuple[str | None, str]:
		"""Pregunta una vez si ya se autorizó. Devuelve ``(token, estado)``.

		``estado``: ``ok``, ``pendiente``, ``despacio`` o lanza ``ErrorAutenticacion``.
		"""
		cuerpo = self._post(self.url_token, {
			"client_id": self.id_cliente,
			"device_code": codigo.codigo_dispositivo,
			"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
		})
		if cuerpo.get("access_token"):
			self.renovacion = self._datos_renovacion(cuerpo)
			return cuerpo["access_token"], "ok"
		error = cuerpo.get("error", "")
		if error == "authorization_pending":
			return None, "pendiente"
		if error == "slow_down":
			# GitHub pide ir más despacio: suma 5 segundos al intervalo (o el que diga).
			codigo.intervalo = int(cuerpo.get("interval") or codigo.intervalo + 5)
			return None, "despacio"
		raise ErrorAutenticacion(_mensaje_dispositivo(error, cuerpo.get("error_description")))

	def esperar_token(self, codigo: CodigoDispositivo, cancelado: Callable[[], bool] | None = None) -> str:
		"""Espera (respetando el intervalo) hasta que la persona autoriza, cancela o caduca."""
		while True:
			if cancelado and cancelado():
				raise ErrorAutenticacion(_("Inicio de sesión cancelado."))
			if codigo.caducado:
				raise ErrorAutenticacion(_(_MENSAJES_DISPOSITIVO["expired_token"]))
			# Se espera en pasos cortos para atender la cancelación enseguida.
			limite = time.monotonic() + codigo.intervalo
			while time.monotonic() < limite:
				if cancelado and cancelado():
					raise ErrorAutenticacion(_("Inicio de sesión cancelado."))
				self._dormir(0.2)
			token, _estado = self.comprobar_una_vez(codigo)
			if token:
				return token


# ════════════════════════════════════════════════════════════════════════════
# GitHub CLI y Git Credential Manager
# ════════════════════════════════════════════════════════════════════════════


def _sin_ventana() -> dict[str, Any]:
	"""Opciones de subprocess para no abrir consolas en Windows."""
	if sys.platform == "win32":
		return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
	return {}


def ruta_gh() -> str | None:
	"""Ruta del ejecutable de GitHub CLI, si está instalado."""
	encontrado = shutil.which("gh")
	if encontrado:
		return encontrado
	for candidato in (
		os.path.expandvars(r"%ProgramFiles%\GitHub CLI\gh.exe"),
		os.path.expandvars(r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe"),
	):
		if os.path.isfile(candidato):
			return candidato
	return None


def token_de_gh(host: str = HOST_GITHUB, ejecutable: str | None = None) -> str:
	"""Obtiene el token de la sesión de GitHub CLI (``gh auth token``).

	:raises ErrorAutenticacion: si gh no está instalado o no tiene sesión.
	"""
	gh = ejecutable or ruta_gh()
	if not gh:
		raise ErrorAutenticacion(_("GitHub CLI (gh) no está instalado en este equipo."))
	try:
		resultado = subprocess.run(
			[gh, "auth", "token", "--hostname", normalizar_host(host)],
			capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
			env={**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}, **_sin_ventana(),
		)
	except (OSError, subprocess.SubprocessError) as error:
		raise ErrorAutenticacion(_("No se pudo ejecutar GitHub CLI: {e}").format(e=error)) from error
	token = resultado.stdout.strip()
	if resultado.returncode != 0 or not token:
		raise ErrorAutenticacion(_(
			"GitHub CLI no tiene una sesión iniciada en {host}. Ejecute «gh auth login» o use otro método."
		).format(host=normalizar_host(host)))
	return token


def token_de_git(host: str = HOST_GITHUB, ejecutable: str | None = None, tiempo: float = 300) -> str:
	"""Pide la credencial guardada a Git (``git credential fill``).

	Con Git Credential Manager puede abrirse su propia ventana de inicio de
	sesión; por eso el tiempo de espera es largo. ``GIT_TERMINAL_PROMPT=0``
	evita que git se quede esperando en una consola invisible.
	"""
	git = ejecutable or shutil.which("git")
	if not git:
		raise ErrorAutenticacion(_("Git no está instalado en este equipo."))
	entrada = f"protocol=https\nhost={normalizar_host(host)}\n\n"
	try:
		resultado = subprocess.run(
			[git, "credential", "fill"], input=entrada, capture_output=True, text=True, encoding="utf-8",
			errors="replace", timeout=tiempo, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **_sin_ventana(),
		)
	except subprocess.TimeoutExpired as error:
		raise ErrorAutenticacion(_("Git tardó demasiado en devolver la credencial.")) from error
	except (OSError, subprocess.SubprocessError) as error:
		raise ErrorAutenticacion(_("No se pudo ejecutar git: {e}").format(e=error)) from error
	valores = dict(linea.split("=", 1) for linea in resultado.stdout.splitlines() if "=" in linea)
	token = valores.get("password", "").strip()
	if resultado.returncode != 0 or not token:
		raise ErrorAutenticacion(_("Git no tiene credenciales guardadas para {host}.").format(host=normalizar_host(host)))
	return token


# ════════════════════════════════════════════════════════════════════════════
# Gestor de cuentas
# ════════════════════════════════════════════════════════════════════════════


class GestorCuentas:
	"""Guarda las cuentas (configuración) y sus tokens (secretos cifrados).

	:param config: objeto con ``obtener``/``establecer`` (la configuración de la app).
	:param secretos: objeto con ``obtener``/``guardar``/``borrar``.
	"""

	CLAVE_LISTA = "cuentas.lista"
	CLAVE_ACTIVA = "cuentas.activa"

	def __init__(self, config: Any, secretos: Any) -> None:
		self._config = config
		self._secretos = secretos
		self._candado = threading.RLock()
		self._clientes: dict[str, ClienteGitHub] = {}
		# Aparte del candado general: renovar hace una petición de red y no debe bloquear lo demás.
		self._candado_renovar = threading.Lock()
		self._oyentes: list[Callable[[Cuenta | None], None]] = []

	def suscribir(self, funcion: Callable[[Cuenta | None], None]) -> None:
		"""``funcion(cuenta_activa)`` se llama al cambiar la cuenta activa (desde el hilo que la cambie)."""
		self._oyentes.append(funcion)

	def _avisar(self) -> None:
		activa = self.activa()
		for funcion in list(self._oyentes):
			try:
				funcion(activa)
			except Exception:  # noqa: BLE001 - un oyente roto no debe impedir el cambio de cuenta
				log.exception("Fallo en un oyente del cambio de cuenta")

	def cuentas(self) -> list[Cuenta]:
		with self._candado:
			lista = self._config.obtener(self.CLAVE_LISTA, []) or []
			return [Cuenta.desde_dict(d) for d in lista if isinstance(d, dict) and d.get("usuario")]

	def activa(self) -> Cuenta | None:
		clave = self._config.obtener(self.CLAVE_ACTIVA, "")
		cuentas = self.cuentas()
		for cuenta in cuentas:
			if cuenta.clave == clave:
				return cuenta
		return cuentas[0] if cuentas else None

	def token(self, cuenta: Cuenta) -> str | None:
		token = self._secretos.obtener(cuenta.nombre_secreto)
		if token:
			_registrar(token)
		datos = self.renovacion(cuenta)
		if token and datos and float(datos.get("caduca") or 0) - time.time() < 300:
			# A punto de caducar: se renueva antes de dárselo a quien lo pida (git, por
			# ejemplo, no sabría renovarlo él solo).
			token = self.renovar(cuenta, token) or token
		return token

	@staticmethod
	def _nombre_renovacion(cuenta: Cuenta) -> str:
		return f"{cuenta.nombre_secreto}:renovacion"

	def _guardar_juntos(self, cambios: dict[str, str | None]) -> None:
		# El token nuevo y su renovación se guardan a la vez: GitHub invalida los anteriores,
		# y guardar solo uno dejaría la cuenta sin forma de renovar.
		if hasattr(self._secretos, "guardar_varios"):
			self._secretos.guardar_varios(cambios)
			return
		for nombre, valor in cambios.items():
			if valor is None:
				self._secretos.borrar(nombre)
			else:
				self._secretos.guardar(nombre, valor)

	def renovacion(self, cuenta: Cuenta) -> dict[str, Any] | None:
		"""Datos para renovar el token de la cuenta (solo existen si su token caduca)."""
		texto = self._secretos.obtener(self._nombre_renovacion(cuenta))
		if not texto:
			return None
		try:
			datos = json.loads(texto)
		except ValueError:
			log.warning("Datos de renovación ilegibles para %s; se descartan.", cuenta.clave)
			return None
		return datos if isinstance(datos, dict) and datos.get("refresh_token") else None

	def guardar_renovacion(self, cuenta: Cuenta, datos: dict[str, Any] | None) -> None:
		"""Guarda (cifrados) o borra los datos de renovación del token de la cuenta."""
		if datos:
			_registrar(datos["refresh_token"])
		self._guardar_juntos({self._nombre_renovacion(cuenta): json.dumps(datos) if datos else None})

	def renovar(self, cuenta: Cuenta, token_rechazado: str | None = None) -> str | None:
		"""Renueva el token de la cuenta. Devuelve el nuevo, o ``None`` si no se puede.

		Si otro hilo ya lo renovó (el guardado ya no es el rechazado), devuelve ese sin
		gastar el token de renovación, que GitHub solo acepta una vez.
		"""
		with self._candado_renovar:
			actual = self._secretos.obtener(cuenta.nombre_secreto)
			if token_rechazado and actual and actual != token_rechazado:
				return actual
			datos = self.renovacion(cuenta)
			if not datos:
				return None
			if float(datos.get("caduca_renovacion") or 0) and float(datos["caduca_renovacion"]) < time.time():
				log.warning("El token de renovación de %s caducó (6 meses sin uso): hay que volver a iniciar sesión.", cuenta.clave)
				return None
			try:
				flujo = FlujoDispositivo(datos.get("id_cliente") or ID_CLIENTE_OAUTH, host=cuenta.host)
				nuevo, nuevos_datos = flujo.renovar(datos["refresh_token"])
			except ErrorAutenticacion as error:
				log.warning("No se pudo renovar el token de %s: %s", cuenta.clave, error)
				return None
			_registrar(nuevo)
			if nuevos_datos:
				_registrar(nuevos_datos["refresh_token"])
			self._guardar_juntos({
				cuenta.nombre_secreto: nuevo,
				self._nombre_renovacion(cuenta): json.dumps(nuevos_datos) if nuevos_datos else None,
			})
			with self._candado:
				cliente = self._clientes.get(cuenta.clave)
			if cliente is not None:
				cliente.cambiar_token(nuevo)
			log.info("Token de %s renovado.", cuenta.clave)
			return nuevo

	def anadir(self, cuenta: Cuenta, token: str, activar: bool = True) -> None:
		"""Añade o actualiza una cuenta y guarda su token cifrado."""
		with self._candado:
			_registrar(token)
			self._secretos.guardar(cuenta.nombre_secreto, token)
			lista = [c for c in self.cuentas() if c.clave != cuenta.clave]
			lista.append(cuenta)
			self._config.establecer(self.CLAVE_LISTA, [c.a_dict() for c in lista])
			self._clientes.pop(cuenta.clave, None)
			if activar:
				self._config.establecer(self.CLAVE_ACTIVA, cuenta.clave)
		log.info("Cuenta guardada: %s (%s)", cuenta.clave, cuenta.metodo)
		self._avisar()

	def eliminar(self, cuenta: Cuenta) -> None:
		with self._candado:
			self._guardar_juntos({cuenta.nombre_secreto: None, self._nombre_renovacion(cuenta): None})
			lista = [c for c in self.cuentas() if c.clave != cuenta.clave]
			self._config.establecer(self.CLAVE_LISTA, [c.a_dict() for c in lista])
			self._clientes.pop(cuenta.clave, None)
			if self._config.obtener(self.CLAVE_ACTIVA, "") == cuenta.clave:
				self._config.establecer(self.CLAVE_ACTIVA, lista[0].clave if lista else "")
		log.info("Cuenta eliminada: %s", cuenta.clave)
		self._avisar()

	def activar(self, cuenta: Cuenta) -> None:
		self._config.establecer(self.CLAVE_ACTIVA, cuenta.clave)
		log.info("Cuenta activa: %s", cuenta.clave)
		self._avisar()

	def cliente(self, cuenta: Cuenta | None = None) -> ClienteGitHub:
		"""Cliente de la cuenta indicada o de la activa (uno por cuenta, reutilizado).

		Sin cuentas, devuelve un cliente anónimo (búsquedas y repositorios públicos).
		"""
		cuenta = cuenta or self.activa()
		with self._candado:
			if cuenta is None:
				anonimo = self._clientes.get("")
				if anonimo is None:
					anonimo = ClienteGitHub(None)
					self._clientes[""] = anonimo
				return anonimo
			cliente = self._clientes.get(cuenta.clave)
			if cliente is None:
				cliente = ClienteGitHub(self.token(cuenta), cuenta.host,
					renovar=lambda rechazado, c=cuenta: self.renovar(c, rechazado))
				self._clientes[cuenta.clave] = cliente
			return cliente


def _registrar(token: str) -> None:
	try:
		from app.core import registro

		registro.registrar_secreto(token)
	except Exception:  # noqa: BLE001
		log.debug("No se pudo registrar el token para ocultarlo en el registro.", exc_info=True)
