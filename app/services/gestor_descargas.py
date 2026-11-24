"""Gestor de descargas de la aplicación: varias a la vez, en segundo plano, con pausa y reanudación.

Por qué: antes cada ventana lanzaba su descarga y, al cerrarla, la descarga se
cancelaba y se perdía lo bajado. Ahora las descargas son de la APLICACIÓN: la
ventana que las pide puede cerrarse y se siguen bajando; el gestor (ventana
«Descargas») las muestra, las pausa, las reanuda, las cancela y explica los
errores.

Cómo:

- Cada descarga activa tiene su hilo y un ``threading.Event`` para pararla. Se
  descargan como mucho ``simultaneas()`` a la vez; el resto espera en cola.
- Se usa ``app.core.descargas.descargar``: escribe en ``<destino>.parcial`` y,
  al reanudar, pide el resto con ``Range`` (e ``If-Range``). Pausar es parar
  conservando el parcial; cancelar es parar y borrarlo.
- Se guarda en ``data/config/descargas.json`` (escritura atómica) en cada cambio
  de estado, no en cada trozo. Al cerrar la aplicación, lo que se estaba bajando
  queda en pausa marcado como «interrumpida» y, si Preferencias lo pide, sigue
  solo al volver a abrirla.
- Sin wx: avisa a los oyentes (``suscribir``) desde el hilo de la descarga; la
  interfaz los pasa por ``wx.CallAfter``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core import i18n  # noqa: F401 - instala _ y N_ aunque se importe suelto (pruebas)
from app.core import descargas

log = logging.getLogger(__name__)

PENDIENTE = "pendiente"
DESCARGANDO = "descargando"
PAUSADA = "pausada"
COMPLETADA = "completada"
ERROR = "error"
CANCELADA = "cancelada"

#: Estados visibles: se traducen al mostrarlos.
NOMBRES_ESTADO = {
	PENDIENTE: N_("En cola"),
	DESCARGANDO: N_("Descargando"),
	PAUSADA: N_("En pausa"),
	COMPLETADA: N_("Completada"),
	ERROR: N_("Error"),
	CANCELADA: N_("Cancelada"),
}
ACTIVAS = (PENDIENTE, DESCARGANDO)
TERMINADAS = (COMPLETADA, CANCELADA)
ARCHIVO = "descargas.json"
#: Una descarga avisa de su progreso como mucho una vez por segundo (la lista no necesita más).
INTERVALO_AVISO = 1.0


def _ahora() -> str:
	return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Descarga:
	"""Una descarga del gestor. Lo que no empieza por ``_`` se guarda en disco."""

	url: str
	destino: str
	nombre: str
	id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
	aceptar: str = ""
	sha256: str = ""
	cuenta: str = ""
	origen: str = ""
	estado: str = PENDIENTE
	hecho: int = 0
	total: int | None = None
	error: str = ""
	ruta_final: str = ""
	creada: str = field(default_factory=_ahora)
	terminada: str = ""
	#: Se paró al cerrar la aplicación (no la pausó la persona): puede seguir sola al volver.
	interrumpida: bool = False
	#: Sustituir el archivo si ya existe (la persona lo eligió en «Guardar como» y aceptó). Si no, «nombre (1).ext».
	sobrescribir: bool = False
	_velocidad: float = 0.0

	@property
	def porcentaje(self) -> int | None:
		if self.estado == COMPLETADA:
			return 100
		if not self.total:
			return None
		return min(100, int(self.hecho * 100 / self.total))

	@property
	def restante_s(self) -> float | None:
		if self.estado != DESCARGANDO or not self.total or self._velocidad <= 0:
			return None
		return max(0.0, (self.total - self.hecho) / self._velocidad)

	@property
	def activa(self) -> bool:
		return self.estado in ACTIVAS

	def ruta_parcial(self) -> Path:
		destino = Path(self.destino)
		return destino.with_name(destino.name + descargas.SUFIJO_PARCIAL)

	def a_dict(self) -> dict:
		return {k: v for k, v in asdict(self).items() if not k.startswith("_")}

	@classmethod
	def de_dict(cls, datos: dict) -> Descarga | None:
		validos = {f.name for f in fields(cls) if not f.name.startswith("_")}
		limpio = {k: v for k, v in (datos or {}).items() if k in validos}
		if not limpio.get("url") or not limpio.get("destino"):
			return None
		limpio.setdefault("nombre", Path(limpio["destino"]).name)
		return cls(**limpio)


@dataclass
class _Activa:
	hilo: threading.Thread
	parar: threading.Event
	motivo: str = PAUSADA  # en qué estado queda si se para: PAUSADA o CANCELADA


class GestorDescargas:
	"""Cola de descargas de la aplicación (una instancia, en el contexto).

	:param carpeta_config: donde se guarda ``descargas.json`` (``data/config``).
	:param sesion_para: ``(cuenta, aceptar) -> requests.Session`` con las cabeceras de
		la cuenta (token incluido). Se pide al empezar o reanudar cada descarga.
	:param simultaneas: cuántas se bajan a la vez (se lee cada vez: Preferencias al momento).
	"""

	def __init__(self, carpeta_config: Path, sesion_para: Callable[[str, str], Any],
		simultaneas: Callable[[], int] = lambda: 3) -> None:
		self._ruta = Path(carpeta_config) / ARCHIVO
		self._sesion_para = sesion_para
		self._simultaneas = simultaneas
		self._candado = threading.RLock()
		self._descargas: list[Descarga] = []
		self._activas: dict[str, _Activa] = {}
		self._oyentes: list[Callable[[str, Descarga], None]] = []
		self._ultimo_aviso: dict[str, float] = {}
		self._cerrando = False

	# ── Consulta ──────────────────────────────────────────────────────────────

	def descargas(self) -> list[Descarga]:
		with self._candado:
			return list(self._descargas)

	def buscar(self, identificador: str) -> Descarga | None:
		with self._candado:
			return next((d for d in self._descargas if d.id == identificador), None)

	def cuenta_por_estado(self) -> dict[str, int]:
		cuentas: dict[str, int] = {}
		with self._candado:
			for d in self._descargas:
				cuentas[d.estado] = cuentas.get(d.estado, 0) + 1
		return cuentas

	def hay_activas(self) -> bool:
		with self._candado:
			return any(d.activa for d in self._descargas)

	# ── Oyentes ───────────────────────────────────────────────────────────────

	def suscribir(self, funcion: Callable[[str, Descarga], None]) -> Callable[[], None]:
		"""``funcion(evento, descarga)``: «anadida», «estado», «progreso», «quitada». Desde CUALQUIER hilo."""
		self._oyentes.append(funcion)
		return lambda: self._oyentes.remove(funcion) if funcion in self._oyentes else None

	def _avisar(self, evento: str, descarga: Descarga) -> None:
		for funcion in list(self._oyentes):
			try:
				funcion(evento, descarga)
			except Exception:  # noqa: BLE001 - un oyente roto no para las descargas
				log.exception("Falló un oyente del gestor de descargas")

	# ── Persistencia ──────────────────────────────────────────────────────────

	def cargar(self, reanudar_interrumpidas: bool = True) -> None:
		"""Lee las descargas guardadas. Las que se cortaron al cerrar siguen si ``reanudar_interrumpidas``."""
		try:
			datos = json.loads(self._ruta.read_text(encoding="utf-8"))
		except FileNotFoundError:
			return
		except (OSError, ValueError):
			log.warning("No se pudo leer %s; se empieza con la lista vacía", self._ruta, exc_info=True)
			return
		cargadas = [d for d in (Descarga.de_dict(x) for x in (datos.get("descargas") if isinstance(datos, dict) else []) or []) if d]
		with self._candado:
			for d in cargadas:
				if d.estado in ACTIVAS:
					d.estado, d.interrumpida = PAUSADA, True
				if d.interrumpida and reanudar_interrumpidas and d.estado == PAUSADA:
					d.estado, d.interrumpida = PENDIENTE, False
				self._descargas.append(d)
		self._planificar()

	def guardar(self) -> None:
		with self._candado:
			datos = {"descargas": [d.a_dict() for d in self._descargas]}
		try:
			self._ruta.parent.mkdir(parents=True, exist_ok=True)
			descriptor, temporal = tempfile.mkstemp(prefix=ARCHIVO + ".", suffix=".tmp", dir=self._ruta.parent)
			with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
				json.dump(datos, archivo, ensure_ascii=False, indent="\t")
			os.replace(temporal, self._ruta)
		except OSError:
			log.warning("No se pudo guardar la lista de descargas en %s", self._ruta, exc_info=True)

	# ── Órdenes ───────────────────────────────────────────────────────────────

	def anadir(self, url: str, destino: str | os.PathLike[str], nombre: str = "", *, aceptar: str = "", sha256: str = "",
		cuenta: str = "", origen: str = "", sobrescribir: bool = False) -> Descarga:
		"""Pone una descarga en la cola (o devuelve la que ya baja ese archivo) y la empieza si hay hueco."""
		destino = str(Path(destino))
		with self._candado:
			existente = next((d for d in self._descargas if d.destino == destino and d.url == url and d.estado != CANCELADA
				and d.estado != COMPLETADA), None)
			if existente is not None:
				if existente.estado in (PAUSADA, ERROR):
					self.reanudar(existente.id)
				return existente
			descarga = Descarga(url, destino, nombre or Path(destino).name, aceptar=aceptar, sha256=sha256, cuenta=cuenta,
				origen=origen, sobrescribir=sobrescribir)
			self._descargas.append(descarga)
		self._avisar("anadida", descarga)
		self.guardar()
		self._planificar()
		return descarga

	def pausar(self, identificador: str) -> bool:
		return self._parar(identificador, PAUSADA)

	def cancelar(self, identificador: str) -> bool:
		"""Para y borra lo bajado (el ``.parcial``). La descarga queda en la lista como cancelada."""
		descarga = self.buscar(identificador)
		if descarga is None or descarga.estado in (COMPLETADA, CANCELADA):
			return False
		if not self._parar(identificador, CANCELADA):
			# No estaba bajando (en cola, en pausa o con error): se cancela aquí mismo.
			self._borrar_parcial(descarga)
			self._cambiar(descarga, CANCELADA)
		return True

	def reanudar(self, identificador: str) -> bool:
		"""En pausa, con error o cancelada: vuelve a la cola (continúa donde se quedó si hay parcial)."""
		descarga = self.buscar(identificador)
		if descarga is None or descarga.estado not in (PAUSADA, ERROR, CANCELADA):
			return False
		descarga.error, descarga.interrumpida = "", False
		self._cambiar(descarga, PENDIENTE)
		self._planificar()
		return True

	def quitar(self, identificador: str) -> bool:
		"""Quita de la lista. Si aún baja, la cancela antes (y borra el parcial); el archivo terminado no se toca."""
		descarga = self.buscar(identificador)
		if descarga is None:
			return False
		if descarga.estado not in (COMPLETADA, CANCELADA):
			self.cancelar(identificador)
			activa = self._activas.get(identificador)
			if activa is not None:
				activa.hilo.join(timeout=5)
		with self._candado:
			if descarga in self._descargas:
				self._descargas.remove(descarga)
		self._avisar("quitada", descarga)
		self.guardar()
		return True

	def quitar_terminadas(self) -> int:
		"""Quita de la lista las completadas y las canceladas (los archivos no se tocan). Devuelve cuántas."""
		with self._candado:
			terminadas = [d for d in self._descargas if d.estado in TERMINADAS]
			self._descargas = [d for d in self._descargas if d.estado not in TERMINADAS]
		for descarga in terminadas:
			self._avisar("quitada", descarga)
		if terminadas:
			self.guardar()
		return len(terminadas)

	def pausar_todas(self) -> int:
		cuantas = 0
		for descarga in self.descargas():
			if descarga.estado == PENDIENTE:
				self._cambiar(descarga, PAUSADA)
				cuantas += 1
			elif descarga.estado == DESCARGANDO and self.pausar(descarga.id):
				cuantas += 1
		return cuantas

	def reanudar_todas(self) -> int:
		return sum(1 for d in self.descargas() if d.estado in (PAUSADA, ERROR) and self.reanudar(d.id))

	def detener(self, espera: float = 5.0) -> None:
		"""Al cerrar la aplicación: para lo que baja conservando lo bajado, para seguir la próxima vez."""
		self._cerrando = True
		with self._candado:
			activas = list(self._activas.items())
			for d in self._descargas:
				if d.estado == PENDIENTE:
					d.estado, d.interrumpida = PAUSADA, True
		for identificador, activa in activas:
			activa.motivo = PAUSADA
			activa.parar.set()
			descarga = self.buscar(identificador)
			if descarga is not None:
				descarga.interrumpida = True
		limite = time.monotonic() + espera
		for _identificador, activa in activas:
			activa.hilo.join(timeout=max(0.0, limite - time.monotonic()))
		self.guardar()

	# ── Funcionamiento ────────────────────────────────────────────────────────

	def _parar(self, identificador: str, motivo: str) -> bool:
		descarga = self.buscar(identificador)
		if descarga is None:
			return False
		with self._candado:
			activa = self._activas.get(identificador)
			if activa is not None:
				activa.motivo = motivo
				activa.parar.set()
				return True
			if descarga.estado == PENDIENTE and motivo == PAUSADA:
				self._cambiar(descarga, PAUSADA)
				return True
		return False

	def _cambiar(self, descarga: Descarga, estado: str, guardar: bool = True) -> None:
		descarga.estado = estado
		if estado in (COMPLETADA, ERROR, CANCELADA):
			descarga.terminada = _ahora()
		if estado != DESCARGANDO:
			descarga._velocidad = 0.0
		self._avisar("estado", descarga)
		if guardar:
			self.guardar()

	def _planificar(self) -> None:
		if self._cerrando:
			return
		with self._candado:
			hueco = max(1, int(self._simultaneas() or 1)) - len(self._activas)
			for descarga in [d for d in self._descargas if d.estado == PENDIENTE][:max(0, hueco)]:
				parar = threading.Event()
				hilo = threading.Thread(target=self._trabajar, args=(descarga, parar), name=f"descarga-{descarga.id}", daemon=True)
				self._activas[descarga.id] = _Activa(hilo, parar)
				descarga.error = ""
				self._cambiar(descarga, DESCARGANDO, guardar=False)
				hilo.start()
		self.guardar()

	def _borrar_parcial(self, descarga: Descarga) -> None:
		parcial = descarga.ruta_parcial()
		for ruta in (parcial, parcial.with_name(Path(descarga.destino).name + descargas.SUFIJO_METADATOS)):
			try:
				ruta.unlink(missing_ok=True)
			except OSError:
				log.debug("No se pudo borrar %s", ruta, exc_info=True)

	def _trabajar(self, descarga: Descarga, parar: threading.Event) -> None:
		marcas = {"t": time.monotonic(), "hecho": descarga.hecho}

		def al_progresar(hecho: int, total: int | None) -> None:
			ahora = time.monotonic()
			if ahora - marcas["t"] >= 0.5:
				instantanea = (hecho - marcas["hecho"]) / (ahora - marcas["t"])
				# Media móvil: la velocidad que se lee no salta de un valor a otro cada medio segundo.
				descarga._velocidad = instantanea if descarga._velocidad <= 0 else 0.7 * descarga._velocidad + 0.3 * instantanea
				marcas["t"], marcas["hecho"] = ahora, hecho
			descarga.hecho, descarga.total = hecho, total
			if ahora - self._ultimo_aviso.get(descarga.id, 0.0) >= INTERVALO_AVISO:
				self._ultimo_aviso[descarga.id] = ahora
				self._avisar("progreso", descarga)

		estado_final, mensaje = ERROR, ""
		try:
			sesion = self._sesion_para(descarga.cuenta, descarga.aceptar)
			resultado = descargas.descargar(
				descarga.url, descarga.destino, sha256=descarga.sha256 or None, reanudar=True, al_progresar=al_progresar,
				cancelacion=parar, sesion=sesion, conservar_parcial=True, sobrescribir=descarga.sobrescribir,
			)
			descarga.ruta_final, descarga.hecho, descarga.total = str(resultado.ruta), resultado.tamano, resultado.tamano
			estado_final = COMPLETADA
		except descargas.DescargaCancelada:
			activa = self._activas.get(descarga.id)
			estado_final = activa.motivo if activa is not None else PAUSADA
			if estado_final == CANCELADA:
				self._borrar_parcial(descarga)
				descarga.hecho = 0
		except Exception as error:  # noqa: BLE001 - cualquier fallo se ve en el gestor, con su explicación
			log.warning("Falló la descarga de %s", descarga.nombre, exc_info=True)
			mensaje = getattr(error, "mensaje_usuario", None) or str(error) or type(error).__name__
		finally:
			with self._candado:
				self._activas.pop(descarga.id, None)
			self._ultimo_aviso.pop(descarga.id, None)
		descarga.error = mensaje if estado_final == ERROR else ""
		self._cambiar(descarga, estado_final)
		self._planificar()
