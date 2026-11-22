"""Más áreas de la API: Actions, gists, notificaciones, organizaciones, equipos,
búsqueda, seguridad, paquetes, codespaces, Copilot, patrocinios (sin wx)."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from typing import Any

from app.services.github.api import _Base, _limpiar, _q, ruta_repo
from app.services.github.cliente import ErrorGitHub, ErrorValidacion, Pagina, _

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_MARCA_TIEMPO = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z ")


def limpiar_registro(texto: str, quitar_horas: bool = True) -> str:
	"""Quita códigos de color ANSI y (opcionalmente) la marca de tiempo de cada línea.

	Los registros de Actions vienen llenos de secuencias de escape que el lector
	de pantalla lee como basura y de una marca de tiempo larga al principio de
	cada línea que hay que escuchar entera antes de llegar a lo importante.
	"""
	lineas = []
	for linea in texto.splitlines():
		linea = _ANSI.sub("", linea)
		if quitar_horas:
			linea = _MARCA_TIEMPO.sub("", linea)
		lineas.append(linea.replace("##[group]", "▸ ").replace("##[endgroup]", "").replace("##[error]", "ERROR: ")
			.replace("##[warning]", "AVISO: ").replace("##[notice]", "NOTA: ").replace("##[debug]", "DEPURACIÓN: "))
	return "\n".join(lineas)


# ════════════════════════════════════════════════════════════════════════════
# GitHub Actions
# ════════════════════════════════════════════════════════════════════════════


class ApiAcciones(_Base):
	def flujos(self, nombre: str) -> list:
		return (self.c.get(f"{ruta_repo(nombre)}/actions/workflows", {"per_page": 100}) or {}).get("workflows", [])

	def flujo(self, nombre: str, id_flujo: int | str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/workflows/{_q(id_flujo)}")

	def activar_flujo(self, nombre: str, id_flujo: int | str) -> None:
		self.c.put(f"{ruta_repo(nombre)}/actions/workflows/{_q(id_flujo)}/enable")

	def desactivar_flujo(self, nombre: str, id_flujo: int | str) -> None:
		self.c.put(f"{ruta_repo(nombre)}/actions/workflows/{_q(id_flujo)}/disable")

	def lanzar_flujo(self, nombre: str, id_flujo: int | str, ref: str, entradas: dict | None = None) -> None:
		"""Lanza un flujo con ``workflow_dispatch``."""
		self.c.post(f"{ruta_repo(nombre)}/actions/workflows/{_q(id_flujo)}/dispatches", {"ref": ref, "inputs": entradas or {}})

	def ejecuciones(self, nombre: str, numero: int = 1, id_flujo: int | str | None = None, rama: str = "",
		estado: str = "", evento: str = "", actor: str = "", sha: str = "") -> Pagina:
		ruta = f"{ruta_repo(nombre)}/actions/workflows/{_q(id_flujo)}/runs" if id_flujo else f"{ruta_repo(nombre)}/actions/runs"
		params = _limpiar({"branch": rama or None, "status": estado or None, "event": evento or None, "actor": actor or None,
			"head_sha": sha or None})
		return self.c.pagina(ruta, params, numero, 50, clave="workflow_runs")

	def ejecucion(self, nombre: str, id_ejecucion: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}")

	def trabajos(self, nombre: str, id_ejecucion: int, filtro: str = "latest") -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/jobs", {"filter": filtro}, clave="jobs")

	def trabajo(self, nombre: str, id_trabajo: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/jobs/{int(id_trabajo)}")

	def registro_trabajo(self, nombre: str, id_trabajo: int) -> str:
		"""Texto del registro de un trabajo (GitHub redirige a un almacenamiento temporal)."""
		respuesta = self.c.peticion("GET", f"{ruta_repo(nombre)}/actions/jobs/{int(id_trabajo)}/logs", condicional=False,
			aceptar="application/vnd.github+json")
		respuesta.encoding = "utf-8"
		return respuesta.text

	def registros_ejecucion(self, nombre: str, id_ejecucion: int) -> dict[str, str]:
		"""Todos los registros de una ejecución: ``{archivo: texto}`` (llegan en un zip)."""
		datos = self.c.binario(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/logs", "application/vnd.github+json")
		resultado: dict[str, str] = {}
		with zipfile.ZipFile(io.BytesIO(datos)) as archivo_zip:
			for info in archivo_zip.infolist():
				if info.is_dir() or info.file_size > 50 * 1024 * 1024:
					continue
				resultado[info.filename] = archivo_zip.read(info).decode("utf-8", errors="replace")
		return resultado

	def volver_a_ejecutar(self, nombre: str, id_ejecucion: int, solo_fallidos: bool = False, depuracion: bool = False) -> None:
		accion = "rerun-failed-jobs" if solo_fallidos else "rerun"
		self.c.post(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/{accion}", {"enable_debug_logging": depuracion})

	def volver_a_ejecutar_trabajo(self, nombre: str, id_trabajo: int) -> None:
		self.c.post(f"{ruta_repo(nombre)}/actions/jobs/{int(id_trabajo)}/rerun")

	def cancelar_ejecucion(self, nombre: str, id_ejecucion: int, forzar: bool = False) -> None:
		self.c.post(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/{'force-cancel' if forzar else 'cancel'}")

	def borrar_ejecucion(self, nombre: str, id_ejecucion: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}")

	def borrar_registros(self, nombre: str, id_ejecucion: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/logs")

	def aprobar_ejecucion(self, nombre: str, id_ejecucion: int) -> None:
		self.c.post(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/approve")

	def despliegues_pendientes(self, nombre: str, id_ejecucion: int) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/pending_deployments") or []

	def revisar_despliegue(self, nombre: str, id_ejecucion: int, ids_entorno: list[int], aprobar: bool, comentario: str = "") -> list:
		return self.c.post(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/pending_deployments", {
			"environment_ids": ids_entorno, "state": "approved" if aprobar else "rejected", "comment": comentario,
		})

	def tiempos(self, nombre: str, id_ejecucion: int) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/timing")

	# Artefactos
	def artefactos(self, nombre: str, id_ejecucion: int | None = None) -> list:
		ruta = f"{ruta_repo(nombre)}/actions/runs/{int(id_ejecucion)}/artifacts" if id_ejecucion else f"{ruta_repo(nombre)}/actions/artifacts"
		return self.c.todos(ruta, clave="artifacts", maximo=500)

	def url_artefacto(self, nombre: str, id_artefacto: int) -> str:
		return self.c.url(f"{ruta_repo(nombre)}/actions/artifacts/{int(id_artefacto)}/zip")

	def borrar_artefacto(self, nombre: str, id_artefacto: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/actions/artifacts/{int(id_artefacto)}")

	# Cachés
	def caches(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/actions/caches", clave="actions_caches", maximo=1000)

	def borrar_cache(self, nombre: str, id_cache: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/actions/caches/{int(id_cache)}")

	def uso_caches(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/cache/usage")

	# Secretos y variables
	def secretos(self, nombre: str, entorno: str = "") -> list:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		return self.c.todos(f"{base}/actions/secrets", clave="secrets")

	def clave_publica_secretos(self, nombre: str, entorno: str = "", org: str = "") -> dict:
		if org:
			return self.c.get(f"/orgs/{_q(org)}/actions/secrets/public-key")
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		return self.c.get(f"{base}/actions/secrets/public-key")

	def guardar_secreto(self, nombre: str, secreto: str, valor: str, entorno: str = "") -> None:
		"""Cifra el valor con la clave pública del repositorio (sellado de libsodium) y lo guarda."""
		clave = self.clave_publica_secretos(nombre, entorno)
		cifrado = cifrar_secreto(clave["key"], valor)
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		self.c.put(f"{base}/actions/secrets/{_q(secreto)}", {"encrypted_value": cifrado, "key_id": clave["key_id"]})

	def borrar_secreto(self, nombre: str, secreto: str, entorno: str = "") -> None:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		self.c.delete(f"{base}/actions/secrets/{_q(secreto)}")

	def variables(self, nombre: str, entorno: str = "") -> list:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		return self.c.todos(f"{base}/actions/variables", clave="variables")

	def crear_variable(self, nombre: str, variable: str, valor: str, entorno: str = "") -> None:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		self.c.post(f"{base}/actions/variables", {"name": variable, "value": valor})

	def editar_variable(self, nombre: str, variable: str, valor: str, entorno: str = "") -> None:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		self.c.patch(f"{base}/actions/variables/{_q(variable)}", {"name": variable, "value": valor})

	def borrar_variable(self, nombre: str, variable: str, entorno: str = "") -> None:
		base = f"{ruta_repo(nombre)}/environments/{_q(entorno)}" if entorno else ruta_repo(nombre)
		self.c.delete(f"{base}/actions/variables/{_q(variable)}")

	# Ejecutores (runners)
	def ejecutores(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/actions/runners", clave="runners")

	def borrar_ejecutor(self, nombre: str, id_ejecutor: int) -> None:
		self.c.delete(f"{ruta_repo(nombre)}/actions/runners/{int(id_ejecutor)}")

	def token_registro_ejecutor(self, nombre: str) -> dict:
		return self.c.post(f"{ruta_repo(nombre)}/actions/runners/registration-token")

	def permisos_acciones(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/actions/permissions")

	def cambiar_permisos_acciones(self, nombre: str, activadas: bool, permitidas: str = "all") -> None:
		self.c.put(f"{ruta_repo(nombre)}/actions/permissions", {"enabled": activadas, "allowed_actions": permitidas})


def cifrar_secreto(clave_publica_b64: str, valor: str) -> str:
	"""Cifra un secreto para la API de Actions (caja sellada de libsodium: X25519 + XSalsa20-Poly1305).

	Se implementa con ``cryptography`` (ya es dependencia por el actualizador) para
	no añadir PyNaCl. Formato de la caja sellada: ``clave_efímera(32) || cifrado``,
	con el nonce = BLAKE2b(clave_efímera || clave_destino, 24 bytes).
	"""
	import hashlib

	from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
	from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

	destino_bytes = base64.b64decode(clave_publica_b64)
	destino = X25519PublicKey.from_public_bytes(destino_bytes)
	efimera = X25519PrivateKey.generate()
	efimera_publica = efimera.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
	compartido = efimera.exchange(destino)
	# BLAKE2b con salida de 24 bytes (no truncar uno de 64: el resultado es distinto).
	nonce = hashlib.blake2b(efimera_publica + destino_bytes, digest_size=24).digest()
	cifrado = _caja_xsalsa20_poly1305(compartido, nonce, valor.encode("utf-8"))
	return base64.b64encode(efimera_publica + cifrado).decode("ascii")


def _caja_xsalsa20_poly1305(compartido: bytes, nonce: bytes, mensaje: bytes) -> bytes:
	"""``crypto_box_afternm`` de NaCl: HSalsa20 deriva la clave y XSalsa20-Poly1305 cifra."""
	clave = _hsalsa20(compartido, bytes(16))  # crypto_box_beforenm
	subclave = _hsalsa20(clave, nonce[:16])
	flujo = _salsa20_flujo(subclave, nonce[16:24], len(mensaje) + 32)
	clave_poly = flujo[:32]
	cifrado = bytes(a ^ b for a, b in zip(mensaje, flujo[32:], strict=False))
	from cryptography.hazmat.primitives.poly1305 import Poly1305

	etiqueta = Poly1305.generate_tag(clave_poly, cifrado)
	return etiqueta + cifrado


def _rotl(v: int, c: int) -> int:
	return ((v << c) & 0xFFFFFFFF) | (v >> (32 - c))


def _salsa_rondas(x: list[int]) -> list[int]:
	for _i in range(10):
		x[4] ^= _rotl((x[0] + x[12]) & 0xFFFFFFFF, 7)
		x[8] ^= _rotl((x[4] + x[0]) & 0xFFFFFFFF, 9)
		x[12] ^= _rotl((x[8] + x[4]) & 0xFFFFFFFF, 13)
		x[0] ^= _rotl((x[12] + x[8]) & 0xFFFFFFFF, 18)
		x[9] ^= _rotl((x[5] + x[1]) & 0xFFFFFFFF, 7)
		x[13] ^= _rotl((x[9] + x[5]) & 0xFFFFFFFF, 9)
		x[1] ^= _rotl((x[13] + x[9]) & 0xFFFFFFFF, 13)
		x[5] ^= _rotl((x[1] + x[13]) & 0xFFFFFFFF, 18)
		x[14] ^= _rotl((x[10] + x[6]) & 0xFFFFFFFF, 7)
		x[2] ^= _rotl((x[14] + x[10]) & 0xFFFFFFFF, 9)
		x[6] ^= _rotl((x[2] + x[14]) & 0xFFFFFFFF, 13)
		x[10] ^= _rotl((x[6] + x[2]) & 0xFFFFFFFF, 18)
		x[3] ^= _rotl((x[15] + x[11]) & 0xFFFFFFFF, 7)
		x[7] ^= _rotl((x[3] + x[15]) & 0xFFFFFFFF, 9)
		x[11] ^= _rotl((x[7] + x[3]) & 0xFFFFFFFF, 13)
		x[15] ^= _rotl((x[11] + x[7]) & 0xFFFFFFFF, 18)
		x[1] ^= _rotl((x[0] + x[3]) & 0xFFFFFFFF, 7)
		x[2] ^= _rotl((x[1] + x[0]) & 0xFFFFFFFF, 9)
		x[3] ^= _rotl((x[2] + x[1]) & 0xFFFFFFFF, 13)
		x[0] ^= _rotl((x[3] + x[2]) & 0xFFFFFFFF, 18)
		x[6] ^= _rotl((x[5] + x[4]) & 0xFFFFFFFF, 7)
		x[7] ^= _rotl((x[6] + x[5]) & 0xFFFFFFFF, 9)
		x[4] ^= _rotl((x[7] + x[6]) & 0xFFFFFFFF, 13)
		x[5] ^= _rotl((x[4] + x[7]) & 0xFFFFFFFF, 18)
		x[11] ^= _rotl((x[10] + x[9]) & 0xFFFFFFFF, 7)
		x[8] ^= _rotl((x[11] + x[10]) & 0xFFFFFFFF, 9)
		x[9] ^= _rotl((x[8] + x[11]) & 0xFFFFFFFF, 13)
		x[10] ^= _rotl((x[9] + x[8]) & 0xFFFFFFFF, 18)
		x[12] ^= _rotl((x[15] + x[14]) & 0xFFFFFFFF, 7)
		x[13] ^= _rotl((x[12] + x[15]) & 0xFFFFFFFF, 9)
		x[14] ^= _rotl((x[13] + x[12]) & 0xFFFFFFFF, 13)
		x[15] ^= _rotl((x[14] + x[13]) & 0xFFFFFFFF, 18)
	return x


_SIGMA = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574]


def _palabras(datos: bytes) -> list[int]:
	return [int.from_bytes(datos[i:i + 4], "little") for i in range(0, len(datos), 4)]


def _estado_inicial(clave: bytes, entrada16: bytes) -> list[int]:
	k = _palabras(clave)
	n = _palabras(entrada16)
	return [_SIGMA[0], k[0], k[1], k[2], k[3], _SIGMA[1], n[0], n[1], n[2], n[3], _SIGMA[2], k[4], k[5], k[6], k[7], _SIGMA[3]]


def _hsalsa20(clave: bytes, entrada16: bytes) -> bytes:
	x = _salsa_rondas(_estado_inicial(clave, entrada16))
	salida = [x[0], x[5], x[10], x[15], x[6], x[7], x[8], x[9]]
	return b"".join(v.to_bytes(4, "little") for v in salida)


def _salsa20_flujo(clave: bytes, nonce8: bytes, longitud: int) -> bytes:
	resultado = bytearray()
	contador = 0
	while len(resultado) < longitud:
		entrada = nonce8 + contador.to_bytes(8, "little")
		inicial = _estado_inicial(clave, entrada)
		x = _salsa_rondas(list(inicial))
		resultado += b"".join(((a + b) & 0xFFFFFFFF).to_bytes(4, "little") for a, b in zip(x, inicial, strict=True))
		contador += 1
	return bytes(resultado[:longitud])


# ════════════════════════════════════════════════════════════════════════════
# Gists
# ════════════════════════════════════════════════════════════════════════════


class ApiGists(_Base):
	def mis_gists(self, numero: int = 1) -> Pagina:
		return self.c.pagina("/gists", numero=numero, por_pagina=100)

	def gists_de(self, login: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"/users/{_q(login)}/gists", numero=numero, por_pagina=100)

	def gists_con_estrella(self, numero: int = 1) -> Pagina:
		return self.c.pagina("/gists/starred", numero=numero, por_pagina=100)

	def gists_publicos(self, numero: int = 1) -> Pagina:
		return self.c.pagina("/gists/public", numero=numero, por_pagina=100)

	def gist(self, id_gist: str) -> dict:
		return self.c.get(f"/gists/{_q(id_gist)}")

	def crear_gist(self, archivos: dict[str, str], descripcion: str = "", publico: bool = False) -> dict:
		return self.c.post("/gists", {"description": descripcion, "public": publico,
			"files": {n: {"content": c} for n, c in archivos.items()}})

	def editar_gist(self, id_gist: str, archivos: dict[str, str | None], descripcion: str | None = None,
		renombrar: dict[str, str] | None = None) -> dict:
		"""``archivos``: ``{nombre: contenido}``; ``None`` borra el archivo."""
		ficheros: dict[str, Any] = {}
		for nombre, contenido in archivos.items():
			ficheros[nombre] = None if contenido is None else {"content": contenido}
		for antiguo, nuevo in (renombrar or {}).items():
			ficheros.setdefault(antiguo, {})
			if ficheros[antiguo] is not None:
				ficheros[antiguo]["filename"] = nuevo
		return self.c.patch(f"/gists/{_q(id_gist)}", _limpiar({"description": descripcion, "files": ficheros}))

	def borrar_gist(self, id_gist: str) -> None:
		self.c.delete(f"/gists/{_q(id_gist)}")

	def estrella_gist(self, id_gist: str, poner: bool = True) -> None:
		if poner:
			self.c.put(f"/gists/{_q(id_gist)}/star")
		else:
			self.c.delete(f"/gists/{_q(id_gist)}/star")

	def tiene_estrella_gist(self, id_gist: str) -> bool:
		return self.c.existe(f"/gists/{_q(id_gist)}/star")

	def bifurcar_gist(self, id_gist: str) -> dict:
		return self.c.post(f"/gists/{_q(id_gist)}/forks")

	def historial_gist(self, id_gist: str) -> list:
		return self.c.todos(f"/gists/{_q(id_gist)}/commits")

	def comentarios_gist(self, id_gist: str) -> list:
		return self.c.todos(f"/gists/{_q(id_gist)}/comments")

	def comentar_gist(self, id_gist: str, texto: str) -> dict:
		return self.c.post(f"/gists/{_q(id_gist)}/comments", {"body": texto})

	def borrar_comentario_gist(self, id_gist: str, id_comentario: int) -> None:
		self.c.delete(f"/gists/{_q(id_gist)}/comments/{int(id_comentario)}")


# ════════════════════════════════════════════════════════════════════════════
# Notificaciones
# ════════════════════════════════════════════════════════════════════════════

MOTIVOS_NOTIFICACION = {
	"approval_requested": "aprobación pedida",
	"assign": "asignada a usted",
	"author": "usted es autor",
	"ci_activity": "actividad de Actions",
	"comment": "comentario",
	"invitation": "invitación",
	"manual": "suscripción manual",
	"member_feature_requested": "función pedida",
	"mention": "le mencionan",
	"review_requested": "revisión pedida",
	"security_advisory_credit": "crédito en aviso de seguridad",
	"security_alert": "alerta de seguridad",
	"state_change": "cambio de estado",
	"subscribed": "repositorio vigilado",
	"team_mention": "mencionan a su equipo",
}

TIPOS_SUJETO = {
	"Issue": "Issue", "PullRequest": "Pull request", "Commit": "Commit", "Release": "Release",
	"Discussion": "Discusión", "CheckSuite": "Actions", "RepositoryVulnerabilityAlert": "Alerta de seguridad",
	"RepositoryDependabotAlertsThread": "Dependabot", "RepositoryInvitation": "Invitación",
}


class ApiNotificaciones(_Base):
	def notificaciones(self, todas: bool = False, participando: bool = False, numero: int = 1, desde: str = "") -> Pagina:
		params = _limpiar({"all": str(todas).lower(), "participating": str(participando).lower(), "since": desde or None})
		return self.c.pagina("/notifications", params, numero, 50)

	def notificaciones_repo(self, nombre: str, todas: bool = False, numero: int = 1) -> Pagina:
		return self.c.pagina(f"{ruta_repo(nombre)}/notifications", {"all": str(todas).lower()}, numero, 50)

	def marcar_todas_leidas(self, hasta: str = "") -> None:
		self.c.put("/notifications", _limpiar({"last_read_at": hasta or None, "read": True}))

	def marcar_repo_leidas(self, nombre: str) -> None:
		self.c.put(f"{ruta_repo(nombre)}/notifications", {"read": True})

	def hilo(self, id_hilo: str) -> dict:
		return self.c.get(f"/notifications/threads/{_q(id_hilo)}")

	def marcar_leida(self, id_hilo: str) -> None:
		self.c.patch(f"/notifications/threads/{_q(id_hilo)}")

	def marcar_hecha(self, id_hilo: str) -> None:
		self.c.delete(f"/notifications/threads/{_q(id_hilo)}")

	def silenciar_hilo(self, id_hilo: str) -> None:
		self.c.put(f"/notifications/threads/{_q(id_hilo)}/subscription", {"ignored": True})

	def suscribir_hilo(self, id_hilo: str) -> None:
		self.c.put(f"/notifications/threads/{_q(id_hilo)}/subscription", {"ignored": False})

	def anular_suscripcion_hilo(self, id_hilo: str) -> None:
		self.c.delete(f"/notifications/threads/{_q(id_hilo)}/subscription")


# ════════════════════════════════════════════════════════════════════════════
# Organizaciones y equipos
# ════════════════════════════════════════════════════════════════════════════


class ApiOrganizaciones(_Base):
	def mis_organizaciones(self) -> list:
		return self.c.todos("/user/orgs")

	def organizaciones_de(self, login: str) -> list:
		return self.c.todos(f"/users/{_q(login)}/orgs")

	def organizacion(self, org: str) -> dict:
		return self.c.get(f"/orgs/{_q(org)}")

	def editar_organizacion(self, org: str, **campos: Any) -> dict:
		return self.c.patch(f"/orgs/{_q(org)}", _limpiar(campos))

	def miembros(self, org: str, numero: int = 1, rol: str = "all") -> Pagina:
		return self.c.pagina(f"/orgs/{_q(org)}/members", {"role": rol}, numero, 100)

	def membresia(self, org: str, login: str) -> dict:
		return self.c.get(f"/orgs/{_q(org)}/memberships/{_q(login)}")

	def poner_membresia(self, org: str, login: str, rol: str = "member") -> dict:
		return self.c.put(f"/orgs/{_q(org)}/memberships/{_q(login)}", {"role": rol})

	def quitar_miembro(self, org: str, login: str) -> None:
		self.c.delete(f"/orgs/{_q(org)}/members/{_q(login)}")

	def invitaciones_pendientes(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/invitations")

	def invitar(self, org: str, correo_o_id: str, rol: str = "direct_member") -> dict:
		datos: dict[str, Any] = {"role": rol}
		if "@" in correo_o_id:
			datos["email"] = correo_o_id
		else:
			datos["invitee_id"] = int(correo_o_id)
		return self.c.post(f"/orgs/{_q(org)}/invitations", datos)

	def mis_membresias(self) -> list:
		return self.c.todos("/user/memberships/orgs")

	def aceptar_membresia(self, org: str) -> dict:
		return self.c.patch(f"/user/memberships/orgs/{_q(org)}", {"state": "active"})

	def salir_de_organizacion(self, org: str, login: str) -> None:
		self.c.delete(f"/orgs/{_q(org)}/memberships/{_q(login)}")

	def colaboradores_externos(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/outside_collaborators")

	def bloqueados_org(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/blocks")

	def webhooks_org(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/hooks")

	def secretos_org(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/actions/secrets", clave="secrets")

	def variables_org(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/actions/variables", clave="variables")

	def registro_auditoria(self, org: str, frase: str = "") -> list:
		return self.c.get(f"/orgs/{_q(org)}/audit-log", _limpiar({"phrase": frase or None, "per_page": 100})) or []

	def eventos_org(self, org: str, numero: int = 1) -> Pagina:
		return self.c.pagina(f"/orgs/{_q(org)}/events", numero=numero, por_pagina=100)

	# Equipos
	def equipos(self, org: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/teams")

	def mis_equipos(self) -> list:
		return self.c.todos("/user/teams")

	def equipo(self, org: str, slug: str) -> dict:
		return self.c.get(f"/orgs/{_q(org)}/teams/{_q(slug)}")

	def crear_equipo(self, org: str, nombre: str, descripcion: str = "", privacidad: str = "closed", padre: int | None = None) -> dict:
		return self.c.post(f"/orgs/{_q(org)}/teams", _limpiar({"name": nombre, "description": descripcion,
			"privacy": privacidad, "parent_team_id": padre}))

	def editar_equipo(self, org: str, slug: str, **campos: Any) -> dict:
		return self.c.patch(f"/orgs/{_q(org)}/teams/{_q(slug)}", _limpiar(campos))

	def borrar_equipo(self, org: str, slug: str) -> None:
		self.c.delete(f"/orgs/{_q(org)}/teams/{_q(slug)}")

	def miembros_equipo(self, org: str, slug: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/teams/{_q(slug)}/members")

	def anadir_a_equipo(self, org: str, slug: str, login: str, rol: str = "member") -> dict:
		return self.c.put(f"/orgs/{_q(org)}/teams/{_q(slug)}/memberships/{_q(login)}", {"role": rol})

	def quitar_de_equipo(self, org: str, slug: str, login: str) -> None:
		self.c.delete(f"/orgs/{_q(org)}/teams/{_q(slug)}/memberships/{_q(login)}")

	def repos_equipo(self, org: str, slug: str) -> list:
		return self.c.todos(f"/orgs/{_q(org)}/teams/{_q(slug)}/repos")

	def dar_repo_a_equipo(self, org: str, slug: str, nombre: str, permiso: str = "push") -> None:
		self.c.put(f"/orgs/{_q(org)}/teams/{_q(slug)}/repos/{nombre.strip('/')}", {"permission": permiso})

	def quitar_repo_a_equipo(self, org: str, slug: str, nombre: str) -> None:
		self.c.delete(f"/orgs/{_q(org)}/teams/{_q(slug)}/repos/{nombre.strip('/')}")


# ════════════════════════════════════════════════════════════════════════════
# Búsqueda
# ════════════════════════════════════════════════════════════════════════════

TIPOS_BUSQUEDA = {
	"repositories": "Repositorios",
	"code": "Código",
	"issues": "Issues y pull requests",
	"users": "Usuarios y organizaciones",
	"commits": "Commits",
	"topics": "Temas",
	"labels": "Etiquetas",
}


ACEPTAR_TEXT_MATCH = "application/vnd.github.text-match+json"
TIPOS_SEMANTICOS = ("semantic", "hybrid")


class ApiBusqueda(_Base):
	#: Caché de ``dueño/nombre`` → id numérico (las etiquetas lo exigen). Clave: (host, nombre en minúsculas).
	_ids_repositorio: dict[tuple[str, str], int] = {}

	def buscar(self, tipo: str, consulta: str, numero: int = 1, orden: str = "", direccion: str = "desc",
		por_pagina: int = 50, id_repo: int | None = None, search_type: str = "", repositorio: str = "",
		coincidencias: bool = True) -> Pagina:
		"""Busca en GitHub. ``tipo``: una clave de ``TIPOS_BUSQUEDA``.

		- Pide los fragmentos resaltados (text-match) en todos los tipos REST
		  (``coincidencias=False`` para no pedirlos); llegan en ``text_matches``.
		- Para issues y PR, GitHub exige ahora ``advanced_search``; se pide siempre.
		- ``search_type`` («semantic» o «hybrid», solo issues): búsqueda por
		  significado. Exige sesión, no admite orden y tiene su propio límite de
		  10 peticiones por minuto; quien llama debe pedir una sola página.
		- Etiquetas: GitHub exige ``repository_id``; con ``repositorio``
		  («dueño/nombre») se averigua con GET /repos.
		- ``Pagina.incompleto`` trae ``incomplete_results``.
		- Los 422 típicos se traducen a un mensaje en español.
		"""
		from app.services.busqueda import traducir_error_busqueda

		if tipo == "labels" and id_repo is None and repositorio:
			id_repo = self.id_repositorio(repositorio)
		if tipo == "labels" and id_repo is None:
			raise ErrorValidacion(_("Para buscar etiquetas hay que indicar el repositorio (dueño/nombre)."), 422)
		semantica = tipo == "issues" and search_type in TIPOS_SEMANTICOS
		params = _limpiar({"q": consulta, "sort": (orden or None) if not semantica else None,
			"order": direccion if orden and not semantica else None, "repository_id": id_repo})
		aceptar = ACEPTAR_TEXT_MATCH if coincidencias else None
		if tipo == "issues":
			params["advanced_search"] = "true"
			if semantica:
				params["search_type"] = search_type
		try:
			return self.c.pagina(f"/search/{tipo}", params, numero, por_pagina, clave="items", aceptar=aceptar)
		except ErrorValidacion as error:
			raise ErrorValidacion(traducir_error_busqueda(error), error.codigo_http, error.detalle, error.errores,
				error.documentacion) from error

	def id_repositorio(self, nombre: str) -> int:
		"""Id numérico de un repositorio (``GET /repos/dueño/nombre``), con caché en memoria."""
		clave = (self.c.host, nombre.strip().strip("/").lower())
		if clave not in ApiBusqueda._ids_repositorio:
			datos = self.c.get(ruta_repo(nombre.strip().strip("/"))) or {}
			ApiBusqueda._ids_repositorio[clave] = int(datos["id"])
		return ApiBusqueda._ids_repositorio[clave]

	def tendencias(self, fuente: str = "web_repos", periodo: str = "daily", lenguaje: str = "", idioma: str = "",
		obtener: Any = None) -> list[dict]:
		"""Repositorios («web_repos») o desarrolladores («web_devs») de github.com/trending.

		No hay API oficial: se lee la página una vez por consulta, con caché de una
		hora (ver ``app.services.busqueda.leer_tendencias``). Solo existe en github.com.
		"""
		from app.services import busqueda

		if self.c.host != "github.com":
			raise ErrorGitHub(_("Las tendencias solo existen en github.com, no en GitHub Enterprise."))
		return busqueda.leer_tendencias(fuente, periodo, lenguaje, idioma, obtener=obtener)


# ════════════════════════════════════════════════════════════════════════════
# Seguridad
# ════════════════════════════════════════════════════════════════════════════


class ApiSeguridad(_Base):
	def alertas_dependabot(self, nombre: str, estado: str = "open") -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/dependabot/alerts", {"state": estado}, maximo=1000)

	def cambiar_alerta_dependabot(self, nombre: str, numero: int, estado: str, motivo: str = "", comentario: str = "") -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/dependabot/alerts/{int(numero)}", _limpiar({
			"state": estado, "dismissed_reason": motivo or None, "dismissed_comment": comentario or None,
		}))

	def alertas_codigo(self, nombre: str, estado: str = "open") -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/code-scanning/alerts", {"state": estado}, maximo=1000)

	def cambiar_alerta_codigo(self, nombre: str, numero: int, estado: str, motivo: str = "", comentario: str = "") -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/code-scanning/alerts/{int(numero)}", _limpiar({
			"state": estado, "dismissed_reason": motivo or None, "dismissed_comment": comentario or None,
		}))

	def alertas_secretos(self, nombre: str, estado: str = "open") -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/secret-scanning/alerts", {"state": estado}, maximo=1000)

	def cambiar_alerta_secreto(self, nombre: str, numero: int, estado: str, resolucion: str = "", comentario: str = "") -> dict:
		return self.c.patch(f"{ruta_repo(nombre)}/secret-scanning/alerts/{int(numero)}", _limpiar({
			"state": estado, "resolution": resolucion or None, "resolution_comment": comentario or None,
		}))

	def avisos_seguridad(self, nombre: str) -> list:
		return self.c.todos(f"{ruta_repo(nombre)}/security-advisories")

	def avisos_globales(self, consulta: str = "", ecosistema: str = "") -> list:
		return self.c.get("/advisories", _limpiar({"keyword": consulta or None, "ecosystem": ecosistema or None, "per_page": 100})) or []

	def politica_seguridad(self, nombre: str) -> str:
		for ruta in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"):
			try:
				return self.c.texto(f"{ruta_repo(nombre)}/contents/{ruta}", "application/vnd.github.raw")
			except Exception:  # noqa: BLE001 - se prueba la siguiente ubicación
				continue
		return ""

	def activar_alertas_vulnerabilidad(self, nombre: str, activar: bool = True) -> None:
		if activar:
			self.c.put(f"{ruta_repo(nombre)}/vulnerability-alerts")
		else:
			self.c.delete(f"{ruta_repo(nombre)}/vulnerability-alerts")

	def activar_correcciones_automaticas(self, nombre: str, activar: bool = True) -> None:
		if activar:
			self.c.put(f"{ruta_repo(nombre)}/automated-security-fixes")
		else:
			self.c.delete(f"{ruta_repo(nombre)}/automated-security-fixes")

	def sbom(self, nombre: str) -> dict:
		return self.c.get(f"{ruta_repo(nombre)}/dependency-graph/sbom")

	def comparar_dependencias(self, nombre: str, base: str, cabeza: str) -> list:
		return self.c.get(f"{ruta_repo(nombre)}/dependency-graph/compare/{_q(base)}...{_q(cabeza)}") or []


# ════════════════════════════════════════════════════════════════════════════
# Paquetes, codespaces, Copilot, patrocinios, aplicaciones
# ════════════════════════════════════════════════════════════════════════════


class ApiPaquetes(_Base):
	TIPOS = ("npm", "maven", "rubygems", "docker", "nuget", "container")

	def paquetes(self, tipo: str = "container", org: str = "") -> list:
		ruta = f"/orgs/{_q(org)}/packages" if org else "/user/packages"
		return self.c.todos(ruta, {"package_type": tipo})

	def versiones_paquete(self, tipo: str, nombre: str, org: str = "") -> list:
		ruta = f"/orgs/{_q(org)}/packages/{tipo}/{_q(nombre)}/versions" if org else f"/user/packages/{tipo}/{_q(nombre)}/versions"
		return self.c.todos(ruta)

	def borrar_paquete(self, tipo: str, nombre: str, org: str = "") -> None:
		ruta = f"/orgs/{_q(org)}/packages/{tipo}/{_q(nombre)}" if org else f"/user/packages/{tipo}/{_q(nombre)}"
		self.c.delete(ruta)

	def borrar_version_paquete(self, tipo: str, nombre: str, id_version: int, org: str = "") -> None:
		base = f"/orgs/{_q(org)}" if org else "/user"
		self.c.delete(f"{base}/packages/{tipo}/{_q(nombre)}/versions/{int(id_version)}")


class ApiCodespaces(_Base):
	def codespaces(self) -> list:
		return self.c.todos("/user/codespaces", clave="codespaces")

	def crear_codespace(self, nombre: str, rama: str = "", maquina: str = "") -> dict:
		repo = self.c.get(ruta_repo(nombre))
		return self.c.post("/user/codespaces", _limpiar({"repository_id": repo["id"], "ref": rama or None, "machine": maquina or None}))

	def iniciar_codespace(self, nombre_cs: str) -> dict:
		return self.c.post(f"/user/codespaces/{_q(nombre_cs)}/start")

	def detener_codespace(self, nombre_cs: str) -> dict:
		return self.c.post(f"/user/codespaces/{_q(nombre_cs)}/stop")

	def borrar_codespace(self, nombre_cs: str) -> None:
		self.c.delete(f"/user/codespaces/{_q(nombre_cs)}")

	def maquinas(self, nombre: str) -> list:
		return (self.c.get(f"{ruta_repo(nombre)}/codespaces/machines") or {}).get("machines", [])


class ApiVarios(_Base):
	def copilot_asientos_org(self, org: str) -> dict:
		return self.c.get(f"/orgs/{_q(org)}/copilot/billing")

	def instalaciones_apps(self) -> list:
		return self.c.todos("/user/installations", clave="installations")

	def autorizaciones_sso(self) -> list:
		return []

	def facturacion_actions(self, org: str = "") -> dict:
		if org:
			return self.c.get(f"/orgs/{_q(org)}/settings/billing/actions")
		return {}

	def meta(self) -> dict:
		return self.c.get("/meta")

	def zen(self) -> str:
		return self.c.texto("/zen", "text/plain")

	def estado_github(self) -> dict:
		"""Estado del servicio (githubstatus.com), sin autenticar."""
		import requests

		respuesta = requests.get("https://www.githubstatus.com/api/v2/summary.json", timeout=15)
		respuesta.raise_for_status()
		return respuesta.json()
